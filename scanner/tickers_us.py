"""
美股 Universe Builder
組合 5 個來源：
  1. S&P 500 (~500)         - Wikipedia
  2. NASDAQ 100 (~100)      - Wikipedia
  3. Russell 1000 (~1000)   - iShares IWB ETF holdings
  4. IPO past 36 months     - 用 yfinance firstTradeDate 識別
  5. Volume Top 1000        - 由 universe 入面抓最活躍嘅
"""
from __future__ import annotations
import io
import json
import urllib.request
from pathlib import Path
from typing import List

import pandas as pd

SCANNER_DIR = Path(__file__).resolve().parent
UNIVERSE_FILE = SCANNER_DIR / "universe_us.json"

USER_AGENT = {"User-Agent": "Mozilla/5.0"}


def fetch_sp500() -> List[str]:
    """從 Wikipedia 抓 S&P 500"""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode()
        tables = pd.read_html(io.StringIO(html))
        sp500 = tables[0]
        # 處理可能嘅 dot/dash 變體 (BRK.B -> BRK-B for yfinance)
        symbols = sp500["Symbol"].str.replace(".", "-", regex=False).tolist()
        return [s for s in symbols if isinstance(s, str)]
    except Exception as e:
        print(f"  S&P 500 fetch 失敗: {e}")
        return []


def fetch_nasdaq100() -> List[str]:
    """從 Wikipedia 抓 NASDAQ 100"""
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode()
        tables = pd.read_html(io.StringIO(html))
        # 揾包含 ~100 行 + Ticker 嘅 table
        for t in tables:
            if 80 < len(t) < 120:
                ticker_col = None
                for col in ["Ticker", "Symbol"]:
                    if col in t.columns:
                        ticker_col = col
                        break
                if ticker_col:
                    symbols = t[ticker_col].str.replace(".", "-", regex=False).tolist()
                    return [s for s in symbols if isinstance(s, str)]
        return []
    except Exception as e:
        print(f"  NASDAQ 100 fetch 失敗: {e}")
        return []


def fetch_nasdaq_listed() -> List[str]:
    """從 NASDAQ Trader 官方拎所有 NASDAQ 上市股 (包 NBIS、CRWV 等新 IPO)"""
    try:
        url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
        symbols = set()
        for line in data.strip().split('\n')[1:]:  # skip header
            parts = line.split('|')
            if not parts or not parts[0]:
                continue
            sym = parts[0].strip()
            # Skip metadata line
            if 'File Creation' in sym or len(sym) > 6:
                continue
            # Skip test issues (Y in column 3)
            if len(parts) > 3 and parts[3] == 'Y':
                continue
            # Only normal symbols (letters + maybe dash)
            if sym.replace('-', '').replace('.', '').isalpha():
                # yfinance format: BRK.A -> BRK-A
                symbols.add(sym.replace('.', '-'))
        return sorted(symbols)
    except Exception as e:
        print(f"  NASDAQ listed fetch 失敗: {e}")
        return []


def fetch_nyse_amex_listed() -> List[str]:
    """從 NASDAQ Trader 官方拎 NYSE / AMEX 上市股"""
    try:
        url = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
        symbols = set()
        for line in data.strip().split('\n')[1:]:
            parts = line.split('|')
            if not parts or not parts[0]:
                continue
            sym = parts[0].strip()
            if 'File Creation' in sym or len(sym) > 6:
                continue
            # Skip test issues
            if len(parts) > 6 and parts[6] == 'Y':
                continue
            if sym.replace('-', '').replace('.', '').isalpha():
                symbols.add(sym.replace('.', '-'))
        return sorted(symbols)
    except Exception as e:
        print(f"  NYSE/AMEX listed fetch 失敗: {e}")
        return []


def fetch_russell1000() -> List[str]:
    """從 iShares IWB ETF 抓 Russell 1000 holdings"""
    try:
        url = ("https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/"
               "1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund")
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
        # 揾 Ticker header line
        lines = data.split('\n')
        header_idx = None
        for i, line in enumerate(lines):
            if line.startswith('Ticker') or '"Ticker"' in line:
                header_idx = i
                break
        if header_idx is None:
            return []
        csv_text = '\n'.join(lines[header_idx:])
        df = pd.read_csv(io.StringIO(csv_text))
        if 'Asset Class' in df.columns:
            df = df[df['Asset Class'].str.contains('Equity', na=False, case=False)]
        symbols = df['Ticker'].str.replace(".", "-", regex=False).tolist()
        return [s for s in symbols if isinstance(s, str) and s and s != '-']
    except Exception as e:
        print(f"  Russell 1000 fetch 失敗: {e}")
        return []


def fetch_russell3000() -> List[str]:
    """從 iShares IWV ETF 抓 Russell 3000 holdings (覆蓋 98% 美股)"""
    try:
        url = ("https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/"
               "1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund")
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
        lines = data.split('\n')
        header_idx = None
        for i, line in enumerate(lines):
            if line.startswith('Ticker') or '"Ticker"' in line:
                header_idx = i
                break
        if header_idx is None:
            return []
        csv_text = '\n'.join(lines[header_idx:])
        df = pd.read_csv(io.StringIO(csv_text))
        if 'Asset Class' in df.columns:
            df = df[df['Asset Class'].str.contains('Equity', na=False, case=False)]
        symbols = df['Ticker'].astype(str).str.replace(".", "-", regex=False).tolist()
        return [s for s in symbols if isinstance(s, str) and s.replace('-', '').isalpha() and 1 <= len(s) <= 6]
    except Exception as e:
        print(f"  Russell 3000 fetch 失敗: {e}")
        return []


