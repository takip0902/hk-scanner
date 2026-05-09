# Scanner v2 升級教學

## 🆕 V2 新功能

1. **覆蓋範圍擴大**：由 200+ 隻擴展到約 1000 隻港股主板（自動 cache）
2. **RS Rating**（相對強度排名 1-99）— 金色 90+ / 綠色 80+ / 灰色 < 70
3. **新股特殊篩選**：上市 < 200 日嘅用 MA10/MA20 + 上市首日高點
4. **入選天數欄**：顯示股票連續入選幾多日
5. **週末 bug 修復**：週六日睇都會繼續顯示週五嘅新增/剔除
6. **成交額門檻調整**：500萬 → **200萬**（多啲中型股入選）
7. **分模式運行**：
   - 平日 17:30 — 快速模式（< 1 分鐘）
   - 每週日上午 — 探索模式（自動發現新股票）

---

## 📤 點上傳到 GitHub

### 方法 A：直接覆蓋（最快，建議）

1. 解壓 `hk-scanner-v2.zip`，會見到 `hk-scanner-v2/` 資料夾
2. 入去 GitHub repo → [https://github.com/takip0902/hk-scanner](https://github.com/takip0902/hk-scanner)
3. 對應每個檔案點擊 → 右上角 ✏️ → 用新內容覆蓋

需要更新嘅檔案：
- ✅ `scanner/scanner.py` — 全新引擎
- ✅ `scanner/tickers.py` — 擴大代碼範圍
- ✅ `requirements.txt` — 加 openpyxl
- ✅ `site/index.html` — 加 RS / 入選天數欄
- ✅ `site/app.js` — 加新邏輯
- ✅ `site/style.css` — 加新樣式
- ✅ `.github/workflows/daily-scan.yml` — 加探索模式
- ✅ `scanner/universe_cache.json` — 新檔案（直接 Add file → Upload file）
- ✅ `site/streaks.json` — 新檔案（同上）

### 方法 B：刪除舊 repo 重新上傳（最徹底，但會丟失 commit history）

1. Settings → 拉到最底 → Delete this repository
2. 重新建立 hk-scanner repo
3. 上傳整個 hk-scanner-v2 資料夾內容（13 個檔/資料夾）
4. 喺網頁建立 `.github/workflows/daily-scan.yml`（用 V2 嘅內容）
5. Settings → Pages → Source 揀 GitHub Actions
6. Settings → Actions → General → Read and write permissions

---

## 🚀 第一次跑探索模式（重要）

V2 第一次跑要先做「探索模式」嚟發現所有有效港股代碼。**呢個會慢啲（10-30 分鐘）**，但只需要做一次。

1. Actions 標籤 → 港股強勢股每日掃描
2. **Run workflow** ▼
3. 揀 `explore = true`
4. 點 Run workflow

之後 GitHub 會：
- 嘗試 5999 個港股代碼範圍
- 自動過濾冇數據嘅
- 建立 `universe_cache.json`
- 之後每次跑都用呢個 cache（< 1 分鐘）

完成後，你個網會見到 **800-1000+ 隻**有實質流動性嘅港股被掃描。

---

## ⚙️ 如果要調整參數

### 改成交額門檻
編輯 `scanner/scanner.py`，搜「`MIN_TURNOVER_M`」：

```python
MIN_TURNOVER_M = 2.0   # 200萬港元，可改 5.0 變回 500萬
```

### 改新股定義（幾多日先算新股）
搜「`NEW_STOCK_DAYS`」：

```python
NEW_STOCK_DAYS = 200   # 上市 < 200 日視為新股
```

### 改 RS Rating 加權
搜 `compute_rs_score`，調整權重數字。

---

## 🎯 之後嘅自動化

✅ **平日 17:30 HKT** — 快速掃描，更新網站
✅ **週日 10:00 AM HKT** — 探索模式，發現新上市股票
✅ **隨時手動** — Actions → Run workflow（可以揀 explore mode）

每次運行都會自動 push 結果到 GitHub，網頁同步更新。
