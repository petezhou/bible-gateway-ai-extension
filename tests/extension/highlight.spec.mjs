import { test as base, expect, chromium } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createServer } from 'node:http';

// Synthetic text using the verse markup verified on BibleGateway's live page.
const fixture = `<!doctype html><html><head><style>
  body { margin: 100px; font: 24px/2 system-ui; max-width: 680px; }
</style></head><body>
  <div class="passage-text"><div class="passage-table" data-osis="John.3.10-John.4.1">
    <p><span class="text John-3-10"><sup>10</sup> First verse text with <span class="woj">nested words.</span></span>
    <span class="text John-3-11"><sup>11</sup> Second verse text for highlighting.</span>
    <span class="text John-3-12"><sup>12</sup> Third verse text for highlighting.</span></p>
    <p><span class="text John-4-1"><sup>1</sup> Another chapter text.</span></p>
  </div></div>
  <div class="passage-text"><span class="text 1-John-5-13"><sup>13</sup> A numbered book verse.</span></div>
  <p id="outside">Text outside the Bible passage.</p>
</body></html>`;

const test = base.extend({
  app: async ({}, use) => {
    const state = { requests: [], text: '**A sourced answer.**', status: 200, delay: 0 };
    const server = createServer(async (request, response) => {
      let body = '';
      for await (const chunk of request) body += chunk;
      state.requests.push({ endpoint: request.url, body: JSON.parse(body) });
      const text = state.text;
      const status = state.status;
      const delay = state.delay;
      setTimeout(() => {
        response.writeHead(status, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify(status === 200 ? {
          text, sources: ['Test commentary on John 3:10-12'], translation: 'ESV',
        } : { detail: 'Set ANTHROPIC_API_KEY in .env and restart the server' }));
      }, delay);
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const profile = await mkdtemp(path.join(tmpdir(), 'biblegateway-ai-test-'));
    const extension = path.resolve('extension');
    let context;
    try {
      context = await chromium.launchPersistentContext(profile, {
        channel: 'chromium',
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
        headless: true,
        viewport: { width: 1280, height: 900 },
        args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
      });
      const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
      await worker.evaluate((serverURL) => chrome.storage.local.set({ serverURL }),
        `http://127.0.0.1:${server.address().port}`);
      await context.route('https://www.biblegateway.com/**', (route) => route.fulfill({
        contentType: 'text/html', body: fixture,
      }));
      const page = await context.newPage();
      await page.goto('https://www.biblegateway.com/passage/?search=John+3&version=NIV');
      await expect(page.locator('#biblegateway-ai-study')).toBeAttached();
      await use({ page, worker, state });
    } finally {
      await context?.close();
      await new Promise((resolve) => server.close(resolve));
      await rm(profile, { recursive: true, force: true });
    }
  },
});

async function highlight(page, start, end = start) {
  await page.evaluate(({ start, end }) => {
    function textNode(selector, last) {
      const walker = document.createTreeWalker(document.querySelector(selector), NodeFilter.SHOW_TEXT);
      const nodes = [];
      let node;
      while ((node = walker.nextNode())) {
        if (node.textContent.trim() && !node.parentElement.closest('sup')) nodes.push(node);
      }
      return last ? nodes.at(-1) : nodes[0];
    }
    const from = textNode(start, false);
    const to = textNode(end, true);
    const range = document.createRange();
    range.setStart(from, 3); // Deliberately start and end partway through a verse.
    range.setEnd(to, to.textContent.length - 2);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    document.dispatchEvent(new Event('selectionchange'));
  }, { start, end });
  await expect(page.getByRole('button', { name: 'Ask AI about highlighted verses' })).toBeVisible();
}

for (const { start, end, reference, label } of [
  { start: '.John-3-10', end: '.John-3-12', reference: 'John.3.10-John.3.12', label: 'John 3:10-12' },
  { start: '[class="text 1-John-5-13"]', end: '[class="text 1-John-5-13"]', reference: '1John.5.13', label: '1 John 5:13' },
]) {
  test(`highlight to chat: ${reference}`, async ({ app }) => {
    // Arrange
    const { page, state } = app;

    // Act
    await highlight(page, start, end);
    await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).click();
    await page.getByRole('textbox', { name: 'Question about selected verses' }).fill('What connects these verses?');
    await page.getByRole('button', { name: 'Send', exact: true }).click();

    // Assert
    await expect(page.getByRole('heading', { name: label, exact: true })).toBeVisible();
    await expect(page.locator('.message.assistant strong')).toHaveText('A sourced answer.');
    expect(state.requests[0]).toEqual({ endpoint: '/chat', body: {
      reference, question: 'What connects these verses?', history: [],
    } });
  });
}

test('follow-up history, summary, and a new selection', async ({ app }) => {
  // Arrange
  const { page, state } = app;
  await highlight(page, '.John-3-10', '.John-3-12');
  await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).click();

  // Act
  await page.getByRole('button', { name: 'Summarize', exact: true }).click();
  await expect(page.locator('.message.assistant')).toHaveCount(1);
  await page.getByRole('textbox').fill('Tell me more.');
  await page.getByRole('textbox').press('Enter');

  // Assert
  await expect(page.locator('.message.assistant')).toHaveCount(2);
  expect(state.requests[0].endpoint).toBe('/summary');
  expect(state.requests[1].body.history).toEqual([
    { role: 'user', content: 'Summarize these verses.' },
    { role: 'assistant', content: '**A sourced answer.**' },
  ]);

  // Arrange
  await page.getByRole('button', { name: 'Close chat' }).click();
  // Move focus out of the shadow DOM before selecting the passage again.
  await page.locator('.John-3-10').click();

  // Act
  await highlight(page, '.John-3-11');
  await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).click();
  await page.getByRole('textbox').fill('New passage question.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  // Assert
  await expect(page.locator('.message.assistant')).toHaveCount(1);
  expect(state.requests[2].body.reference).toBe('John.3.11');
  expect(state.requests[2].body.history).toEqual([]);
});

