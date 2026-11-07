(() => {
  const mounted = new Map();
  const answers = new Map();

  function request(reference) {
    if (!answers.has(reference)) {
      const pending = chrome.runtime.sendMessage({
        type: 'study', endpoint: 'summary', payload: { reference },
      }).then((result) => {
        if (!result?.ok) throw new Error(result?.error || 'No response. Reload this page.');
        if (typeof result.data?.text !== 'string') throw new Error('The server returned an invalid answer.');
        return result.data;
      }).catch((error) => {
        answers.delete(reference);
        throw error;
      });
      answers.set(reference, pending);
    }
    return answers.get(reference);
  }

  async function load(state, passage) {
    const version = ++state.version;
    state.title.textContent = `Study summary · ${passage.label}`;
    state.body.replaceChildren();
    state.status.textContent = 'Reading the passage and commentary…';
    state.status.hidden = false;
    state.spinner.hidden = false;
    state.retry.hidden = true;
    state.region.setAttribute('aria-busy', 'true');
    try {
      const data = await request(passage.reference);
      if (state.version !== version || !state.host.isConnected) return;
      const { marked, DOMPurify } = BibleGatewayAILibraries;
      state.body.innerHTML = DOMPurify.sanitize(marked.parse(data.text), {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'a', 'hr'],
        ALLOWED_ATTR: ['href', 'title'],
      });
      for (const link of state.body.querySelectorAll('a')) {
        if (!/^https?:\/\//i.test(link.getAttribute('href') || '')) link.removeAttribute('href');
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }
      state.status.hidden = true;
    } catch (error) {
      if (state.version !== version || !state.host.isConnected) return;
      state.status.textContent = error.message || 'Unable to load the summary.';
      state.retry.hidden = false;
    } finally {
      if (state.version === version) {
        state.spinner.hidden = true;
        state.region.setAttribute('aria-busy', 'false');
      }
    }
  }

  function mount(passage) {
    const host = document.createElement('div');
    host.className = 'biblegateway-ai-summary';
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `
      <style>
        :host { display: block; margin: 12px 0 24px; color-scheme: light; }
        * { box-sizing: border-box; }
        [hidden] { display: none !important; }
        section { border-left: 3px solid #a7bcb0; padding: 14px 18px;
          background: #f5f7f1; color: #23362f; font: 14px/1.6 system-ui, sans-serif; }
        h2 { font-size: 13px; font-weight: 650; margin: 0 0 8px; }
        .loading { display: flex; align-items: center; gap: 9px; color: #57655b; }
        .spinner { width: 15px; height: 15px; flex-shrink: 0; border: 2px solid #cbd8ce;
          border-top-color: #244d40; border-radius: 50%; animation: spin .8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }
        p { margin: 0 0 10px; }
        .answer > :last-child { margin-bottom: 0; }
        .answer { overflow-wrap: anywhere; }
        .answer h1, .answer h2, .answer h3, .answer h4 { font-size: 14px; margin: 12px 0 6px; }
        ul, ol { padding-left: 22px; }
        pre { overflow-x: auto; }
        a { color: #2d6550; }
        button { margin-top: 10px; border: 1px solid #bdcdbf; border-radius: 8px;
          padding: 6px 12px; background: white; color: #244d40; font: inherit; cursor: pointer; }
        .note { font-size: 11px; color: #697970; margin: 10px 0 0; }
      </style>
      <section aria-label="Passage study summary" aria-busy="true">
        <h2></h2>
        <div class="loading"><span class="spinner" aria-hidden="true"></span><span role="status"></span></div>
        <div class="answer"></div>
        <button type="button" hidden>Retry summary</button>
        <p class="note">Uses ESV text, historic commentary, and Westminster context.</p>
      </section>`;
    passage.heading.after(host);
    return {
      host, version: 0, reference: passage.reference,
      region: shadow.querySelector('section'), title: shadow.querySelector('h2'),
      body: shadow.querySelector('.answer'), status: shadow.querySelector('[role="status"]'),
      spinner: shadow.querySelector('.spinner'), retry: shadow.querySelector('button'),
    };
  }

  function refresh() {
    for (const [table, state] of mounted) {
      if (!table.isConnected || !state.host.isConnected) {
        state.version++;
        state.host.remove();
        mounted.delete(table);
      }
    }
    for (const column of document.querySelectorAll('.passage-col')) {
      const table = column.closest('.passage-table[data-osis]') || column.querySelector('.passage-table[data-osis]');
      if (!table) continue;
      const passage = window.BibleGatewayAISelection.passage(table, column);
      let state = mounted.get(column);
      if (!passage?.heading) {
        if (state) {
          state.version++;
          state.host.remove();
          mounted.delete(column);
        }
        continue;
      }
      if (!state) {
        state = mount(passage);
        mounted.set(column, state);
        state.retry.addEventListener('click', () => {
          const current = window.BibleGatewayAISelection.passage(table, column);
          if (current) load(state, current);
        });
        load(state, passage);
      } else if (state.reference !== passage.reference) {
        state.reference = passage.reference;
        load(state, passage);
      }
    }
  }

  let timer;
  new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(refresh, 100);
  }).observe(document.body, { childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: ['data-osis'] });
  refresh();
})();
