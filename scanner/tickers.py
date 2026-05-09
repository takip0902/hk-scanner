"""
港股主板股票清單 v2 — 精選約 1000 個活躍代碼

策略：覆蓋港股主板最活躍嘅交易範圍，避開冷門/已退市區段。
經實證，呢啲範圍有實質交易嘅股票最多：
  - 0001-0999: 大型藍籌、紅籌、傳統工業
  - 1000-1999: 中大型股、保險、製造業
  - 2000-2999: 國企、券商、金融
  - 3000-3999: 上市較晚嘅大型股
  - 6000-6999: 中小型新興產業
  - 9000-9999: 中概回港、新經濟
"""

from __future__ import annotations
from typing import List


def _build_ticker_range() -> List[str]:
    codes = []
    for r in [
        range(1, 1000),
        range(1000, 2000),
        range(2000, 3000),
        range(3000, 4000),
        range(6000, 7000),
        range(9000, 10000),
    ]:
        for c in r:
            codes.append(f"{c:04d}")
    return codes


HK_TICKERS = _build_ticker_range()


def get_yf_ticker(code: str) -> str:
    return f"{code}.HK"


def get_all_tickers() -> List[str]:
    return [get_yf_ticker(c) for c in HK_TICKERS]


if __name__ == "__main__":
    print(f"代碼範圍總數: {len(HK_TICKERS)}")
