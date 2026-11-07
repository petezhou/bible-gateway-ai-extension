const DEFAULT_SERVER = 'http://127.0.0.1:8001';

function serverURL(value) {
  const url = new URL(value || DEFAULT_SERVER);
  if (
    url.protocol !== 'http:' ||
    !['localhost', '127.0.0.1'].includes(url.hostname) ||
    url.username || url.password || url.pathname !== '/' || url.search || url.hash
  ) {
    throw new Error('Use a local server address, such as http://127.0.0.1:8001.');
  }
  return url.origin;
}

async function studyRequest(message) {
  const settings = await chrome.storage.local.get('serverURL');
  const base = serverURL(settings.serverURL);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 240000);
  // Keep the worker alive during a potentially long model request. Chrome can
  // terminate workers when a fetch response takes more than 30 seconds.
  const keepAlive = setInterval(() => chrome.runtime.getPlatformInfo(), 20000);
  try {
    const response = await fetch(`${base}/${message.endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.payload),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === 'string'
        ? data.detail
        : 'The server rejected this request. Check the selected verses and question.';
      throw new Error(detail);
    }
    if (typeof data.text !== 'string') throw new Error('The server returned an invalid answer.');
    return { ok: true, data };
  } catch (error) {
    if (error.name === 'AbortError') return { ok: false, error: 'The answer timed out. Try again.' };
    if (error instanceof TypeError) {
      return { ok: false, error: `Cannot reach ${base}. Start the local server or update the extension settings.` };
    }
    return { ok: false, error: error.message };
  } finally {
    clearTimeout(timeout);
    clearInterval(keepAlive);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'open-settings') {
    chrome.runtime.openOptionsPage();
    sendResponse({ ok: true });
    return;
  }
  if (message?.type !== 'study' || !['chat', 'summary'].includes(message.endpoint)) return;
  if (!sender.tab || !/^https:\/\/(www\.)?biblegateway\.com\/passage\//.test(sender.url || '')) return;
  studyRequest(message).then(sendResponse).catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
