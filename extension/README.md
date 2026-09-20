# Fuga Vocabs — 浏览器选词扩展

在任意网页上选中一个德语词，页面侧边弹出一个独立小窗口，显示该词在 `vocab_db.json`
中的注释（词 / 原型 / 繁中 / 英文 / 词根词缀），排版与主应用 LESEN 页右栏一致。
词库里没有的词，点一下按钮交给本地 Ollama 生成并自动入库。

## 安装（Vivaldi / Chrome / Edge / Brave）

1. 先让本地服务跑起来：

   ```bash
   python3 server.py   # 在專案根目錄執行
   ```

2. 浏览器地址栏进入 `vivaldi://extensions`（Chrome 是 `chrome://extensions`）
3. 打开右上角 **开发者模式**
4. 点 **加载已解压的扩展程序**，选择本目录 `fugaD/extension/`

装好后工具栏出现红色 **F** 图标。

## 使用

| 操作 | 结果 |
|---|---|
| 网页上选中一个德语词 | 侧边面板弹出，显示词库注释 |
| 词库未收录 | 显示「⚡ Ollama 生成」按钮，点击后本地生成并写入 `vocab_db.json` |
| 右键选中文字 → `Fuga: 查询 “…”` | 手动触发（关掉「选中即查」时用这个） |
| 面板 `⇄` | 左右换边 |
| 面板 `⌫` / `✕` | 清空历史 / 关闭面板 |
| 点工具栏 F 图标 | 设置：选中即查、自动调 Ollama、计入频率统计、面板位置、端口 |

面板保留最近 12 个查过的词，最新的在最上面——一次阅读下来就是一张生词清单。

## 查词逻辑

选中文字先去掉首尾标点，然后按顺序尝试：

1. 原样匹配 `vocab_db.json` 的词条 key
2. 大小写变体（全小写 / 首字母大写 / 全大写 / Title Case）
3. lemma 反向索引 —— 选中 `die Entwicklung` 也能命中 `Entwicklung`；
   索引按 `vocab_db.json` 的 mtime 缓存，改动后自动重建

全部未命中才算「未收录」。选中时所在句子（前后各 140 字符）会随 Ollama 请求一起发过去，
用来消歧义。

## 与主应用的联动

查成功的词会推进服务器的 `pending_queue.json`。主应用 `index.html` 在**加载时**和
**窗口重新获得焦点时**调用 `/api/pending?drain=1` 取走队列，把这些词按各自的时间戳
计入对应旬的词频，模型标记为 `Browser`。所以：

- 浏览器里读到的词会出现在 **Frequenz** 页
- 也会进入 **Prüfung** 的闪卡池（meta 从 `vocab_db.json` 借）
- 主应用开着的话，切回它那个标签页就会同步，右下角提示「瀏覽器查詞 +N」

只有查到结果的词才入队 —— 误选的乱码不会污染统计。这个行为可以在扩展设置里关掉。

## 新增的服务端端点

| 端点 | 用途 |
|---|---|
| `GET /api/lookup?w=Wort` | 单词查询，带大小写与 lemma 回退。**不要**用 `/api/db`，那会吐出整个 1MB 词库 |
| `POST /api/translate` | `{word, context}` → 单词过一遍 Ollama，按 source 优先级写库后返回词条 |
| `POST /api/pending` | `{words:[…]}` 入队 |
| `GET /api/pending[?drain=1]` | 查看 / 取走队列 |

`POST /api/translate` 沿用 `llm(2) > gemma(1)` 优先级：已有 LLM 翻译的词不会被本地模型覆盖，
这时返回 `saved: false` 和原有词条。

## 注意

- 扩展的 content script 匹配 `<all_urls>`，即所有网页都会注入。面板用 shadow DOM 隔离，
  不会被页面样式污染，也不会影响页面本身。介意的话可以把 `manifest.json` 里的
  `matches` 改成具体站点。
- 服务器没跑时面板会显示「连接不到 localhost:8765」。
- 单词生成速度取决于模型：当前 `server.py` 用 `qwen2.5:7b`，实测一个新词约 8 秒。
  想更快就把 `OLLAMA_MODEL` 改成 `qwen2.5:3b`。
