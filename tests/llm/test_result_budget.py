"""result_budget 单元测试（本地逻辑 + 真实文件 I/O，无需 API）。

覆盖（对齐 3d39223c「移除 LLM 数据链路全部截断点」后的语义）：
- 全量直传：任何长度结果原样返回（预算截断已停用，预览式截断对模型
  等同数据丢失——模型不会主动读落盘文件）
- registry.execute 直传（大结果不再缩为预览）
- registry.extend 公共 API（子代理工具子集并入）
- EventSink.on_progress 进度通道（progress 事件不落库、转发文本）
"""

from app.llm.events import EventSink
from app.llm.tools.registry import ToolRegistry
from app.llm.tools.result_budget import (
    DEFAULT_MAX_RESULT_CHARS,
    apply_result_budget,
)


class TestApplyResultBudget:
    def test_under_limit_passthrough(self):
        out = apply_result_budget("my_tool", "short result", task_id="t1")
        assert out == "short result"

    def test_over_limit_full_passthrough(self, tmp_path, monkeypatch):
        """超限结果全量直传：无截断、无「已保存」预览文案（3d39223c 语义）。"""
        monkeypatch.chdir(tmp_path)
        big = "x" * (DEFAULT_MAX_RESULT_CHARS + 10_000)
        out = apply_result_budget("my_tool", big, task_id="task-预算")

        assert out == big
        assert "已保存" not in out
        assert "已截断" not in out

    def test_custom_max_chars_ignored_semantics(self, tmp_path, monkeypatch):
        """自定义阈值同样不触发截断：停用是全局决策，max_chars 仅保留签名兼容。"""
        monkeypatch.chdir(tmp_path)
        out = apply_result_budget("t", "a" * 50, task_id="", max_chars=10)
        assert out == "a" * 50

    def test_unsafe_task_id_passthrough(self, tmp_path, monkeypatch):
        """task_id 不再用于目录隔离（无落盘），任何字符都安全直传。"""
        monkeypatch.chdir(tmp_path)
        payload = "a" * (DEFAULT_MAX_RESULT_CHARS + 100)
        out = apply_result_budget("t", payload, task_id="../evil/id")
        assert out == payload


class TestRegistryBudgetIntegration:
    async def test_execute_full_passthrough(self, tmp_path, monkeypatch):
        """registry.execute 大结果全量直传（预算停用后不再缩为预览）。"""
        monkeypatch.chdir(tmp_path)
        reg = ToolRegistry()

        @reg.register
        def big_tool() -> str:
            """返回大结果"""
            return "y" * (DEFAULT_MAX_RESULT_CHARS + 5_000)

        out = await reg.execute("big_tool", {}, task_id="tk1")
        assert len(out) == DEFAULT_MAX_RESULT_CHARS + 5_000
        assert "已保存" not in out

    async def test_execute_small_untouched(self):
        reg = ToolRegistry()

        @reg.register
        def small_tool() -> str:
            """小结果"""
            return "ok"

        assert await reg.execute("small_tool", {}) == "ok"

    def test_extend_reuses_defs(self):
        from app.llm.core.types import ToolDef

        reg = ToolRegistry()

        def handler(x: int) -> str:
            return str(x)

        defs = [ToolDef(name="ext_tool", description="外部工具", params_schema={"type": "object", "properties": {}}, handler=handler)]
        reg.extend(defs)
        assert reg.get("ext_tool") is not None
        assert reg.defs()[0].handler is handler


class TestEventSinkProgressChannel:
    async def test_progress_event_forwarded_not_persisted(self):
        received = []
        persisted = []
        sink = EventSink(
            task_id="t-prog",
            on_event=lambda ev: received.append(ev),
            on_persist=lambda batch: persisted.extend(batch),
            on_progress=lambda text: None,  # 直接断言经 events 通道
        )
        progress_texts = []
        sink._on_progress = progress_texts.append
        await sink.emit(
            "progress",
            agent_key="bull",
            phase="stage2",
            completed=3,
            total=9,
            percent=33,
            step_text=" Bull 研究员正在发言 ",
        )
        # on_progress 通道传结构化 payload dict（消费方 graph_progress_callback
        # 按 payload.get("percent") 等键读取，对齐 commit 77bece61 计数式进度）
        assert progress_texts == [
            {"completed": 3, "total": 9, "percent": 33, "step_text": " Bull 研究员正在发言 "}
        ]
        # progress 不落库
        await sink.flush()
        assert persisted == []
        # 实时通道仍可见
        assert received and received[-1].event_type == "progress"

    async def test_progress_without_callback_no_error(self):
        sink = EventSink(task_id="t2")
        ev = await sink.emit("progress", text="hi")
        assert ev.event_type == "progress"
