// Fuga Vocabs — service worker.
// All network traffic goes through here so page CSP (connect-src) can never block
// the calls to the local server, and so one lookup can fan out to several endpoints.

const DEFAULTS = {
  port: 8765,
  side: 'right',      // 'right' | 'left'
  auto: true,         // pop the panel on selection, vs. context menu only
  queue: true,        // feed looked-up words into the app's frequency stats
  autoTranslate: false // call Ollama without waiting for the button
};

async function settings() {
  const s = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...s };
}

function base(s) {
  return `http://localhost:${s.port}`;
}

async function enqueue(s, word) {
  if (!s.queue || !word) return;
  try {
    await fetch(`${base(s)}/api/pending`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ words: [word] })
    });
  } catch (e) { /* queue is best-effort; never block a lookup on it */ }
}

async function lookup(word, context) {
  const s = await settings();
  let r;
  try {
    r = await fetch(`${base(s)}/api/lookup?w=${encodeURIComponent(word)}`);
  } catch (e) {
    return { error: `连接不到 ${base(s)} — server.py 在跑吗？` };
  }
  if (!r.ok) return { error: `服务器返回 ${r.status}` };
  const d = await r.json();
  if (d.found) {
    enqueue(s, d.entry.word);
    return { found: true, entry: d.entry };
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
      body: JSON.stringify({ word, context })
    });
  } catch (e) {
    return { error: `连接不到 ${base(s)} — server.py 在跑吗？` };
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.ok) return { error: d.error || `服务器返回 ${r.status}` };
  enqueue(s, d.entry.word);
  return { found: true, entry: d.entry, fresh: true };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
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
