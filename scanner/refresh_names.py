"""
從 HKEX 官方下載最新中文名清單，並更新：
  1. scanner/names.json 加入所有官方中文名
  2. scanner/metadata.json 用新中文名覆寫所有 stock 嘅 name 欄位

呢個腳本只需要跑一次（或者偶爾更新 HKEX 名單時跑）。
"""
import urllib.request
import io
import json
from pathlib import Path

import openpyxl

SCANNER_DIR = Path(__file__).resolve().parent
NAMES_FILE = SCANNER_DIR / "names.json"
METADATA_FILE = SCANNER_DIR / "metadata.json"

HKEX_URL = "https://www.hkex.com.hk/chi/services/trading/securities/securitieslists/ListOfSecurities_c.xlsx"


def fetch_hkex_names() -> dict:
    """從 HKEX 官方 xlsx 下載並解析所有主板上市公司中文名"""
    print(f"從 HKEX 下載官方上市公司清單...")
    req = urllib.request.Request(HKEX_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f"下載完成: {len(data) / 1024:.0f} KB")

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=False)
    ws = wb.active

    names = {}
    for row in ws.iter_rows(values_only=True):
        if not row or len(row) < 4:
            continue
        code = str(row[0]).strip() if row[0] else ""
        name = str(row[1]).strip() if row[1] else ""
        type_ = str(row[3]).strip() if row[3] else ""

        if not code.isdigit() or len(code) > 5:
            continue
        code_int = int(code)
        if code_int < 1 or code_int > 9999:
            continue
        if "主板" not in type_ or "股本" not in type_:
            continue
        if not name:
            continue

        formatted = f"{code_int:04d}"
        names[formatted] = name

    return names


def main():
    print("=" * 60)
    print("Refresh Names - 從 HKEX 同步中文名")
    print("=" * 60)

    # 1. 從 HKEX 下載
    new_names = fetch_hkex_names()
    print(f"HKEX 取得: {len(new_names)} 隻主板股本證券中文名\n")

    # 2. 合併 names.json（HKEX 為主，原有特殊名保留）
    if NAMES_FILE.exists():
        with open(NAMES_FILE) as f:
            old_names = json.load(f)
    else:
        old_names = {}

    merged = dict(old_names)
    merged.update(new_names)  # HKEX 為主
    with open(NAMES_FILE, "w") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"names.json 更新: {len(old_names)} → {len(merged)}")

    # 3. 用新名稱覆寫 metadata.json
    if METADATA_FILE.exists():
        with open(METADATA_FILE) as f:
            metadata = json.load(f)

        updated = 0
        for ticker, info in metadata.items():
            code = ticker.replace(".HK", "")
            chinese = merged.get(code, "")
            if chinese and info.get("name") != chinese:
                info["name"] = chinese
                updated += 1
            elif not chinese and not info.get("name"):
                info["name"] = code  # fallback 用 code

        with open(METADATA_FILE, "w") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"metadata.json: {updated} 隻名稱已用 HKEX 中文名覆寫")
    else:
        print("metadata.json 唔存在，跳過")

    print("\n完成！")


if __name__ == "__main__":
    main()
