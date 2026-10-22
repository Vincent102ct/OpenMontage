/* Real Chrome input flows. Uses the repository's existing CDP browser driver only;
 * never calls a Remotion render/composition API or generates production media. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {openBrowser} = require(require.resolve('@remotion/renderer', {paths: [path.resolve('remotion-composer')]}));

const [url, chrome, screenshots] = process.argv.slice(2);
const findings = {checks: [], externalRequests: [], pageErrors: []};
let browser;
let page;
const pause = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function waitFor(fn, label) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn)) return;
    await pause(50);
  }
  throw new Error(`Timed out: ${label}`);
}
async function check(fn, label) {
  assert.ok(await page.evaluate(fn), label);
  findings.checks.push(label);
}
async function click(id) { await page.evaluate(id => document.getElementById(id).click(), id); }
async function input(id, value) {
  await page.evaluate((id, value) => {
    const node = document.getElementById(id);
    node.value = value;
    node.dispatchEvent(new Event('input', {bubbles: true}));
  }, id, value);
}
async function mode(value) {
  await page.evaluate(value => {
    const node = document.querySelector(`[name="input_mode"][value="${value}"]`);
    node.checked = true;
    node.dispatchEvent(new Event('change', {bubbles: true}));
  }, value);
}
async function capture(name) {
  const {value: layout} = await page._client().send('Page.getLayoutMetrics');
  const {value: result} = await page._client().send('Page.captureScreenshot', {
    format: 'png', captureBeyondViewport: true,
    clip: {x: 0, y: 0, width: layout.cssContentSize.width, height: layout.cssContentSize.height, scale: 1},
  });
  fs.writeFileSync(path.join(screenshots, name), Buffer.from(result.data, 'base64'));
}

(async () => {
  fs.mkdirSync(screenshots, {recursive: true});
  browser = await openBrowser('chrome', {browserExecutable: chrome, logLevel: 'error'});
  page = await browser.newPage({context: () => null, logLevel: 'error', indent: false,
    pageIndex: 0, onBrowserLog: null, onLog: () => {}});
  page.on('error', error => findings.pageErrors.push(String(error)));
  await page.setViewport({width: 1440, height: 1050, deviceScaleFactor: 1});
  await page._client().send('Network.enable');
  page._client().on('Network.requestWillBeSent', event => {
    if (/^https?:/.test(event.request.url) && !event.request.url.startsWith(new URL(url).origin + '/')) {
      findings.externalRequests.push(event.request.url);
    }
  });
  await page.goto({url, timeout: 20000});
  await waitFor(() => document.querySelectorAll('#canonical-package option').length === 2, 'fixture catalog');
  await click('list-tab');
  await waitFor(() => document.getElementById('list-status').textContent.includes('No productions yet'), 'empty library');
  await check(() => document.querySelectorAll('.production-card').length === 0, 'Empty state');
  await click('new-tab');
  await click('save-button');
  await check(() => !document.getElementById('form-error').hidden, 'Missing story validation');
  await input('content', 'Nội dung test');
  await page.evaluate(() => {
    document.getElementById('format-short').checked = false;
    document.getElementById('format-long').checked = false;
  });
  await click('save-button');
  await check(() => document.getElementById('form-error').textContent.includes('output format'), 'Format validation');
  await click('select-both');
  await input('project-id', '../escape');
  await click('save-button');
  await check(() => document.getElementById('form-error').textContent.includes('Project ID'), 'Unsafe ID rejected in UI');

  const story = 'Đây là câu chuyện thử nghiệm giao diện, không phải sự kiện có thật.\n\n'
    + 'Đêm ấy, cánh cửa cuối hành lang khẽ mở. “Có ai ở đó không?” Tôi hỏi.\n'
    + 'Một bóng cây lướt qua ô cửa; tiếng bước chân bỗng dừng lại.\n\n'
    + '<script>window.injected = true</script>';
  await input('title', '[TEST FIXTURE] Cánh cửa cuối hành lang');
  await input('project-id', 'fixture-vietnamese');
  await input('content', story);
  await page.evaluate(() => document.getElementById('form-error').hidden = true);
  await capture('p1-new-production.png');
  await page.evaluate(() => {
    window.originalFetch = window.fetch;
    window.fetch = async (resource, options) => {
      if (options?.method === 'POST') await new Promise(resolve => window.releaseSave = resolve);
      return window.originalFetch(resource, options);
    };
  });
  await click('save-button');
  await waitFor(() => Boolean(window.releaseSave), 'save pending');
  await check(() => document.getElementById('save-button').disabled
    && document.getElementById('save-button').textContent.includes('Saving'), 'Loading/disabled save');
  await page.evaluate(() => { window.releaseSave(); window.fetch = window.originalFetch; });
  await waitFor(() => !document.getElementById('save-success').hidden, 'saved story');
  await check(() => document.getElementById('save-success').textContent.includes('Production not started')
    && document.getElementById('save-success').textContent.includes('Short 9:16 + Long 16:9')
    && document.getElementById('save-success').textContent.includes('input/story.md'), 'Success, both formats and saved files');
  const saved = await page.evaluate(async () => (await fetch('/studio/api/productions/fixture-vietnamese')).json());
  assert.equal(saved.request.content, story);
  assert.equal(saved.request.style, 'stickman_horror_2d');
  assert.equal(saved.request.publishing_enabled, false);
  assert.equal(saved.production_started, false);
  findings.checks.push('Vietnamese content persisted exactly; style/review/publication locked');
  await capture('p1-saved-project.png');
  // The user's actual monitoring link, in a real second Chrome tab.
  await page.evaluate(() => document.querySelector('#save-success a').click());
  // The Remotion driver's pages() omits tabs it did not create, so attach to the opened target.
  let boardTarget;
  for (let i = 0; i < 100 && !boardTarget; i++) {
    boardTarget = browser.targets().find(t => t.type() === 'page' && t.url().includes('/p/fixture-vietnamese'));
    if (!boardTarget) await pause(50);
  }
  assert.ok(boardTarget, 'Backlot link opened a real tab');
  const board = await boardTarget.page({sourceMapGetter: () => null, logLevel: 'error', indent: false,
    pageIndex: 1, onBrowserLog: null, onLog: () => {}});
  assert.ok(await board.evaluate(async () => {
    const state = await (await fetch('/api/project/fixture-vietnamese/state')).json();
    return !state.has_pipeline_state && state.stages.every(s => s.status === 'pending');
  }));
  await board.close();
  findings.checks.push('Open Backlot: real board tab, all stages pending');
  await click('save-button');
  await waitFor(() => !document.getElementById('form-error').hidden, 'duplicate error');
  await check(() => document.getElementById('form-error').textContent.includes('already exists'), 'Duplicate request cannot overwrite');
  await click('list-tab');
  await waitFor(() => document.querySelectorAll('.production-card').length === 1, 'library card');
  await page.evaluate(() => document.querySelector('.card-actions button').click());
  await waitFor(() => !document.getElementById('production-detail').hidden, 'detail');
  await check(() => document.getElementById('detail-content').textContent.includes('<script>')
    && !document.getElementById('detail-content').querySelector('script') && !window.injected, 'XSS text stays literal in saved input');
  await capture('p1-my-productions.png');

  await click('new-tab');
  await input('project-id', 'fixture-upload');
  await input('title', '[TEST FIXTURE] Markdown tiếng Việt');
  await page.evaluate(() => {
    const file = new File(['# Dữ liệu thử nghiệm\r\n\r\n“Xin chào”, cô nói.\r\n'], 'truyện-fixture.md', {type: 'text/markdown'});
    const transfer = new DataTransfer(); transfer.items.add(file);
    document.getElementById('markdown-file').files = transfer.files;
    document.getElementById('markdown-file').dispatchEvent(new Event('change', {bubbles: true}));
  });
  await waitFor(() => document.getElementById('upload-name').textContent === 'truyện-fixture.md', 'Markdown upload');
  await click('save-button');
  await waitFor(() => !document.getElementById('save-success').hidden
    && document.getElementById('save-success').textContent.includes('fixture-upload'), 'uploaded save');
  const upload = await page.evaluate(async () => (await fetch('/studio/api/productions/fixture-upload')).json());
  assert.equal(upload.request.content, '# Dữ liệu thử nghiệm\r\n\r\n“Xin chào”, cô nói.\r\n');
  assert.equal(upload.request.source_filename, 'truyện-fixture.md');
  findings.checks.push('Real Markdown File API: Vietnamese + original CRLF preserved');

  await click('new-tab');
  await mode('topic');
  await input('project-id', 'fixture-topic');
  await input('content', 'Dữ liệu thử nghiệm: câu chuyện một ngọn hải đăng');
  await click('save-button');
  await waitFor(() => !document.getElementById('save-success').hidden, 'topic save');
  const topic = await page.evaluate(async () => (await fetch('/studio/api/productions/fixture-topic')).json());
  assert.equal(topic.request.input_readiness, 'unresearched_topic');
  findings.checks.push('Topic saved as unresearched input');

  await click('new-tab');
  await mode('canonical');
  await input('project-id', 'fixture-canonical');
  await page.evaluate(() => document.getElementById('canonical-package').value = 'test-canonical');
  await click('save-button');
  await waitFor(() => !document.getElementById('save-success').hidden, 'canonical save');
  const canonical = await page.evaluate(async () => (await fetch('/studio/api/productions/fixture-canonical')).json());
  assert.equal(canonical.request.content, null);
  assert.equal(canonical.request.canonical_package.package_id, 'STORY_999');
  findings.checks.push('Canonical fixture mode stores a reference only');

  await click('list-tab');
  await waitFor(() => document.querySelectorAll('.production-card').length === 4, 'all saved modes');
  await page.evaluate(() => {
    window.originalFetch = window.fetch;
    window.fetch = async () => new Response('{"detail":"fixture failure"}', {status: 503});
  });
  await click('refresh-list');
  await waitFor(() => document.getElementById('list-status').textContent.includes('Could not load'), 'list error');
  findings.checks.push('Library error state');
  await page.evaluate(() => {
    window.fetch = async (...args) => {
      await new Promise(resolve => window.releaseList = resolve);
      return window.originalFetch(...args);
    };
  });
  await click('refresh-list');
  await waitFor(() => Boolean(window.releaseList), 'list pending');
  await check(() => document.getElementById('list-status').textContent.includes('Loading'), 'Library loading state');
  await page.evaluate(() => { window.releaseList(); window.fetch = window.originalFetch; });
  await waitFor(() => document.querySelectorAll('.production-card').length === 4, 'library retry');
  findings.checks.push('Library retry recovers');

  await click('new-tab');
  await page.setViewport({width: 390, height: 844, deviceScaleFactor: 1});
  await check(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth, 'Mobile layout without horizontal overflow');
  await capture('p1-mobile.png');
  assert.deepEqual(findings.pageErrors, []);
  assert.deepEqual(findings.externalRequests, []);
  fs.writeFileSync(path.join(screenshots, 'browser-results.json'), JSON.stringify(findings, null, 2));
  console.log(JSON.stringify(findings, null, 2));
})().catch(async error => {
  console.error(error);
  if (page) await capture('failure.png').catch(() => {});
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close({silent: true});
});