test('cross-chapter selection cannot submit a request', async ({ app }) => {
  // Arrange
  const { page, state } = app;

  // Act
  await highlight(page, '.John-3-12', '.John-4-1');
  await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).click();

  // Assert
  await expect(page.getByRole('status')).toContainText('within one chapter');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  expect(state.requests).toHaveLength(0);
});

test('outside text does not trigger Ask AI', async ({ app }) => {
  // Arrange
  const { page } = app;

  // Act
  await page.locator('#outside').evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
  });

  // Assert
  await expect(page.getByRole('button', { name: 'Ask AI about highlighted verses' })).toBeHidden();
});

test('provider errors preserve question and allow retry', async ({ app }) => {
  // Arrange
  const { page, state } = app;
  state.status = 503;
  await highlight(page, '.John-3-10');
  await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).click();
  await page.getByRole('textbox').fill('Keep my question.');

  // Act
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  // Assert
  await expect(page.getByRole('status')).toContainText('ANTHROPIC_API_KEY');
  await expect(page.getByRole('textbox')).toHaveValue('Keep my question.');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();

  // Arrange
  state.status = 200;
  // Act
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  // Assert
  await expect(page.locator('.message.assistant')).toHaveCount(1);
  expect(state.requests[1].body.history).toEqual([]);
});

test('model Markdown is sanitized', async ({ app }) => {
  // Arrange
  const { page, state } = app;
  state.text = '**Safe text** <img src=x onerror="window.bad=true"><script>window.bad=true</script>';
  await highlight(page, '.John-3-10');
  await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).click();

  // Act
  await page.getByRole('button', { name: 'Summarize', exact: true }).click();

  // Assert
  await expect(page.locator('.message.assistant strong')).toHaveText('Safe text');
  await expect(page.locator('.message.assistant img, .message.assistant script')).toHaveCount(0);
  expect(await page.evaluate(() => window.bad)).toBeUndefined();
});

test('Ask AI sits beside the native toolbar', async ({ app }) => {
  // Arrange
  const { page } = app;
  await page.evaluate(() => {
    const toolbar = document.createElement('div');
    toolbar.id = 'native-toolbar';
    toolbar.style.cssText = 'position:fixed;top:400px;left:400px;width:270px;height:36px;background:white';
    toolbar.innerHTML = '<button><svg name="emoji-happy" width="20" height="20"></svg></button>';
    document.body.append(toolbar);
  });

  // Act
  await highlight(page, '.John-3-10', '.John-3-12');

  // Assert
  const toolbar = await page.locator('#native-toolbar').boundingBox();
  const action = await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).boundingBox();
  expect(Math.abs(action.x - toolbar.x - toolbar.width - 8)).toBeLessThan(1);
  expect(Math.abs(action.y + action.height / 2 - toolbar.y - toolbar.height / 2)).toBeLessThan(1);
});

test('a delayed model answer stays connected', async ({ app }) => {
  test.setTimeout(45000);
  // Arrange
  const { page, state } = app;
  state.delay = 31000;
  await highlight(page, '.John-3-10');
  await page.getByRole('button', { name: 'Ask AI about highlighted verses' }).click();

  // Act
  await page.getByRole('button', { name: 'Summarize', exact: true }).click();

  // Assert
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  await expect(page.locator('.message.assistant')).toHaveCount(1, { timeout: 35000 });
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
});
