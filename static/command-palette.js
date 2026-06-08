/* Command Palette (⌘K) — embeddable on any page in this server.
 *
 * Triggers a floating overlay with fuzzy search over agents, processes,
 * dashboards, observations, and quick actions ("open office", "send
 * handoff", "mark X done"). Routes selected actions either to a /api
 * endpoint or to a URL.
 *
 * Usage: <script src="/static/command-palette.js" defer></script>
 *        Pressing ⌘K (or Ctrl+K) opens. Esc closes.
 */
(function () {
  if (window.__cmdkInstalled) return;
  window.__cmdkInstalled = true;

  const CSS = `
    #cmdk-backdrop {
      position: fixed; inset: 0;
      background: rgba(2, 6, 13, 0.55);
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
      z-index: 9998;
      display: none;
    }
    #cmdk-backdrop.open { display: block; }
    #cmdk-panel {
      position: fixed;
      top: 18vh;
      left: 50%;
      transform: translateX(-50%);
      width: min(640px, 92vw);
      max-height: 60vh;
      background: rgba(12, 18, 32, 0.96);
      border: 1px solid rgba(74, 216, 255, 0.4);
      border-radius: 12px;
      box-shadow: 0 24px 80px rgba(0,0,0,0.7), 0 0 32px rgba(74,216,255,0.18);
      z-index: 9999;
      display: none;
      overflow: hidden;
      color: #e6eaf3;
      font-family: 'Assistant', -apple-system, sans-serif;
      direction: rtl;
    }
    #cmdk-panel.open { display: flex; flex-direction: column; }
    #cmdk-input {
      width: 100%;
      padding: 14px 18px;
      background: transparent;
      border: none;
      outline: none;
      color: #e6eaf3;
      font-size: 15px;
      font-family: inherit;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      direction: rtl;
    }
    #cmdk-input::placeholder { color: rgba(133,144,166,0.7); }
    #cmdk-list {
      overflow-y: auto;
      max-height: calc(60vh - 60px);
      padding: 4px 0;
    }
    #cmdk-list::-webkit-scrollbar { width: 6px; }
    #cmdk-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
    .cmdk-row {
      padding: 10px 18px;
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      border-right: 2px solid transparent;
      transition: background 0.1s, border-color 0.1s;
    }
    .cmdk-row:hover, .cmdk-row.active {
      background: rgba(74,216,255,0.08);
      border-right-color: #4ad8ff;
    }
    .cmdk-icon {
      font-size: 16px;
      min-width: 24px;
      text-align: center;
    }
    .cmdk-body { flex: 1; min-width: 0; }
    .cmdk-title { color: #e6eaf3; font-size: 13px; line-height: 1.3; }
    .cmdk-sub { color: #8590a6; font-size: 11px; margin-top: 2px; }
    .cmdk-kind {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      color: #5a6477;
      background: rgba(255,255,255,0.04);
      padding: 2px 6px;
      border-radius: 3px;
      letter-spacing: 0.5px;
    }
    .cmdk-empty {
      color: #5a6477;
      font-style: italic;
      padding: 16px 18px;
      text-align: center;
    }
    .cmdk-foot {
      padding: 8px 18px;
      border-top: 1px solid rgba(255,255,255,0.06);
      font-size: 10px;
      color: #5a6477;
      font-family: 'JetBrains Mono', monospace;
      display: flex;
      gap: 14px;
      justify-content: space-between;
      align-items: center;
    }
    .cmdk-kbd {
      background: rgba(255,255,255,0.06);
      padding: 1px 5px;
      border-radius: 3px;
      color: #c0c7d4;
      font-size: 10px;
    }
  `;

  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  const backdrop = document.createElement('div');
  backdrop.id = 'cmdk-backdrop';
  const panel = document.createElement('div');
  panel.id = 'cmdk-panel';
  panel.innerHTML = `
    <input id="cmdk-input" type="text" placeholder="חפש סוכן, תהליך, פעולה... (פותח עם ⌘K)" autocomplete="off">
    <div id="cmdk-list"></div>
    <div class="cmdk-foot">
      <span><span class="cmdk-kbd">↑↓</span> ניווט · <span class="cmdk-kbd">↵</span> בחירה · <span class="cmdk-kbd">esc</span> סגירה</span>
      <span id="cmdk-count">0 תוצאות</span>
    </div>
  `;
  document.body.appendChild(backdrop);
  document.body.appendChild(panel);

  const input = panel.querySelector('#cmdk-input');
  const list = panel.querySelector('#cmdk-list');
  const countEl = panel.querySelector('#cmdk-count');

  let items = [];          // full item pool (loaded on first open)
  let filtered = [];       // current view
  let activeIdx = 0;

  // ─── Static actions always available ───
  function staticActions() {
    return [
      {
        kind: 'nav', icon: '🏛️', title: 'פתח את ה-Office',
        sub: 'תצוגה ויזואלית של המערכת', match: 'office משרד visual',
        action: () => { location.href = '/office'; },
      },
      {
        kind: 'nav', icon: '🎯', title: 'פתח את Mission Control',
        sub: 'Kanban של תובנות, מתוכננות, בעבודה, הושלמו', match: 'kanban mission control mission-control משימות',
        action: () => { location.href = '/mission-control'; },
      },
      {
        kind: 'nav', icon: '📊', title: 'Chief of Staff Dashboard',
        sub: 'תצוגה ראשית של הסוכנים והסקילים', match: 'dashboard chief of staff cos',
        action: () => { location.href = '/'; },
      },
      {
        kind: 'action', icon: '💬', title: 'שלח handoff חדש (חוויית בדיקה)',
        sub: 'jarvis → consulting-advisor', match: 'handoff שלח test בדיקה',
        action: async () => {
          const title = prompt('כותרת ההודעה:');
          if (!title) return;
          await fetch('/api/agents/message', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              from_agent: 'jarvis',
              to_agent: 'consulting-advisor',
              kind: 'handoff',
              title: title,
              body: 'נשלח דרך ⌘K Command Palette',
            }),
          });
          alert('נשלח. ראה את ה-Office או War Room.');
        },
      },
    ];
  }

  async function loadItems() {
    const pool = staticActions();
    try {
      const state = await fetch('/api/state').then(r => r.json());
      // Agents
      for (const a of state.agents || []) {
        pool.push({
          kind: 'agent', icon: a.icon || '🤖',
          title: a.name, sub: a.description ? a.description.slice(0, 80) : a.slug,
          match: `${a.slug} ${a.name} ${a.kind} agent`,
          action: () => { window.open(`/?focus=agent:${a.slug}`, '_self'); },
        });
      }
      // Processes
      for (const p of state.processes || []) {
        pool.push({
          kind: 'process', icon: p.icon || '🔁',
          title: p.name,
          sub: `${p.cadence || 'manual'} · ${p.last_status || 'unknown'}`,
          match: `${p.slug} ${p.name} process`,
          action: () => { window.open(`/?focus=process:${p.slug}`, '_self'); },
        });
      }
      // Dashboards
      for (const d of state.dashboards || []) {
        pool.push({
          kind: 'dashboard', icon: d.icon || '📊',
          title: d.name, sub: d.url || d.description || '',
          match: `${d.slug} ${d.name} dashboard ${d.url || ''}`,
          action: () => { if (d.url) window.open(d.url, '_blank'); },
        });
      }
      // Open observations (top 15)
      for (const o of (state.observations || []).slice(0, 15)) {
        pool.push({
          kind: 'obs', icon: o.severity === 'critical' ? '🔴' : (o.severity === 'warning' ? '🟡' : '💡'),
          title: o.title,
          sub: o.body ? o.body.slice(0, 80) : o.subject_slug || '',
          match: `${o.title} ${o.body || ''} ${o.kind} observation`,
          action: () => { location.href = `/mission-control`; },
        });
      }
    } catch (e) {
      // server unreachable — fall back to static actions only
    }
    return pool;
  }

  function fuzzyScore(needle, hay) {
    if (!needle) return 1;
    needle = needle.toLowerCase().trim();
    hay = (hay || '').toLowerCase();
    if (!needle) return 1;
    if (hay.includes(needle)) return 100 + (hay.startsWith(needle) ? 20 : 0);
    // char-by-char substring scoring
    let i = 0, score = 0;
    for (const ch of needle) {
      const j = hay.indexOf(ch, i);
      if (j === -1) return 0;
      score += (j === i ? 2 : 1);
      i = j + 1;
    }
    return score;
  }

  function render() {
    if (!filtered.length) {
      list.innerHTML = '<div class="cmdk-empty">אין תוצאות. נסה משהו אחר.</div>';
      countEl.textContent = '0 תוצאות';
      return;
    }
    countEl.textContent = `${filtered.length} תוצאות`;
    list.innerHTML = filtered.slice(0, 30).map((it, i) => `
      <div class="cmdk-row ${i === activeIdx ? 'active' : ''}" data-idx="${i}">
        <div class="cmdk-icon">${it.icon || '•'}</div>
        <div class="cmdk-body">
          <div class="cmdk-title">${escapeHtml(it.title)}</div>
          ${it.sub ? `<div class="cmdk-sub">${escapeHtml(it.sub)}</div>` : ''}
        </div>
        <div class="cmdk-kind">${it.kind}</div>
      </div>
    `).join('');

    list.querySelectorAll('.cmdk-row').forEach(row => {
      row.addEventListener('click', () => {
        activeIdx = parseInt(row.dataset.idx, 10);
        runActive();
      });
      row.addEventListener('mouseenter', () => {
        activeIdx = parseInt(row.dataset.idx, 10);
        updateActiveClass();
      });
    });
  }

  function updateActiveClass() {
    list.querySelectorAll('.cmdk-row').forEach(r => {
      r.classList.toggle('active', parseInt(r.dataset.idx, 10) === activeIdx);
    });
    const active = list.querySelector('.cmdk-row.active');
    if (active) active.scrollIntoView({block: 'nearest'});
  }

  function escapeHtml(s) {
    return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function applyFilter() {
    const q = input.value;
    if (!q) {
      filtered = items.slice();
    } else {
      filtered = items
        .map(it => ({ it, score: fuzzyScore(q, it.match) }))
        .filter(x => x.score > 0)
        .sort((a, b) => b.score - a.score)
        .map(x => x.it);
    }
    activeIdx = 0;
    render();
  }

  function runActive() {
    const it = filtered[activeIdx];
    if (!it) return;
    close();
    setTimeout(() => it.action(), 50);
  }

  async function open() {
    backdrop.classList.add('open');
    panel.classList.add('open');
    input.value = '';
    input.focus();
    if (!items.length) {
      list.innerHTML = '<div class="cmdk-empty">טוען...</div>';
      items = await loadItems();
    }
    applyFilter();
  }

  function close() {
    backdrop.classList.remove('open');
    panel.classList.remove('open');
  }

  input.addEventListener('input', applyFilter);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); activeIdx = Math.min(activeIdx + 1, filtered.length - 1); updateActiveClass(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); activeIdx = Math.max(activeIdx - 1, 0); updateActiveClass(); }
    else if (e.key === 'Enter') { e.preventDefault(); runActive(); }
    else if (e.key === 'Escape') { e.preventDefault(); close(); }
  });
  backdrop.addEventListener('click', close);

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (panel.classList.contains('open')) close();
      else open();
    }
  });

  // Expose for programmatic use
  window.cmdk = { open, close };
})();
