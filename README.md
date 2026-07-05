## 本次改動摘要

### 1. 外部詞彙資料庫 `vocab_db.json`

新增一個獨立的 JSON 檔案作為持久化詞庫，結構如下：

```json
{
  "version": "1.0",
  "vocab": {
    "Entwicklung": { "zh": "發展", "en": "development", "lemma": "die Entwicklung" }
  }
}
```

每當 LLM 結果被解析後，新詞條會自動寫入此檔案，跨 session 永久保留。

---

### 2. 本地伺服器 `server.py`

由於瀏覽器的安全限制，純 HTML 檔案無法直接讀寫本地檔案。因此改為以 Python 啟動一個 localhost 伺服器，提供兩個功能：

- **靜態檔案服務**：提供 `index.html` 等頁面
- **API 端點**：
  - `GET /api/db` — 讀取詞庫
  - `POST /api/db` — 合併新詞條寫入詞庫

---

### 3. 三種翻譯模式（`index.html`）

在底部工具列新增了模式切換按鈕：

| 模式 | 行為 |
|---|---|
| **LLM** | 原有流程不變——所有篩選後的 token 全數複製為提示詞，LLM 結果解析後同步更新詞庫 |
| **混合** | 詞庫中已有的詞條直接顯示；尚未收錄的才匯出至提示詞交由 LLM 處理，結果回傳後兩者合併顯示 |
| **本地** | 僅查閱詞庫，完全不涉及 LLM，無複製提示詞步驟，LLM 輸入欄也會自動隱藏 |

---

### 4. 快速啟動腳本 `~/Desktop/FugaVocabs.command`

桌面上新增一個可雙擊執行的 `.command` 程式：

1. 終止舊有的同埠程序（如已在運行）
2. 啟動 `server.py`
3. 等待伺服器就緒後，自動以預設瀏覽器開啟 `http://localhost:8765`
4. 關閉視窗即停止伺服器

---

### 5. Tolino 詞典轉換腳本 `build_quickdic.py`

將 `vocab_db.json` 轉換為 Tolino Vision Color 原生支援的 **QuickDic v6** 格式（`.quickdic`）：

- 使用 `pyglossary` 函式庫處理格式轉換
- 因 macOS 26 的 Homebrew 尚不相容，改透過 **Anaconda（conda-forge）** 安裝所需的 `pyicu`（Unicode 字元排序函式庫）
- 每次詞庫有更新後重新執行此腳本即可，USB 傳至 Tolino 即可使用

使用方式：
build_quickdic.py 的 shebang 行已指定直接使用 Anaconda 的 Python，因此最簡單的方式是：

方法一：直接執行（推薦）

`/opt/anaconda3/bin/python /Users/ayano/Documents/MyApp/fugaD/build_quickdic.py`
方法二：因為已 chmod +x，可直接呼叫

`/Users/ayano/Documents/MyApp/fugaD/build_quickdic.py`

系統的 python3（`/usr/bin/python3`）不可用，因為 pyicu 只裝在 Anaconda 環境裡，缺少它會報錯。