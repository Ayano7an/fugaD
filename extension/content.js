// Fuga Vocabs — content script.
// Watches text selections, renders a docked side panel in a shadow root so no
// page stylesheet can reach it and nothing it does leaks back into the page.

(() => {
  if (window.__fugaVocabsLoaded) return;
  window.__fugaVocabsLoaded = true;

  const GERMAN = "A-Za-zÄÖÜäöüßéèêàâçñ";
  const WORD_RE = new RegExp(`^[${GERMAN}][${GERMAN}'’\\-]*(?:\\s+[${GERMAN}][${GERMAN}'’\\-]*){0,2}$`);
  const MAX_CARDS = 12;

  let settings = { side: 'right', auto: true, port: 8765, queue: true,
                   autoTranslate: false, peek: true, width: 332 };
  let host = null, root = null, panel = null, listEl = null, countEl = null;
  let cards = [];          // most-recent-first, {word, state, entry, error}
  let lastQuery = '';

  chrome.runtime.sendMessage({ type: 'settings' }, s => { if (s) settings = s; });

  // Settings live in chrome.storage, which content scripts can read directly —
  // no cross-tab broadcast and therefore no host permission on the page needed.
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return;
    for (const [k, v] of Object.entries(changes)) settings[k] = v.newValue;
    applySettings();
  });

  // ── Panel construction ────────────────────────────────────────────────────
  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    .panel {
      position: fixed; top: 9vh; width: 332px; max-height: 78vh;
      min-width: 240px; max-width: 640px;
      display: flex; flex-direction: column;
      background: #ffffff; color: #1a1a1a;
      border: 1px solid #e0e0e0; border-top: 2px solid #c41e3a;
      box-shadow: 0 4px 24px rgba(0,0,0,0.18);
      font-family: 'Cormorant Garamond', Georgia, 'Times New Roman', serif;
      font-size: 16px; line-height: 1.5;
      z-index: 2147483647;
      transition: transform .18s ease, opacity .18s ease;
    }
    .panel.right { right: 0; border-right: none; }
    .panel.left  { left: 0;  border-left: none; }
    .panel.hidden.right { transform: translateX(105%); opacity: 0; pointer-events: none; }
    .panel.hidden.left  { transform: translateX(-105%); opacity: 0; pointer-events: none; }

    /* Peek: fade out while hovered so the text underneath stays readable.
       Hovering the header strip or any control brings it straight back, so the
       controls never become unaimable. */
    .panel.peekable:hover { opacity: .15; }
    .panel.peekable:hover:has(.head:hover, button:hover, a:hover) { opacity: 1; }
    .panel.resizing { transition: none; }
    .panel.resizing, .panel.resizing * { user-select: none; }

    /* Drag handle on the panel's inner edge */
    .grip { position: absolute; top: 0; bottom: 0; width: 9px; cursor: ew-resize; }
    .panel.right .grip { left: -1px; }
    .panel.left  .grip { right: -1px; }
    .grip::after {
      content: ''; position: absolute; top: 50%; transform: translateY(-50%);
      left: 3px; width: 3px; height: 34px; border-radius: 2px;
      background: #c41e3a; opacity: 0; transition: opacity .15s;
    }
    .grip:hover::after, .grip.dragging::after { opacity: .55; }

    .head {
      background: #1e4a8a; color: #fff; flex: none;
      padding: .5rem .7rem; display: flex; align-items: center; gap: .5rem;
      font-family: ui-monospace, 'JetBrains Mono', Menlo, monospace;
      font-size: 11px; text-transform: uppercase; letter-spacing: .1em;
    }
    .head .title { font-weight: 600; }
    .head .count { color: #d4a849; }
    .head .spacer { flex: 1; }
    .head button {
      background: transparent; border: 1px solid rgba(255,255,255,.3); color: #fff;
      font: inherit; font-size: 11px; line-height: 1; padding: 3px 6px; cursor: pointer;
      transition: background .15s;
    }
    .head button:hover { background: rgba(255,255,255,.15); }

    .list { overflow-y: auto; flex: 1; }
    .list::-webkit-scrollbar { width: 6px; }
    .list::-webkit-scrollbar-thumb { background: #d8d8d8; }

    .card { border-bottom: 1px solid #e0e0e0; padding: .55rem .8rem; }
    .card:first-child { background: #f8f9fa; }
    .card .word { font-weight: 600; color: #c41e3a; font-size: 17px; letter-spacing: .02em; }
    .card .badge {
      font-family: ui-monospace, Menlo, monospace; font-size: 9px; color: #6a6a6a;
      border: 1px solid #e0e0e0; border-radius: 2px; padding: 0 3px;
      margin-left: .4rem; vertical-align: middle; opacity: .8;
    }
    .card .def { padding-top: .15rem; }
    .card .lemma { color: #6a6a6a; font-style: italic; font-size: 13px; }
    .card .zh { color: #c41e3a; font-weight: 700; font-size: 15px; }
    .card .en { color: #1e4a8a; font-size: 13px; }
    .card .etym { color: #6a6a6a; font-size: 12px; margin-top: .15rem; }
    .card .sep { color: #c0c0c0; }
    .card .miss { color: #6a6a6a; font-style: italic; font-size: 13px; padding-top: .2rem; }
    .card .err  { color: #c41e3a; font-size: 12px; padding-top: .2rem; }

    .gen {
      margin-top: .35rem; background: transparent; border: 1px solid #c41e3a; color: #c41e3a;
      font-family: ui-monospace, Menlo, monospace; font-size: 11px; letter-spacing: .05em;
      padding: 3px 8px; cursor: pointer; transition: all .15s;
    }
    .gen:hover { background: #c41e3a; color: #fff; }
    .gen:disabled { opacity: .5; cursor: default; background: transparent; color: #c41e3a; }

    .empty { color: #6a6a6a; font-style: italic; text-align: center; padding: 2rem 1rem; font-size: 14px; }
    .foot {
      flex: none; border-top: 1px solid #e0e0e0; background: #f8f9fa;
      padding: .35rem .7rem; color: #6a6a6a;
      font-family: ui-monospace, Menlo, monospace; font-size: 10px; letter-spacing: .04em;
      display: flex; justify-content: space-between; align-items: center;
    }
    .foot a { color: #1e4a8a; text-decoration: none; }
    .foot a:hover { text-decoration: underline; }
  `;

  function build() {
    host = document.createElement('div');
    host.id = 'fuga-vocabs-host';
    root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>${CSS}</style>
      <div class="panel hidden ${settings.side}">
        <div class="grip" title="拖曳調整寬度"></div>
        <div class="head">
          <span class="title">Fuga</span><span class="count"></span>
          <span class="spacer"></span>
          <button data-act="side" title="换边">⇄</button>
          <button data-act="clear" title="清空">⌫</button>
          <button data-act="close" title="关闭">✕</button>
        </div>
        <div class="list"></div>
        <div class="foot">
          <span class="hint">选中词即查</span>
          <a href="#" data-act="open">打开 Fuga ↗</a>
        </div>
      </div>`;
    (document.body || document.documentElement).appendChild(host);
    panel = root.querySelector('.panel');
    listEl = root.querySelector('.list');
    countEl = root.querySelector('.count');

    root.addEventListener('click', e => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act) e.preventDefault();
      if (act === 'close') hide();
      else if (act === 'clear') { cards = []; render(); }
      else if (act === 'side') {
        settings.side = settings.side === 'right' ? 'left' : 'right';
        chrome.runtime.sendMessage({ type: 'save', patch: { side: settings.side } });
        applySettings();
      } else if (act === 'open') {
        window.open(`http://localhost:${settings.port}/index.html`, '_blank');
      } else if (act === 'gen') {
        const w = e.target.dataset.word;
        generate(w, e.target);
      }
    });

    initGrip();
    applySettings();
  }

  // Side, width and peek all live in settings; one place applies them so the
  // popup, the ⇄ button and a drag all converge on the same rendering.
  function applySettings() {
    if (!panel) return;
    panel.classList.remove('left', 'right');
    panel.classList.add(settings.side);
    panel.classList.toggle('peekable', !!settings.peek);
    panel.style.width = clampWidth(settings.width) + 'px';
  }

  const clampWidth = w => Math.min(640, Math.max(240, Math.round(Number(w) || 332)));

  // Drag the panel's inner edge to resize. Pointer capture keeps the drag alive
  // when the cursor leaves the handle or the window.
  function initGrip() {
    const grip = root.querySelector('.grip');
    grip.addEventListener('pointerdown', e => {
      e.preventDefault();
      const startX = e.clientX;
      const startW = panel.getBoundingClientRect().width;
      grip.setPointerCapture(e.pointerId);
      grip.classList.add('dragging');
      panel.classList.add('resizing');

      const move = ev => {
        const dx = ev.clientX - startX;
        settings.width = clampWidth(settings.side === 'right' ? startW - dx : startW + dx);
        panel.style.width = settings.width + 'px';
      };
      const done = () => {
        grip.removeEventListener('pointermove', move);
        grip.removeEventListener('pointerup', done);
        grip.removeEventListener('pointercancel', done);
        grip.classList.remove('dragging');
        panel.classList.remove('resizing');
        chrome.runtime.sendMessage({ type: 'save', patch: { width: settings.width } });
      };
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', done);
      grip.addEventListener('pointercancel', done);
    });
  }

  function show() {
    if (!host) build();
    applySettings();
    panel.classList.remove('hidden');
  }
  function hide() { panel?.classList.add('hidden'); }

  const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const SRC_BADGE = { gemma: '🈹 Ollama', llm: '🛜 LLM' };

  function cardHtml(c) {
    if (c.state === 'loading')
      return `<div class="card"><span class="word">${esc(c.word)}</span>
              <div class="miss">查询中…</div></div>`;
    if (c.state === 'error')
      return `<div class="card"><span class="word">${esc(c.word)}</span>
              <div class="err">${esc(c.error)}</div></div>`;
    if (c.state === 'missing')
      return `<div class="card"><span class="word">${esc(c.word)}</span>
              <div class="miss">词库未收录</div>
              <button class="gen" data-act="gen" data-word="${esc(c.word)}">⚡ Ollama 生成</button></div>`;
    if (c.state === 'generating')
      return `<div class="card"><span class="word">${esc(c.word)}</span>
              <div class="miss">Ollama 生成中…</div></div>`;

    const e = c.entry;
    const badge = SRC_BADGE[e.source] ? `<span class="badge">${SRC_BADGE[e.source]}</span>` : '';
    const parts = [];
    if (e.lemma && e.lemma !== e.word) parts.push(`<span class="lemma">${esc(e.lemma)}</span>`);
    if (e.zh) parts.push(`<span class="zh">${esc(e.zh)}</span>`);
    if (e.en) parts.push(`<span class="en">${esc(e.en)}</span>`);
    const etym = e.etym ? `<div class="etym">» ${esc(e.etym)}</div>` : '';
    return `<div class="card"><span class="word">${esc(e.word)}</span>${badge}
            <div class="def">${parts.join(' <span class="sep">·</span> ')}${etym}</div></div>`;
  }

  function render() {
    if (!root) return;
    listEl.innerHTML = cards.length
      ? cards.map(cardHtml).join('')
      : '<div class="empty">选中页面上的德语词以查询</div>';
    countEl.textContent = cards.length ? `${cards.length}` : '';
    listEl.scrollTop = 0;
  }

  function upsert(word, patch) {
    const i = cards.findIndex(c => c.word === word);
    const c = { word, ...(i >= 0 ? cards[i] : {}), ...patch };
    if (i >= 0) cards.splice(i, 1);
    cards.unshift(c);
    cards = cards.slice(0, MAX_CARDS);
    render();
  }

  // ── Lookup flow ───────────────────────────────────────────────────────────
  function query(word, context) {
    word = word.trim();
    if (!word) return;
    show();
    upsert(word, { state: 'loading' });
    chrome.runtime.sendMessage({ type: 'lookup', word, context }, res => {
      if (chrome.runtime.lastError) {
        upsert(word, { state: 'error', error: '扩展未就绪，请重载页面' });
        return;
      }
      if (!res) upsert(word, { state: 'error', error: '无响应' });
      else if (res.error) upsert(word, { state: 'error', error: res.error });
      else if (res.found) upsert(word, { state: 'ok', entry: res.entry });
      else upsert(word, { state: 'missing' });
    });
  }

  function generate(word, btn) {
    if (btn) btn.disabled = true;
    const ctx = lastContextFor.get(word) || '';
    upsert(word, { state: 'generating' });
    chrome.runtime.sendMessage({ type: 'translate', word, context: ctx }, res => {
      if (!res || res.error) upsert(word, { state: 'error', error: res?.error || '生成失败' });
      else upsert(word, { state: 'ok', entry: res.entry });
    });
  }

  // ── Selection watching ────────────────────────────────────────────────────
  const lastContextFor = new Map();

  function sentenceAround(sel) {
    try {
      const node = sel.anchorNode;
      if (!node) return '';
      const text = (node.textContent || '').replace(/\s+/g, ' ');
      const at = sel.anchorOffset;
      const from = Math.max(0, at - 140), to = Math.min(text.length, at + 140);
      return text.slice(from, to).trim();
    } catch (e) { return ''; }
  }

  function onSelect() {
    if (!settings.auto) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    // ignore selections made inside our own panel
    if (host && sel.anchorNode && host.contains(sel.anchorNode)) return;
    const raw = sel.toString().trim();
    if (raw.length < 2 || raw.length > 48) return;
    if (!WORD_RE.test(raw)) return;
    if (raw === lastQuery) return;
    lastQuery = raw;
    lastContextFor.set(raw, sentenceAround(sel));
    query(raw, lastContextFor.get(raw));
  }

  let timer = null;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(onSelect, 180); };
  document.addEventListener('mouseup', schedule, true);
  document.addEventListener('keyup', e => { if (e.shiftKey || e.key === 'Shift') schedule(); }, true);

  // ── Messages from the service worker ──────────────────────────────────────
  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (msg.type === 'show') {
      const w = (msg.word || '').trim();
      lastQuery = w;
      query(w, '');
    } else if (msg.type === 'toggle') {
      if (!host || panel.classList.contains('hidden')) { show(); render(); } else hide();
    }
    reply?.({ ok: true });
  });
})();
