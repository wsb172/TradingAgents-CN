"""
Tushare 股票基础信息 API

调用模板收敛在 app/data/sources/tushare_common/caller.py。
"""
import logging
from typing import Any, Dict, Optional

import pandas as pd

from app.data.sources.tushare_common.caller import call_tushare

from .connection import TushareConnection

logger = logging.getLogger(__name__)

_DOMAIN = "stock_basic"
_SOURCE = "tushare"

_STOCK_BASIC_FIELDS = (
    "ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs"
)


async def fetch_stock_list(conn: TushareConnection, market: str = None) -> Optional[pd.DataFrame]:
    """获取 A 股股票列表（沪深 + 北交所）。

    北交所（BSE/BJ）必须纳入：basic_info 是覆盖率的分母与逐股同步的
    股票池，缺它会导致 920xxx 全市场无基础信息、无行情。
    tushare stock_basic 的 exchange 过滤对 BJ 需单独传值，故分两次
    拉取后合并；北交所拉取失败不阻塞沪深主列表。
    """
    params: Dict[str, Any] = {"list_status": "L", "fields": _STOCK_BASIC_FIELDS}
    if market == "CN":
        params["exchange"] = "SSE,SZSE"

    main_df = await call_tushare(conn, "stock_basic", _SOURCE, _DOMAIN, **params)

    if market != "CN":
        return main_df

    try:
        bj_df = await call_tushare(
            conn, "stock_basic", _SOURCE, _DOMAIN,
            **{"list_status": "L", "exchange": "BSE", "fields": _STOCK_BASIC_FIELDS},
        )
    except Exception as e:
        logger.warning(f"拉取北交所股票列表失败（仅影响 BSE 覆盖）: {e}")
        return main_df

    if bj_df is None or bj_df.empty:
        return main_df
    if main_df is None or main_df.empty:
        return bj_df
    return pd.concat([main_df, bj_df], ignore_index=True)


async def fetch_stock_basic_info(
    conn: TushareConnection, ts_code: str
) -> Optional[pd.DataFrame]:
    """获取单只股票基础信息"""
    # 港股基础信息已独立为 tushare_hk 源（独立 Token/积分），CN 源不再处理 .HK 代码
    return await call_tushare(
        conn,
        "stock_basic",
        _SOURCE,
        _DOMAIN,
        f"ts_code={ts_code}",
        ts_code=ts_code,
        fields=_STOCK_BASIC_FIELDS + ",act_name,act_ent_type",
    )
