(() => {
  if (document.getElementById('biblegateway-ai-study')) return;
  const host = document.createElement('div');
  host.id = 'biblegateway-ai-study';
  host.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;';
  const shadow = host.attachShadow({ mode: 'open' });
  // Static UI only. Model output is rendered through the sanitizer below.
  shadow.innerHTML = `
    <style>
      :host { all: initial; color-scheme: light; }
      * { box-sizing: border-box; }
      [hidden] { display: none !important; }
      button, input, textarea { font: inherit; }
      button { cursor: pointer; }
      button:disabled { cursor: wait; opacity: .55; }
      button:focus-visible, textarea:focus-visible { outline: 3px solid #9bbfb2; outline-offset: 2px; }
      .ask { position: fixed; pointer-events: auto; border: 1px solid #dae2dd; border-radius: 22px;
        padding: 10px 16px; color: white; background: #244d40; box-shadow: 0 3px 14px #0003;
        font: 600 14px/1.2 system-ui, sans-serif; white-space: nowrap; }
      .panel { position: fixed; pointer-events: auto; right: 20px; top: 20px;
        width: min(420px, calc(100vw - 24px)); height: min(680px, calc(100dvh - 40px));
        display: flex; flex-direction: column; background: #fffefb; color: #23362f;
        border: 1px solid #dedfd6; border-radius: 18px; box-shadow: 0 12px 50px #0003;
        font: 14px/1.55 system-ui, sans-serif; overflow: hidden; }
      header { display: flex; align-items: center; gap: 12px; padding: 18px 20px 12px; }
      .heading { flex: 1; }
      .eyebrow { color: #697970; text-transform: uppercase; letter-spacing: .12em; font-size: 10px; }
      h2 { margin: 3px 0 0; font-size: 19px; font-weight: 650; }
      .close { border: 0; background: transparent; color: #53665c; font-size: 26px; padding: 2px 8px; }
      .context { margin: 0 20px; padding: 10px 12px; border-left: 3px solid #a7bcb0;
        background: #f2f4ec; max-height: 90px; overflow: auto; font-size: 13px; color: #57655b; }
      .note { font-size: 11px; color: #6e7a71; margin: 9px 20px 13px; }
      .messages { flex: 1; min-height: 0; overflow-y: auto; padding: 2px 20px 18px; overscroll-behavior: contain; }
      .empty { padding-top: 25px; color: #6b776e; }
      .message { margin-top: 16px; overflow-wrap: anywhere; }
      .message.user { background: #edf2ec; border-radius: 12px; padding: 10px 13px; white-space: pre-wrap; }
      .message.assistant p { margin: 0 0 12px; }
      .message.assistant h1, .message.assistant h2, .message.assistant h3 { font-size: 16px; margin: 16px 0 8px; }
      .message.assistant ul, .message.assistant ol { padding-left: 22px; }
      .message.assistant blockquote { border-left: 2px solid #bbcbbf; margin-left: 0; padding-left: 12px; }
      .message.assistant pre { overflow-x: auto; background: #f0f1e9; padding: 10px; border-radius: 8px; }
      .message.assistant a { color: #2d6550; }
      details { color: #788176; font-size: 11px; margin-top: 8px; }
      details ul { padding-left: 18px; }
      .status { margin: 0 20px 8px; font-size: 12px; color: #68776c; }
      .status.error { color: #a0392b; }
      .settings { background: none; border: none; padding: 0; color: #375f4d; text-decoration: underline; }
      form { border-top: 1px solid #e3e5db; padding: 12px 16px 16px; background: #fafbf6; }
      textarea { resize: none; display: block; width: 100%; border: 1px solid #d6ded3;
        background: white; border-radius: 10px; padding: 11px 12px; color: #23362f; min-height: 76px; }
      .actions { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
      .summary { border: 1px solid #d4ded3; border-radius: 9px; background: white; padding: 8px 11px; color: #385548; }
      .hint { flex: 1; font-size: 10px; color: #849082; text-align: right; }
      .send { border: 0; border-radius: 9px; background: #244d40; color: white; padding: 8px 15px; }
      @media (max-width: 500px) { .panel { top: 12px; right: 12px; height: calc(100dvh - 24px); } .hint { display: none; } }
    </style>
    <button class="ask" type="button" hidden aria-label="Ask AI about highlighted verses">Ask AI ↗</button>
    <section class="panel" hidden role="dialog" aria-label="Bible study chat">
      <header>
        <div class="heading"><div class="eyebrow">Bible study</div><h2></h2></div>
        <button class="close" type="button" aria-label="Close chat">×</button>
      </header>
      <div class="context"></div>
      <p class="note">Answers use ESV text, historic commentary, and Westminster context.</p>
      <div class="messages" role="log" aria-label="Conversation"></div>
      <p class="status" role="status" aria-live="polite" hidden></p>
      <form>
        <textarea aria-label="Question about selected verses" placeholder="What would you like to understand?" maxlength="4000"></textarea>
        <div class="actions">
          <button class="summary" type="button">Summarize</button>
          <span class="hint">Enter to send · Shift+Enter for a new line</span>
          <button class="send" type="submit">Send</button>
        </div>
      </form>
    </section>
  `;
  document.documentElement.append(host);
  const find = (selector) => shadow.querySelector(selector);
  const ask = find('.ask');
  const panel = find('.panel');
  const messages = find('.messages');
  const input = find('textarea');
  const status = find('.status');
  let pendingSelection = null;
  let activeSelection = null;
  let history = [];
  let busy = false;
  let conversation = 0;
  let timer;

  function setStatus(text, error = false) {
    status.textContent = text;
    status.classList.toggle('error', error);
    status.hidden = !text;
    if (error) {
      status.append(' ');
      const link = document.createElement('button');
      link.className = 'settings';
      link.textContent = 'Settings';
      link.addEventListener('click', () => chrome.runtime.sendMessage({ type: 'open-settings' }));
      status.append(link);
    }
  }

  function refreshSelection() {
    const selection = window.getSelection();
    // Editing in the panel must not replace the verse selection.
    const focus = shadow.activeElement;
    if (focus && panel.contains(focus)) return;
    pendingSelection = window.BibleGatewayAISelection.read(selection);
    ask.hidden = !pendingSelection;
    if (!pendingSelection) return;
    const rect = pendingSelection.rect;
    ask.textContent = pendingSelection.error ? 'Ask AI · check selection' : 'Ask AI ↗';
    ask.title = pendingSelection.error || `Ask about ${pendingSelection.label}`;
    const { width, height } = ask.getBoundingClientRect();
    let left = rect.right - width;
    let top = rect.top - height - 8;
    // Anchor beside the native highlight toolbar using its semantic icon name,
    // avoiding BibleGateway's generated CSS class names. Fall back to the text
    // selection if the native toolbar is absent or its markup changes.
    const icon = document.querySelector('svg[name="emoji-happy"]');
    let ancestor = icon?.parentElement;
    for (let depth = 0; ancestor && depth < 6; depth++, ancestor = ancestor.parentElement) {
      const toolbar = ancestor.getBoundingClientRect();
      if (toolbar.width < 200 || toolbar.width > 700 || toolbar.height < 24 || toolbar.height > 100 || toolbar.right < 0 || toolbar.top < 0) continue;
      left = toolbar.right + 8;
      top = toolbar.top + (toolbar.height - height) / 2;
      if (left + width > window.innerWidth - 8) {
        left = toolbar.right - width;
        top = toolbar.bottom + 8;
      }
      break;
    }
    ask.style.left = `${Math.max(8, Math.min(left, window.innerWidth - width - 8))}px`;
    ask.style.top = `${Math.max(8, Math.min(top, window.innerHeight - height - 8))}px`;
  }

  function scheduleSelection() {
    clearTimeout(timer);
    timer = setTimeout(refreshSelection, 120);
  }

  function openSelection() {
    if (!pendingSelection) return;
    panel.hidden = false;
    if (pendingSelection.error) {
      conversation += 1;
      activeSelection = null;
      history = [];
      messages.replaceChildren();
      find('h2').textContent = 'Check your selection';
      find('.context').textContent = pendingSelection.excerpt;
      setBusy(false);
      setStatus(pendingSelection.error, true);
      return;
    }
    if (activeSelection?.reference !== pendingSelection.reference) {
      conversation += 1;
      busy = false;
      history = [];
      messages.replaceChildren();
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'Ask a question about these verses, or start with a summary.';
      messages.append(empty);
      input.value = '';
      setStatus('');
    }
    activeSelection = { ...pendingSelection };
    find('h2').textContent = activeSelection.label;
    find('.context').textContent = activeSelection.excerpt;
    ask.hidden = true;
    setBusy(busy);
    input.focus();
  }

  function setBusy(value) {
    busy = value;
    find('.send').disabled = value || !activeSelection;
    find('.summary').disabled = value || !activeSelection;
    input.disabled = value || !activeSelection;
  }

  function addMessage(role, text, sources = []) {
    find('.empty')?.remove();
    const element = document.createElement('div');
    element.className = `message ${role}`;
    if (role === 'assistant') {
      const { marked, DOMPurify } = BibleGatewayAILibraries;
      element.innerHTML = DOMPurify.sanitize(marked.parse(text), {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'a', 'hr'],
        ALLOWED_ATTR: ['href', 'title'],
      });
      for (const link of element.querySelectorAll('a')) {
        if (!/^https?:\/\//i.test(link.getAttribute('href') || '')) link.removeAttribute('href');
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }
      if (sources.length) {
        const details = document.createElement('details');
        const label = document.createElement('summary');
        label.textContent = 'Reference material supplied';
        const list = document.createElement('ul');
        for (const source of sources) {
          const item = document.createElement('li');
          item.textContent = source;
          list.append(item);
        }
        details.append(label, list);
        element.append(details);
      }
    } else {
      element.textContent = text;
    }
    messages.append(element);
    messages.scrollTop = messages.scrollHeight;
    return element;
  }

  async function send(endpoint) {
    if (busy || !activeSelection) return;
    const question = endpoint === 'summary' ? 'Summarize these verses.' : input.value.trim();
    if (!question) { input.focus(); return; }
    const currentConversation = conversation;
    const userBubble = addMessage('user', question);
    setBusy(true);
    setStatus('Reading the passage and commentary…');
    try {
      const payload = { reference: activeSelection.reference };
      if (endpoint === 'chat') {
        payload.question = question;
        payload.history = history.slice(-20);
      }
      const result = await chrome.runtime.sendMessage({ type: 'study', endpoint, payload });
      if (currentConversation !== conversation) return;
      if (!result?.ok) throw new Error(result?.error || 'No response from the extension. Reload this page.');
      addMessage('assistant', result.data.text, result.data.sources);
      history.push({ role: 'user', content: question }, { role: 'assistant', content: result.data.text });
      input.value = '';
      setStatus('');
    } catch (error) {
      if (currentConversation !== conversation) return;
      userBubble.remove();
      setStatus(error.message || 'Reload this page after reloading the extension.', true);
    } finally {
      if (currentConversation === conversation) {
        setBusy(false);
        input.focus();
      }
    }
  }

  // Prevent clicking the floating action from clearing the browser selection.
  ask.addEventListener('pointerdown', (event) => event.preventDefault());
  ask.addEventListener('click', openSelection);
  find('.close').addEventListener('click', () => { panel.hidden = true; });
  find('form').addEventListener('submit', (event) => { event.preventDefault(); send('chat'); });
  find('.summary').addEventListener('click', () => send('summary'));
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send('chat');
    }
  });
  shadow.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') panel.hidden = true;
  });
  document.addEventListener('selectionchange', scheduleSelection);
  document.addEventListener('pointerup', (event) => {
    if (!event.composedPath().includes(host)) scheduleSelection();
  });
  document.addEventListener('keyup', (event) => {
    if (!event.composedPath().includes(host)) scheduleSelection();
  });
  document.addEventListener('scroll', () => { ask.hidden = true; }, { passive: true, capture: true });
  window.addEventListener('resize', () => { ask.hidden = true; });
})();
