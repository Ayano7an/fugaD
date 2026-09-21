# Fuga 26 Nördlingen

德語閱讀詞彙工具：貼上原文 → 分詞 → 查詞庫或呼叫本地 LLM 註釋 → 追蹤詞頻、以反應時間排閃卡 → 匯出成電子閱讀器詞典。附一個瀏覽器選詞擴展。

> **產品名** `Fuga`，搭配「年份 + 地名」版本號：`Fuga <西元年後兩位> <地名>`。
> 視窗標題列、首頁大標與跑馬燈一律用產品名。
>
> **題詞** *Introduction et rondo capriccioso*（Saint-Saëns, Op. 28），置於頁面底部，
> 並在該處寫明兩重隱喻——引子與回旋、以及賦格——的由來。

### 名字的兩重意思

**引子與回旋。** 本程式是引子，不是全程。初識生詞時它省下翻查的工夫，但日常所讀多半無從數位化；真把詞握在手裡靠的是往後一次次重逢。回旋曲的疊句去而復返，`capriccioso` 說它任性——何時回來不由日程表決定，只看那天讀到什麼。這也是本程式與制式複習軟體的分別：詞頻是所讀過內容的自然統計，而非人為設置的背單詞排程表。

**賦格。** `fuga` 是拉丁語的「逃」。記憶會逃：背了忘、忘了背，記得過去式卻想不起原形；聲部彼此追逐，而人跟在後頭。但賦格的主題經過倒影、增值、移調仍舊是那個主題——`laufen`／`läuft`／`lief`／`gelaufen` 亦然。於是賦格說的不只是逃逸，還有在萬變之中認出同一個東西。

**Nördlingen** 是全德僅存可繞行一週的完整環形城牆，走一圈回到原點。

---

## 安裝與使用

### 共通前置

| 項目 | 需求 | 備註 |
|---|---|---|
| Python | 3.8+ | `server.py` 只用標準庫，**沒有任何第三方依賴** |
| Ollama | 可選 | 只有「Ollama 模式」和擴展的「⚡ 生成」按鈕需要 |
| 模型 | `qwen2.5:7b` | 寫死在 `server.py` 的 `OLLAMA_MODEL`；想更快可換 `qwen2.5:3b` |

裝 Ollama 與模型：

```bash
ollama pull qwen2.5:7b
```

### macOS

```bash
cd ~/Documents/MyApp/fugaD
python3 server.py
```

然後瀏覽器開 `http://localhost:8765`。

桌面上的 `.command` 啟動器可雙擊執行，它會先清掉佔用埠號的舊行程、啟動伺服器、等就緒後自動開瀏覽器；關掉視窗即停止伺服器。腳本內硬編碼了 `APP_DIR`，搬動專案目錄後要同步改。

### Windows

```bat
cd C:\path\to\fugaD
py server.py
```

同樣開 `http://localhost:8765`。若 `py` 不存在，改用 `python`（安裝 Python 時記得勾選 *Add python.exe to PATH*）。

想要雙擊啟動，把下面存成 `start.bat` 放在專案目錄：

```bat
@echo off
cd /d "%~dp0"
start "" http://localhost:8765
py server.py
pause
```

### Linux

看得懂上面兩段就會了，不另外寫。

---

## 但書：「辞」鈕的適用範圍

底部工具列的「**辞**」（詞典匯出）**不是通用功能**，它只對使用 **Tolino 或 Kobo 電子書閱讀器**的人有意義——輸出的是 Kobo `dicthtml` 格式，需要把 zip 放進裝置的 `.kobo/custom-dict/` 目錄才能用。其他閱讀器（Kindle、reMarkable、PocketBook）格式不相容。

不用這兩種裝置的話，忽略這個按鈕即可；**其餘功能與它無關**，不裝 `pyglossary` 也不影響任何其他部分。

它另需 `pip install pyglossary marisa-trie`。麻煩之處在於 `pyglossary` 依賴 `pyicu`，而 `pyicu` 通常只裝在某一個特定環境裡（例如 Anaconda），不在系統 python 裡；Windows 上更不好裝。

因此執行詞典建置的直譯器是可設定的，預設取**啟動 server.py 的那個直譯器**：

| 環境變數 | 預設 | 用途 |
|---|---|---|
| `FUGA_DICT_PYTHON` | `sys.executable` | 執行 `build_quickdic.py` 的直譯器 |
| `FUGA_OLLAMA_MODEL` | `qwen2.5:7b` | Ollama 模型 |
| `FUGA_OLLAMA_URL` | `http://localhost:11434/api/generate` | Ollama 端點 |

所以最省事的做法是**直接用裝了 pyglossary 的那個 python 啟動伺服器**（`server.py` 只用標準庫，任何 3.8+ 直譯器都跑得動）：

```bash
/path/to/env/bin/python server.py
```

或者分開指定：

```bash
FUGA_DICT_PYTHON=/path/to/env/bin/python python3 server.py
```

伺服器啟動時會把實際採用的值印出來，可據以核對。**除此之外**（伺服器、網頁介面、Ollama 模式、瀏覽器擴展）在 Windows 上都正常。

---

## AI 聲明

本專案在開發過程中大量借助 Claude 撰寫程式碼。

其中瀏覽器選詞擴展 `extension/`、`server.py` 的 `/api/lookup`、`/api/translate`、`/api/pending` 端點與執行緒化改造、`index.html` 的待處理佇列回流邏輯，以及本安裝說明，由 **Claude Opus 5**（Anthropic）撰寫。

`vocab_db.json` 為個人詞庫，已在 `.gitignore` 中排除，不隨本倉庫發布。

---

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

更新 build_quickdic.py
將腳本從 QuickDic 格式改為 Kobo dicthtml 格式，流程是：

讀取 vocab_db.json
用 pyglossary 產生 Kobo 格式目錄（含 gzip 壓縮的 HTML + marisa-trie 索引）
將目錄打包成 dicthtml-de-zht.zip（不壓縮存儲，與官方格式一致）
輸出轉移指令
將詞典載入閱讀器的對應 目錄：`~/.kobo/custom-dict`

使用方式：在專案根目錄下，用**裝有 pyglossary 的那個直譯器**執行：

```bash
/path/to/env/bin/python build_quickdic.py
```

系統的 `python3` 通常不可用，因為 `pyicu` 多半只裝在特定環境（如 Anaconda）裡，缺少它會報錯。
從網頁介面按「辞」鈕時，伺服器會改用 `FUGA_DICT_PYTHON`（預設為啟動伺服器的直譯器）——見上方「但書」一節。


---

### 6. 瀏覽器選詞擴展 `extension/`

一個 Manifest V3 擴展（Vivaldi / Chrome / Edge / Brave）：在任意網頁上選中德語詞，
頁面側邊彈出獨立小窗口顯示詞庫註釋，排版與 LESEN 頁右欄一致；詞庫未收錄的詞可
一鍵交給本地 Ollama 生成並入庫。查過的詞會經由 `pending_queue.json` 回流到主應用的
詞頻與 Prüfung 閃卡池。

安裝與細節見 [extension/README.md](extension/README.md)。

`server.py` 為此新增了四個端點：`GET /api/lookup`、`POST /api/translate`、
`POST /api/pending`、`GET /api/pending?drain=1`，並改用 `ThreadingHTTPServer`，
避免一次 Ollama 生成把整個伺服器堵住。

## 截圖

![](img/homepage.png)

Get start.
![](img/start.png)

![](img/annotated-reading.png)

Anki quiz based on responsing time.
![](img/anki-Rosch.png)

