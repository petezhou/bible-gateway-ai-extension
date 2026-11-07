const server = document.querySelector('#server');
const status = document.querySelector('#status');
chrome.storage.local.get('serverURL').then((settings) => {
  server.value = settings.serverURL || 'http://127.0.0.1:8001';
});
document.querySelector('form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const url = new URL(server.value.trim());
    if (
      url.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(url.hostname) ||
      url.pathname !== '/' || url.username || url.password || url.search || url.hash
    ) throw new Error('Use a local address such as http://127.0.0.1:8001.');
    await chrome.storage.local.set({ serverURL: url.origin });
    status.textContent = 'Saved. New questions will use this server.';
  } catch (error) {
    status.textContent = error.message;
  }
});
