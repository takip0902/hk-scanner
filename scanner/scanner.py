"""
港股強勢股 Scanner v2

新功能：
  1. 覆蓋範圍擴大到港股主板 (1000+ 隻活躍股)
  2. 加入相對強度排名 (RS Rating, IBD 風格 1-99)
  3. 新股特殊篩選邏輯（上市 < 200 日）
  4. 連續入選天數 (streak counter)
  5. 修正週末顯示 bug — 保留最近一次有變動嘅 baseline

篩選準則（標準）：
  - 收市價 > MA50, MA50 > MA100, MA50 > MA200
  - 20 日平均成交額 > 200 萬港元

新股準則（上市 < 200 日）：
  - 收市價 > MA10, MA10 > MA20
  - 收市價 > 上市首日高點
  - 5 日平均成交額 > 200 萬港元
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tickers import get_all_tickers, HK_TICKERS

SCANNER_DIR = Path(__file__).resolve().parent
ROOT = SCANNER_DIR.parent
SITE_DIR = ROOT / "site"
HISTORY_DIR = SITE_DIR / "history"
SITE_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)

# Universe cache：保存哪些代碼有實質數據（避免每次重新探索）
UNIVERSE_FILE = SCANNER_DIR / "universe_cache.json"

HKT = timezone(timedelta(hours=8))

# 篩選參數
MIN_TURNOVER_M = 2.0          # 平均成交額 200萬港元
MIN_TURNOVER = MIN_TURNOVER_M * 1_000_000
NEW_STOCK_DAYS = 200          # 少於 200 日上市 = 新股
MIN_HISTORY_DAYS = 10         # 至少要有 30 日數據先納入 universe


# ============================================
# 數據抓取
# ============================================

def load_universe_cache() -> set:
    """讀取已知有數據嘅股票代碼 cache"""
    if UNIVERSE_FILE.exists():
        try:
            with open(UNIVERSE_FILE) as f:
                data = json.load(f)
                return set(data.get("tickers", []))
        except Exception:
            pass
    return set()


def save_universe_cache(tickers: set) -> None:
    with open(UNIVERSE_FILE, "w") as f:
        json.dump({
            "updated": datetime.now(HKT).isoformat(),
            "count": len(tickers),
            "tickers": sorted(tickers),
        }, f, ensure_ascii=False, indent=2)


def _download_batch(batch, period, max_retries=3):
    """下載一批股票，包含 retry。返回 (data_dict, valid_set)"""
    for attempt in range(max_retries):
        try:
            data = yf.download(
                tickers=" ".join(batch),
                period=period, interval="1d",
                group_by="ticker", auto_adjust=True,
                progress=False, threads=True,
            )
            result = {}
            valid = set()
            for t in batch:
                try:
                    if t in data.columns.get_level_values(0):
                        df = data[t].dropna()
                        if len(df) >= MIN_HISTORY_DAYS:
                            result[t] = df
                            valid.add(t)
                except Exception:
                    continue
            # 如果成功率太低，可能撞到 rate limit，retry
            success_rate = len(result) / max(len(batch), 1)
            if attempt < max_retries - 1 and success_rate < 0.20:
                wait = 8 * (attempt + 1)
                print(f"    成功率低 ({len(result)}/{len(batch)})，等 {wait}s retry...")
                time.sleep(wait)
                continue
            return result, valid
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 8 * (attempt + 1)
                print(f"    批次失敗 ({e}), 等 {wait}s retry...")
                time.sleep(wait)
            else:
                print(f"    批次最終失敗: {e}")
    return {}, set()


def fetch_data(tickers: list[str], period: str = "1y", explore: bool = False) -> dict:
    """
    分批下載股票數據，帶 retry 邏輯。
    explore=False: 只下載 universe cache 內嘅股票（快速模式）
    explore=True : 下載全部代碼範圍（探索模式，重建 universe）
    """
    universe = load_universe_cache()
    if universe and not explore:
        # 快速模式：universe + 「邊緣探索」（檢查唔喺 universe 嘅範圍嘅 10%）
        in_universe = [t for t in tickers if t in universe]
        not_in_universe = [t for t in tickers if t not in universe]
        # 每次抽樣 not_in_universe 嘅 10%（最多 500 個）
        import random
        sample_size = min(500, max(100, len(not_in_universe) // 10))
        random.seed(int(time.time()) // 86400)  # 每日 seed 唔同
        edge_sample = random.sample(not_in_universe, min(sample_size, len(not_in_universe)))
        target = in_universe + edge_sample
        print(f"快速模式: {len(in_universe)} (universe) + {len(edge_sample)} (邊緣探索) = {len(target)} 隻")
    else:
        target = tickers
        print(f"探索模式: {len(target)} 個代碼範圍")

    result = {}
    new_universe = set(universe)
    batch_size = 50
    total_batches = (len(target) + batch_size - 1) // batch_size

    for i in range(0, len(target), batch_size):
        batch = target[i:i + batch_size]
        batch_num = i // batch_size + 1
        if batch_num % 10 == 1 or batch_num == total_batches:
            print(f"  批次 {batch_num}/{total_batches}: {batch[0]} ~ {batch[-1]}")
        batch_data, batch_valid = _download_batch(batch, period)
        result.update(batch_data)
        new_universe.update(batch_valid)
        time.sleep(0.5)  # 每批之間小延遲

    if explore or len(new_universe) > len(universe):
        save_universe_cache(new_universe)
        print(f"  Universe cache: {len(new_universe)} 隻")

    print(f"成功取得 {len(result)} 隻股票數據")
    return result


# ============================================
# 篩選邏輯
# ============================================

def is_new_stock(df: pd.DataFrame) -> bool:
    """判斷是否新股（上市 < 200 日）"""
    return len(df) < NEW_STOCK_DAYS


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """計算所有需要嘅技術指標"""
    df = df.copy()
    # 標準準則用嘅
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA100"] = df["Close"].rolling(100).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    # 新股準則用嘅
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    # 成交額
    df["Turnover"] = df["Close"] * df["Volume"]
    df["AvgTurnover20"] = df["Turnover"].rolling(20).mean()
    df["AvgTurnover5"] = df["Turnover"].rolling(5).mean()
    return df


def screen_standard(ticker: str, df: pd.DataFrame) -> dict | None:
    """標準準則篩選（上市 ≥ 200 日）"""
    if len(df) < 200:
        return None
    df = compute_indicators(df)
    last = df.iloc[-1]
    close = float(last["Close"])
    ma50 = float(last["MA50"])
    ma100 = float(last["MA100"])
    ma200 = float(last["MA200"])
    avg_turnover = float(last["AvgTurnover20"])

    if not (close > ma50 > ma100 and ma50 > ma200):
        return None
    if avg_turnover < MIN_TURNOVER:
        return None

    return _build_result(ticker, df, close, avg_turnover, "standard",
                        ma50=ma50, ma100=ma100, ma200=ma200)


def screen_new_stock(ticker: str, df: pd.DataFrame) -> dict | None:
    """新股準則篩選（上市 < 200 日）"""
    if len(df) < 20:  # 至少要有 20 日先有 MA20
        return None
    df = compute_indicators(df)
    last = df.iloc[-1]
    close = float(last["Close"])
    ma10 = float(last["MA10"])
    ma20 = float(last["MA20"])
    avg_turnover_5d = float(last["AvgTurnover5"])

    # 上市首日高點
    ipo_high = float(df["High"].iloc[0]) if "High" in df.columns else float(df["Close"].iloc[0])

    if not (close > ma10 > ma20):
        return None
    if close <= ipo_high:
        return None
    if avg_turnover_5d < MIN_TURNOVER:
        return None

    return _build_result(ticker, df, close, avg_turnover_5d, "new",
                        ma10=ma10, ma20=ma20, ipo_high=ipo_high,
                        days_listed=len(df))


def _build_result(ticker, df, close, avg_turnover, category, **extra):
    """建立統一格式嘅篩選結果"""
    high_52w = float(df["Close"].tail(252).max()) if len(df) >= 252 else float(df["Close"].max())
    low_52w = float(df["Close"].tail(252).min()) if len(df) >= 252 else float(df["Close"].min())
    pct_from_high = (close / high_52w - 1) * 100
    pct_5d = (close / float(df["Close"].iloc[-6]) - 1) * 100 if len(df) > 6 else 0
    pct_20d = (close / float(df["Close"].iloc[-21]) - 1) * 100 if len(df) > 21 else 0

    # 距 baseline 強度（標準股用 MA50，新股用 MA10）
    baseline = extra.get("ma50") or extra.get("ma10") or close
    above_baseline_pct = (close / baseline - 1) * 100

    result = {
        "ticker": ticker,
        "code": ticker.replace(".HK", ""),
        "category": category,
        "close": round(close, 3),
        "above_ma50_pct": round(above_baseline_pct, 2),  # 共用欄位 (新股實際係距 MA10)
        "pct_5d": round(pct_5d, 2),
        "pct_20d": round(pct_20d, 2),
        "pct_from_52w_high": round(pct_from_high, 2),
        "pct_from_52w_low": round((close / low_52w - 1) * 100, 2),
        "avg_turnover_m": round(avg_turnover / 1_000_000, 2),
        "last_date": df.index[-1].strftime("%Y-%m-%d"),
    }
    # 標準股欄位
    if "ma50" in extra:
        result["ma50"] = round(extra["ma50"], 3)
        result["ma100"] = round(extra["ma100"], 3)
        result["ma200"] = round(extra["ma200"], 3)
    # 新股欄位
    if "ma10" in extra:
        result["ma10"] = round(extra["ma10"], 3)
        result["ma20"] = round(extra["ma20"], 3)
        result["ipo_high"] = round(extra["ipo_high"], 3)
        result["days_listed"] = extra["days_listed"]
        # 為咗顯示一致，新股嘅 ma50/100/200 設為 ma10/20 等價
        result["ma50"] = round(extra["ma10"], 3)
        result["ma100"] = round(extra["ma20"], 3)
        result["ma200"] = round(extra["ma20"], 3)
    return result


def apply_metadata(stocks: list, meta: dict) -> list:
    """為每隻通過篩選嘅股票套用 metadata，並過濾市值 < 80 億嘅。
    冇 metadata 嘅股票會留低（不過濾），等下次 fetch 補返。"""
    filtered = []
    for s in stocks:
        m = meta.get(s["ticker"], {})
        market_cap = m.get("market_cap", 0)
        # 只有當有真實市值資料時，先過濾
        if market_cap > 0 and market_cap < MIN_MARKET_CAP:
            continue
        # 套用名稱（如果 metadata 有；否則保持已有 fallback name）
        if m.get("name"):
            s["name"] = m["name"]
        s["market_cap"] = market_cap
        s["market_cap_b"] = round(market_cap / 1e9, 2) if market_cap else 0
        s["sector"] = m.get("sector", "")
        filtered.append(s)
    return filtered


def screen_stock(ticker: str, df: pd.DataFrame) -> dict | None:
    """根據股票上市時長分流到對應篩選邏輯"""
    if is_new_stock(df):
        return screen_new_stock(ticker, df)
    return screen_standard(ticker, df)


# ============================================
# 相對強度排名 (RS Rating)
# ============================================

def compute_rs_score(df: pd.DataFrame) -> float:
    """
    計算單一股票嘅相對強度分數（IBD 風格加權）
    新股可能冇 6 個月數據，動態調整權重
    """
    if len(df) < 21:
        return 0.0

    close = float(df["Close"].iloc[-1])
    components = []

    # 1 週 (5 trading days)
    if len(df) > 6:
        ret_1w = close / float(df["Close"].iloc[-6]) - 1
        components.append((ret_1w, 0.20))

    # 1 月 (21 trading days)
    if len(df) > 22:
        ret_1m = close / float(df["Close"].iloc[-22]) - 1
        components.append((ret_1m, 0.20))

    # 3 月 (63 trading days)
    if len(df) > 64:
        ret_3m = close / float(df["Close"].iloc[-64]) - 1
        components.append((ret_3m, 0.20))

    # 6 月 (126 trading days)
    if len(df) > 127:
        ret_6m = close / float(df["Close"].iloc[-127]) - 1
        components.append((ret_6m, 0.40))

    if not components:
        return 0.0

    # 重新調整權重 (歸一化)
    total_weight = sum(w for _, w in components)
    score = sum(r * w for r, w in components) / total_weight
    return score


def assign_rs_ratings(stocks: list[dict], data: dict) -> None:
    """
    為所有強勢股計算 RS 分數，並轉換成 1-99 嘅百分位排名。
    Note: 排名要考慮全 universe（連冇通過篩選嘅都計），
          先至有客觀嘅相對強度。
    """
    if not stocks:
        return

    # 計算全 universe 嘅 RS 分數
    all_scores = []
    for ticker, df in data.items():
        score = compute_rs_score(df)
        all_scores.append((ticker, score))

    # 排序
    all_scores.sort(key=lambda x: x[1])
    ticker_to_rank = {}
    n = len(all_scores)
    for i, (ticker, score) in enumerate(all_scores):
        # 百分位：1-99
        percentile = max(1, min(99, int((i + 1) / n * 99) + 1))
        ticker_to_rank[ticker] = percentile

    # 套用到強勢股
    for s in stocks:
        s["rs_rating"] = ticker_to_rank.get(s["ticker"], 0)



# ============================================
# Metadata (名稱 + 市值)
# ============================================

METADATA_FILE = SCANNER_DIR / "metadata.json"
MIN_MARKET_CAP = 8_000_000_000  # 80 億港元


def load_metadata() -> dict:
    """載入股票名稱+市值 cache"""
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_metadata(meta: dict) -> None:
    with open(METADATA_FILE, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def fetch_stock_info(ticker: str) -> dict | None:
    """
    取得單一股票嘅名稱、市值、行業。
    失敗返回 None（會 fallback 到舊 cache 或 names.json）。
    """
    try:
        info = yf.Ticker(ticker).info
        name = info.get("longName") or info.get("shortName") or ""
        # 處理 yfinance 返回嘅英文名 → 試下 names.json 入面有冇中文
        market_cap = info.get("marketCap") or 0
        sector = info.get("sector", "")
        return {
            "name_en": name,
            "market_cap": int(market_cap) if market_cap else 0,
            "sector": sector,
        }
    except Exception:
        return None


def update_metadata(tickers: list, force_refresh: bool = False) -> dict:
    """
    更新 metadata cache（增量）。每運行一次補多啲。
    對冇 cache 嘅股票嘗試 fetch info；fetch 失敗會喺下次運行重試。
    """
    meta = load_metadata()
    chinese_names = load_company_names()
    fetched = 0
    failed = 0
    skipped = 0

    # 限制每次最多 fetch 50 隻冇 cache 嘅，避免 rate limit
    MAX_FETCH_PER_RUN = 50
    fetch_count = 0

    for ticker in tickers:
        code = ticker.replace(".HK", "")
        # 已有 cache 而且有市值 → 跳過
        if not force_refresh and ticker in meta and meta[ticker].get("market_cap", 0) > 0:
            skipped += 1
            continue

        if fetch_count >= MAX_FETCH_PER_RUN:
            break

        info = fetch_stock_info(ticker)
        fetch_count += 1
        if info and (info.get("name_en") or info.get("market_cap", 0) > 0):
            chinese = chinese_names.get(code, "")
            info["name"] = chinese if chinese else info.get("name_en", code)
            meta[ticker] = info
            fetched += 1
            if fetched % 10 == 0:
                save_metadata(meta)  # 中途 save 防止失敗失去進度
        else:
            failed += 1
        # 較長延遲避免 rate limit
        time.sleep(0.3)

    save_metadata(meta)
    print(f"  Metadata: {fetched} 新增, {failed} 失敗, {skipped} 用 cache, 總共 {len(meta)} 隻")
    return meta


# ============================================
# Streak 計算（連續入選天數）
# ============================================

STREAKS_FILE = SITE_DIR / "streaks.json"


def load_streaks() -> dict:
    if STREAKS_FILE.exists():
        try:
            with open(STREAKS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_streaks(streaks: dict) -> None:
    with open(STREAKS_FILE, "w") as f:
        json.dump(streaks, f, ensure_ascii=False, indent=2)


def update_streaks(current_codes: set, prev_codes: set) -> dict:
    """
    更新 streak counter。
      - 仲喺榜 → +1
      - 新加入 → 1
      - 剔除 → 移除（下次入選時由 1 重新開始）
    """
    streaks = load_streaks()
    new_streaks = {}

    for code in current_codes:
        if code in streaks and code in prev_codes:
            new_streaks[code] = streaks[code] + 1
        else:
            # 新加入或重新加入
            new_streaks[code] = 1

    save_streaks(new_streaks)
    return new_streaks


# ============================================
# 對比邏輯（修正週末顯示 bug）
# ============================================

def find_previous_baseline() -> dict | None:
    """
    搵最近一次「不同日期」嘅快照做 baseline。
    呢個係修正週末顯示 bug 嘅關鍵。
    """
    today_str = datetime.now(HKT).strftime("%Y-%m-%d")
    snapshots = sorted(HISTORY_DIR.glob("*.json"), reverse=True)

    for snap in snapshots:
        try:
            with open(snap) as f:
                data = json.load(f)
            scan_date = data.get("scan_date")
            # 揾不同日期嘅最近快照
            if scan_date and scan_date != today_str:
                # 但要確保嗰次有 stocks（避免抓到失敗嘅快照）
                if data.get("stocks"):
                    return data
        except Exception:
            continue
    return None


def load_company_names() -> dict:
    names_file = SCANNER_DIR / "names.json"
    if names_file.exists():
        with open(names_file) as f:
            return json.load(f)
    return {}


# ============================================
# 主函數
# ============================================

def run_scan(explore: bool = False) -> dict:
    today = datetime.now(HKT).strftime("%Y-%m-%d")
    print(f"\n{'=' * 60}")
    print(f"港股強勢股 Scanner v2 - {today}")
    print(f"{'=' * 60}")

    tickers = get_all_tickers()
    data = fetch_data(tickers, explore=explore)

    print(f"\n開始篩選...")
    results = []
    for ticker, df in data.items():
        try:
            r = screen_stock(ticker, df)
            if r:
                results.append(r)
        except Exception as e:
            pass  # 靜默跳過個別錯誤

    print(f"符合準則的強勢股: {len(results)} 隻")
    print(f"  其中標準股: {sum(1 for r in results if r['category'] == 'standard')}")
    print(f"  其中新股  : {sum(1 for r in results if r['category'] == 'new')}")

    # 先設定預設 name（fallback 防止 KeyError）
    chinese_names = load_company_names()
    for r in results:
        r["name"] = chinese_names.get(r["code"], r["code"])
        r["market_cap"] = 0
        r["market_cap_b"] = 0
        r["sector"] = ""

    # 取得 metadata (名稱 + 市值) - 容錯處理
    print("更新 metadata...")
    qualified_tickers = [r["ticker"] for r in results]
    try:
        meta = update_metadata(qualified_tickers)
    except Exception as e:
        print(f"  Metadata 更新失敗: {e}, 使用 cache + 中文名")
        meta = load_metadata()

    # 套用 metadata + 市值過濾（容錯：冇 metadata 嘅留低）
    before_count = len(results)
    results = apply_metadata(results, meta)
    print(f"市值過濾: {before_count} → {len(results)} (有市值資料嘅剔除 < 80 億)")

    # 計算 RS Rating（只計留低嘅）
    print("計算相對強度排名...")
    assign_rs_ratings(results, data)

    # 對比前一日（用 baseline finder 修正週末 bug）
    prev = find_previous_baseline()
    prev_codes = set()
    prev_date = None
    prev_stocks = []
    if prev:
        prev_stocks = prev.get("stocks", [])
        prev_codes = {s["code"] for s in prev_stocks}
        prev_date = prev.get("scan_date")
        print(f"對比 baseline: {prev_date} ({len(prev_codes)} 隻)")

    current_codes = {r["code"] for r in results}
    new_codes = current_codes - prev_codes
    removed_codes = prev_codes - current_codes
    kept_codes = current_codes & prev_codes

    removed_stocks = [s for s in prev_stocks if s["code"] in removed_codes]

    # Streak 更新
    streaks = update_streaks(current_codes, prev_codes)
    for r in results:
        r["streak"] = streaks.get(r["code"], 1)
        r["is_new"] = r["code"] in new_codes

    # 排序：先按 RS Rating，相同 RS 再按 above_ma50_pct
    results.sort(key=lambda x: (x.get("rs_rating", 0), x.get("above_ma50_pct", 0)), reverse=True)

    output = {
        "scan_date": today,
        "scan_timestamp": datetime.now(HKT).isoformat(),
        "previous_date": prev_date,
        "total_universe": len(HK_TICKERS),
        "data_available": len(data),
        "total_qualified": len(results),
        "new_count": len(new_codes),
        "removed_count": len(removed_codes),
        "kept_count": len(kept_codes),
        "stocks": results,
        "removed_stocks": removed_stocks,
    }

    # 寫入結果
    with open(SITE_DIR / "data.json", "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(SITE_DIR / "data.js", "w") as f:
        f.write("window.SCANNER_DATA = ")
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    snapshot_file = HISTORY_DIR / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n結果摘要:")
    print(f"  符合準則: {len(results)} 隻")
    print(f"  新加入  : {len(new_codes)}")
    print(f"  剔除    : {len(removed_codes)}")
    print(f"  保持    : {len(kept_codes)}")
    if results:
        top = results[:5]
        print(f"\nTop 5 (按 RS Rating):")
        for r in top:
            print(f"  {r['code']:6s} {r['name']:20s} RS={r.get('rs_rating', '?')}  "
                  f"距均線 {r['above_ma50_pct']:+.2f}%  streak={r['streak']}日")

    return output


if __name__ == "__main__":
    # 用法：
    #   python scanner.py            # 快速模式（用 universe cache）
    #   python scanner.py --explore  # 探索模式（重建 universe）
    explore = "--explore" in sys.argv
    run_scan(explore=explore)
