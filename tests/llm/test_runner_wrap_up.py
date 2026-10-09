"""轮数将尽时的收尾催促与降级回退守卫。

实盘现象：某分析师连续 12 轮只调工具、从未提交，被 runner 硬停后报告退化为占位文本
（且占位文案误写为「LLM 返回空响应」，把排查方向带偏）。本测试锁定三件事：

1. 最后一轮注入收尾催促（且仅一次），且只在预算 >= 3 轮时启用；
2. 小额预算与正常收尾路径不受影响（避免挤占首轮工作）；
3. 占位文案按真实原因区分（轮数耗尽 ≠ 模型空响应）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.llm.core.base import BaseLLMClient, StreamEvent
from app.llm.core.types import (
    ChatResponse,
    Message,
    Role,
    StopReason,
    TextBlock,
    ToolDef,
    ToolUseBlock,
)
from app.llm.runner import WRAP_UP_INSTRUCTION, run_conversation

AGENTS_PATH = Path(__file__).resolve().parents[2] / "app" / "engine" / "orchestrator" / "agents.py"


def _chat_response(blocks, stop_reason=StopReason.END_TURN) -> ChatResponse:
    return ChatResponse(message=Message(role=Role.ASSISTANT, content=blocks), stop_reason=stop_reason)


class _ScriptedLLM(BaseLLMClient):
    """按脚本逐轮返回：最多一次文本轮，其余轮返回工具调用。"""

    protocol = "openai"

    def __init__(
        self,
        *,
        text_on_turn: int | None = None,
        finish_on_turn: int | None = None,
        text: str = "阶段性结论：数据已足够",
    ):
        self.model = "scripted-model"
        self.text_on_turn = text_on_turn
        self.finish_on_turn = finish_on_turn
        self.text = text
        self.seen_messages: list = []
        self.turn = 0  # 真实轮次计数（不能用消息条数：每轮会追加多条消息）

    async def chat(self, messages, *, system=None, **kwargs) -> ChatResponse:
        self.seen_messages = list(messages)
        self.turn += 1
        turn = self.turn
        if self.finish_on_turn is not None and turn == self.finish_on_turn:
            # 只回文本 → 循环正常收尾
            return _chat_response([TextBlock(text=self.text)])
        blocks = []
        if self.text_on_turn is not None and turn == self.text_on_turn:
            # 文本 + 工具调用同行 → 循环继续（用于验证"最后一轮被迫停止时仍有正文可回退"）
            blocks.append(TextBlock(text=self.text))
        blocks.append(ToolUseBlock(id=f"call_{turn}", name="noop", input={"n": turn}))
        return _chat_response(blocks, stop_reason=StopReason.TOOL_USE)

    async def chat_stream(self, messages, *, system=None, **kwargs):
        yield StreamEvent("message", response=await self.chat(messages, system=system))

    async def count_tokens(self, messages) -> int:
        return 1


def _noop_tool() -> list[ToolDef]:
    async def handler(**kwargs):
        return "ok"

    return [ToolDef(name="noop", description="noop", params_schema={}, handler=handler)]


def _nudge_count(messages) -> int:
    n = 0
    for m in messages:
        content = m.content if isinstance(m.content, str) else ""
        if WRAP_UP_INSTRUCTION in content:
            n += 1
    return n


class TestWrapUpNudge:
    @pytest.mark.asyncio
    async def test_small_budget_does_not_inject_nudge(self):
        """1~2 轮预算没有回旋余地，催促只会挤占首轮工作，因此不注入。"""
        result = await run_conversation(
            _ScriptedLLM(), "开始分析", tools=_noop_tool(), max_turns=2
        )
        assert result.stop_reason == "max_turns"
        assert _nudge_count(result.messages) == 0

    @pytest.mark.asyncio
    async def test_last_turn_injects_wrap_up_nudge_once(self):
        result = await run_conversation(
            _ScriptedLLM(), "开始分析", tools=_noop_tool(), max_turns=3
        )
        assert result.stop_reason == "max_turns"
        assert _nudge_count(result.messages) == 1, "最后一轮必须注入且只注入一次收尾催促"

    @pytest.mark.asyncio
    async def test_nudge_not_injected_when_agent_finishes_early(self):
        """正常收尾（模型主动给出文本）时不得注入催促，避免打断既有节奏。"""
        result = await run_conversation(
            _ScriptedLLM(finish_on_turn=2), "开始分析", tools=_noop_tool(), max_turns=5
        )
        assert result.stop_reason != "max_turns"
        assert _nudge_count(result.messages) == 0

class TestPlaceholderTruthfulness:
    """占位文案必须反映真实原因（否则会误导排查方向）。"""

    def _source(self) -> str:
        return AGENTS_PATH.read_text(encoding="utf-8")

    def test_max_turns_has_distinct_placeholder(self):
        source = self._source()
        block = source[source.index("final_report = submission.content.strip()") :][:600]
        assert 'result.stop_reason == "max_turns"' in block, "应按停止原因区分占位文案"
        assert "已达最大工具轮数" in block, "轮数耗尽的占位文案需说明真实原因"

    def test_empty_response_placeholder_retained(self):
        block = self._source()
        block = block[block.index("final_report = submission.content.strip()") :][:600]
        assert "LLM 返回空响应" in block, "模型确实返回空内容的分支需保留"

    def test_placeholder_mentions_configured_limit(self):
        block = self._source()
        block = block[block.index("final_report = submission.content.strip()") :][:600]
        assert re.search(r"max_tool_calls", block), "占位文案应带上实际轮数上限，便于定位"