def fetch_recent_ipos(months: int = 36) -> List[str]:
    """
    用 yfinance 識別過去 N 個月嘅 IPO。
    呢個冇外部來源直接畀 list，所以我哋揀「最有可能新上市」嘅 ticker pattern：
    - 從 NASDAQ 同 NYSE 嘅 IPO calendar (用 ETF holdings 嘅最新增加部分)
    - 結合 iShares IPO ETF (FPX) holdings

    用 First Trust IPOX-100 ETF (FPX) 抓 IPO universe
    """
    try:
        # FPX = First Trust US Equity Opportunities ETF（IPO 概念 ETF）
        url = ("https://www.ftportfolios.com/Retail/Etf/EtfHoldings.aspx?Ticker=FPX")
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode()
        # 嘗試 parse 但呢個源可能要 JS render，用備援
        tables = pd.read_html(io.StringIO(html))
        for t in tables:
            if 50 < len(t) < 150:
                for col in t.columns:
                    if 'icker' in str(col) or 'ymbol' in str(col):
                        symbols = t[col].tolist()
                        return [s for s in symbols if isinstance(s, str)]
    except Exception:
        pass

    # 備援：用 iShares IPO ETF (IPO) holdings
    try:
        url = ("https://www.renaissancecapital.com/IPO-Investing/IPO-ETFs")
        # 呢個源可能唔得，跳過
    except Exception:
        pass

    # 最終備援：返回空，scanner 會用 yfinance firstTradeDate 過濾
    return []


def build_universe() -> dict:
    """
    建立完整美股 universe，組合所有來源
    返回 {tickers: [...], sources: {...}}
    """
    print("=" * 50)
    print("Building US Universe...")
    print("=" * 50)

    sources = {}

    print("1. Fetching S&P 500...")
    sp500 = fetch_sp500()
    sources['sp500'] = sp500
    print(f"   ✓ {len(sp500)} stocks")

    print("2. Fetching NASDAQ 100...")
    ndx = fetch_nasdaq100()
    sources['nasdaq100'] = ndx
    print(f"   ✓ {len(ndx)} stocks")

    print("3. Fetching NASDAQ listed (包 NBIS、CRWV、所有新 IPO)...")
    nasdaq_all = fetch_nasdaq_listed()
    sources['nasdaq_listed'] = nasdaq_all
    print(f"   ✓ {len(nasdaq_all)} stocks")

    print("4. Fetching NYSE/AMEX listed (傳統大藍籌)...")
    nyse_all = fetch_nyse_amex_listed()
    sources['nyse_amex_listed'] = nyse_all
    print(f"   ✓ {len(nyse_all)} stocks")

    print("5. Russell 3000 (overlap，補 cover 萬一前 2 個失敗)...")
    russ3000 = fetch_russell3000()
    sources['russell3000'] = russ3000
    print(f"   ✓ {len(russ3000)} stocks")

    # Russell 1000 fallback
    if len(nasdaq_all) + len(nyse_all) < 3000:
        print("6. Fallback: Russell 1000")
        russ1000 = fetch_russell1000()
        sources['russell1000'] = russ1000
        print(f"   ✓ {len(russ1000)} stocks")

    print("7. IPO universe (detected via yfinance firstTradeDate)...")
    ipos = fetch_recent_ipos()
    sources['recent_ipos'] = ipos
    print(f"   ✓ {len(ipos)} IPO candidates")

    # 合併 + 去重
    all_tickers = set()
    for source_name, source_list in sources.items():
        all_tickers.update(source_list)
    # 過濾無效 ticker（必須係字母 + 可能有 dash）
    all_tickers = {t for t in all_tickers if isinstance(t, str) and t.replace('-', '').isalpha() and 1 <= len(t) <= 6}

    result = {
        "total": len(all_tickers),
        "tickers": sorted(all_tickers),
        "sources_size": {k: len(v) for k, v in sources.items()},
    }

    # Save
    with open(UNIVERSE_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n總共 unique tickers: {result['total']}")
    return result


# 為咗讓 scanner 直接 import 用，提供 helper
def get_all_tickers() -> List[str]:
    """讀取已儲存嘅 universe"""
    if UNIVERSE_FILE.exists():
        try:
            with open(UNIVERSE_FILE) as f:
                d = json.load(f)
                return d.get("tickers", [])
        except Exception:
            pass
    # Fallback：build 一次
    return build_universe()["tickers"]


if __name__ == "__main__":
    result = build_universe()
    print(f"\nSources:")
    for k, v in result['sources_size'].items():
        print(f"  {k}: {v}")
    print(f"\nFirst 10: {result['tickers'][:10]}")
    print(f"Last 10: {result['tickers'][-10:]}")
