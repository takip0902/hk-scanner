"""
獨立嘅 metadata fetcher script。
一次過 fetch universe cache 入面所有股票嘅名稱 + 市值。
分批 fetch，每隻 0.4 秒延遲，預計 1500 隻需要 10-15 分鐘。
"""
import json
import sys
import time
from pathlib import Path

import yfinance as yf

SCANNER_DIR = Path(__file__).resolve().parent
ROOT = SCANNER_DIR.parent
UNIVERSE_FILE = SCANNER_DIR / "universe_cache.json"
METADATA_FILE = SCANNER_DIR / "metadata.json"
NAMES_FILE = SCANNER_DIR / "names.json"


def load_json(path: Path, default):
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 60)
    print("Metadata Bulk Fetcher")
    print("=" * 60)

    universe = load_json(UNIVERSE_FILE, {})
    tickers = universe.get("tickers", [])
    print(f"Universe: {len(tickers)} 隻")

    metadata = load_json(METADATA_FILE, {})
    print(f"已有 metadata: {len(metadata)} 隻")

    chinese_names = load_json(NAMES_FILE, {})
    print(f"中文名清單: {len(chinese_names)} 隻\n")

    # 揾出仲冇 metadata 嘅
    todo = [t for t in tickers if t not in metadata or not metadata[t].get("market_cap", 0)]
    print(f"需要 fetch: {len(todo)} 隻")
    print(f"預計時間: {len(todo) * 0.4 / 60:.1f} 分鐘\n")

    fetched = 0
    failed = 0
    start = time.time()

    for i, ticker in enumerate(todo):
        code = ticker.replace(".HK", "")
        try:
            info = yf.Ticker(ticker).info
            name_en = info.get("longName") or info.get("shortName") or ""
            market_cap = info.get("marketCap") or 0
            sector = info.get("sector", "")

            if name_en or market_cap:
                chinese = chinese_names.get(code, "")
                metadata[ticker] = {
                    "name_en": name_en,
                    "name": chinese if chinese else name_en if name_en else code,
                    "market_cap": int(market_cap) if market_cap else 0,
                    "sector": sector,
                }
                fetched += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1

        # 進度報告
        if (i + 1) % 50 == 0 or (i + 1) == len(todo):
            elapsed = time.time() - start
            eta = (len(todo) - i - 1) * (elapsed / (i + 1)) if i > 0 else 0
            print(f"  進度: {i + 1}/{len(todo)} | 成功 {fetched} | 失敗 {failed} | "
                  f"已用 {elapsed/60:.1f}分 | 剩 {eta/60:.1f}分")
            save_json(METADATA_FILE, metadata)  # 中途 save

        time.sleep(0.4)

    save_json(METADATA_FILE, metadata)
    print(f"\n完成！")
    print(f"  總共 metadata: {len(metadata)} 隻")
    print(f"  本次新增: {fetched} 隻")
    print(f"  失敗: {failed} 隻")


if __name__ == "__main__":
    main()
