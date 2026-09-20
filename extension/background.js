// Fuga Vocabs — service worker.
// All network traffic goes through here so page CSP (connect-src) can never block
// the calls to the local server, and so one lookup can fan out to several endpoints.

const DEFAULTS = {
  port: 8765,
  side: 'right',      // 'right' | 'left'
  auto: true,         // pop the panel on selection, vs. context menu only
  queue: true,        // feed looked-up words into the app's frequency stats
  autoTranslate: false, // call Ollama without waiting for the button
  peek: true,         // fade the panel while hovered, to read the text underneath
  width: 332          // panel width in px, set by dragging its inner edge
};

async function settings() {
  const s = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...s };
}

function base(s) {
  return `http://localhost:${s.port}`;
}

async function lookup(word, context) {
  const s = await settings();
  let r;
  try {
    // A server that accepts the connection but never answers would otherwise
    // hold this worker — and the panel — open indefinitely.
    // count=1 lets the server record the encounter and return the updated
    // tally in the same round trip, so the panel shows the same (N) the web UI
    // does instead of a number one behind.
    const count = s.queue ? '&count=1' : '';
    r = await fetch(`${base(s)}/api/lookup?w=${encodeURIComponent(word)}${count}`,
                    { signal: AbortSignal.timeout(10000) });
  } catch (e) {
    return { error: e.name === 'TimeoutError'
      ? `${base(s)} 无回应（10s）`
      : `连接不到 ${base(s)} — server.py 在跑吗？` };
  }
  if (!r.ok) return { error: `服务器返回 ${r.status}` };
  const d = await r.json();
  if (d.found) {
    return { found: true, entry: { ...d.entry, freq: d.freq ?? 0 } };
  }
  if (s.autoTranslate) return translate(word, context);
  return { found: false, word };
}

async function translate(word, context) {
  const s = await settings();
  let r;
  try {
    r = await fetch(`${base(s)}/api/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word, context, count: !!s.queue }),
      signal: AbortSignal.timeout(140000)   // server gives up at 120s
    });
  } catch (e) {
    return { error: e.name === 'TimeoutError'
      ? 'Ollama 生成逾時（140s）'
      : `连接不到 ${base(s)} — server.py 在跑吗？` };
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.ok) return { error: d.error || `服务器返回 ${r.status}` };
  return { found: true, entry: d.entry, fresh: true };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    // Anything thrown in here would close the port with no reply, which the
    // content script can only report as a timeout. Always answer.
    try {
    switch (msg.type) {
      case 'lookup':    reply(await lookup(msg.word, msg.context)); break;
      case 'translate': reply(await translate(msg.word, msg.context)); break;
      case 'settings':  reply(await settings()); break;
      case 'save':
        await chrome.storage.sync.set(msg.patch);
        reply(await settings());
        break;
      case 'ping': {
        const s = await settings();
        try {
          const r = await fetch(`${base(s)}/api/pending`);
          const d = await r.json();
          reply({ ok: r.ok, queued: d.count ?? 0, url: base(s) });
        } catch (e) {
          reply({ ok: false, url: base(s) });
        }
        break;
      }
      default: reply({ error: 'unknown message' });
    }
    } catch (e) {
      reply({ error: e?.message || String(e) });
    }
  })();
  return true; // keep the channel open for the async reply
});

// ── Context menu, for when auto-lookup is off or the selection is unusual ────
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'fuga-lookup',
    title: 'Fuga: 查询 “%s”',
    contexts: ['selection']
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== 'fuga-lookup' || !tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: 'show', word: info.selectionText });
});
