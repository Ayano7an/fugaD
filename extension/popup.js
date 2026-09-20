const fields = ['auto', 'autoTranslate', 'queue', 'peek', 'side', 'width', 'port'];

function apply(s) {
  document.getElementById('auto').checked = s.auto;
  document.getElementById('autoTranslate').checked = s.autoTranslate;
  document.getElementById('queue').checked = s.queue;
  document.getElementById('peek').checked = s.peek;
  document.getElementById('side').value = s.side;
  document.getElementById('width').value = s.width;
  document.getElementById('port').value = s.port;
  document.getElementById('open').href = `http://localhost:${s.port}/index.html`;
}

function collect() {
  return {
    auto: document.getElementById('auto').checked,
    autoTranslate: document.getElementById('autoTranslate').checked,
    queue: document.getElementById('queue').checked,
    peek: document.getElementById('peek').checked,
    side: document.getElementById('side').value,
    width: Math.min(640, Math.max(240, parseInt(document.getElementById('width').value, 10) || 332)),
    port: parseInt(document.getElementById('port').value, 10) || 8765
  };
}

function ping() {
  chrome.runtime.sendMessage({ type: 'ping' }, r => {
    const el = document.getElementById('status');
    if (r?.ok) {
      el.className = 'status ok';
      el.textContent = `已连接 ${r.url}  ·  队列 ${r.queued} 词`;
    } else {
      el.className = 'status bad';
      el.textContent = `连不上 ${r?.url || 'localhost'} — 启动 server.py`;
    }
  });
}

chrome.runtime.sendMessage({ type: 'settings' }, s => { apply(s); ping(); });

fields.forEach(id => {
  document.getElementById(id).addEventListener('change', () => {
    chrome.runtime.sendMessage({ type: 'save', patch: collect() }, s => { apply(s); ping(); });
  });
});

document.getElementById('open').addEventListener('click', e => {
  e.preventDefault();
  chrome.tabs.create({ url: e.target.href });
});
