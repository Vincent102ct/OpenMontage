/* P2.2 review flow in real Chrome against a temporary fixture workspace. No rendering APIs are called. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {openBrowser} = require(require.resolve('@remotion/renderer', {paths: [path.resolve('remotion-composer')]}));

const [url, chrome, outDir, draftPath, projectId] = process.argv.slice(2);
const findings = {checks: [], externalRequests: [], pageErrors: [], posts: []};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let browser;
let page;

async function waitFor(fn, label, arg) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn, arg)) return;
    await pause(60);
  }
  throw new Error(`Timed out: ${label}`);
}
async function check(fn, label, arg) {
  assert.ok(await page.evaluate(fn, arg), label);
  findings.checks.push(label);
}
const status = target => page.evaluate(t => document.querySelector(`#review-panel [data-target="${t}"] .decision-chip`)
  ?.textContent, target);
async function click(target, decision) {
  await page.evaluate((t, d) => document.querySelector(
    `#review-panel .decision-button[data-target="${t}"][data-decision="${d}"]`).click(), target, decision);
}
async function capture(name) {
  const {value: m} = await page._client().send('Page.getLayoutMetrics');
  const {value: r} = await page._client().send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true,
    clip: {x: 0, y: 0, width: m.cssContentSize.width, height: Math.min(m.cssContentSize.height, 6000), scale: 1}});
  fs.writeFileSync(path.join(outDir, name), Buffer.from(r.data, 'base64'));
}

(async () => {
  fs.mkdirSync(outDir, {recursive: true});
  browser = await openBrowser('chrome', {browserExecutable: chrome, logLevel: 'error'});
  page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0,
    onBrowserLog: null, onLog: () => {}});
  page.on('error', error => findings.pageErrors.push(String(error)));
  await page.setViewport({width: 1440, height: 1000, deviceScaleFactor: 1});
  await page._client().send('Network.enable');
  page._client().on('Network.requestWillBeSent', event => {
    const u = event.request.url;
    if (event.request.method === 'POST') findings.posts.push(u);
    if (/^(https?|wss?):/.test(u) && !u.startsWith(new URL(url).origin + '/')) findings.externalRequests.push(u);
  });
  await page.goto({url, timeout: 20000});
  await page.evaluate(() => document.getElementById('list-tab').click());
  await waitFor(id => Boolean(document.querySelector(`.open-review[data-project-id="${id}"]`)), 'card', projectId);
  await pause(500);  // Let the initial page-load list request finish too; overlapping loads must not duplicate cards.
  await check(id => document.querySelectorAll(`.open-review[data-project-id="${id}"]`).length === 1,
    'Each production is listed once', projectId);
  await page.evaluate(id => document.querySelector(`.open-review[data-project-id="${id}"]`).click(), projectId);
  await waitFor(() => document.getElementById('review-panel').textContent.includes('Import Story Bible draft'), 'review');
  await check(() => {
    const text = document.getElementById('review-panel').textContent;
    return text.includes('Review status: Pending human review') && text.includes('No fiction Story Bible package')
      && text.includes('Original story (read-only)') && text.includes('Proposed working text');
  }, 'Review before import: pending, missing package listed, original and working text');
  assert.equal(findings.posts.length, 0);
  findings.checks.push('Opening the review sent no POST');

  const {value: doc} = await page._client().send('DOM.getDocument', {depth: 0});
  const {value: q} = await page._client().send('DOM.querySelector', {nodeId: doc.root.nodeId, selector: '#bible-draft-file'});
  await page._client().send('DOM.setFileInputFiles', {nodeId: q.nodeId, files: [draftPath]});
  await waitFor(() => document.getElementById('review-panel').textContent.includes('Story Bible · '), 'package');
  await check(() => {
    const text = document.getElementById('review-panel').textContent;
    return text.includes('FIC_TEST_FIXTURE') && text.includes('Authored proposal, not source text')
      && text.includes('Verbatim source text') && text.includes('Estimate only, pending TTS measurement');
  }, 'Imported package shows verbatim vs authored narration and duration estimate');

  await click('CHG_0001', 'accept');
  await waitFor(() => document.querySelector('#review-panel [data-target="CHG_0001"] .decision-chip')
    ?.textContent === 'Accepted', 'accepted');
  findings.checks.push('Accept recorded');
  await click('CHG_0001', 'reject');
  await waitFor(() => document.querySelector('#review-panel [data-target="CHG_0001"] .decision-chip')
    ?.textContent === 'Rejected', 'rejected');
  await check(() => document.querySelector('#review-panel [data-target="CHG_0001"]').textContent
    .includes('2 decisions recorded'), 'Changing a decision supersedes it explicitly and keeps history');

  await click('AMB_WRITER', 'answer');
  await waitFor(() => document.getElementById('review-panel').textContent.includes('An empty answer is not recorded'), 'empty');
  assert.equal(await status('AMB_WRITER'), 'Open (unresolved)');
  findings.checks.push('Empty answer refused; question stays unresolved');
  await page.evaluate(() => {
    const box = document.querySelector('#review-panel [data-target="AMB_WRITER"] textarea');
    box.value = 'Chưa xác định; giữ bí ẩn.';
  });
  await click('AMB_WRITER', 'answer');
  await waitFor(() => document.querySelector('#review-panel [data-target="AMB_WRITER"] .decision-chip')
    ?.textContent === 'Answered', 'answered');
  await check(() => document.querySelector('#review-panel [data-target="AMB_WRITER"]').textContent
    .includes('Recorded answer: Chưa xác định; giữ bí ẩn.'), 'Vietnamese answer recorded');
  await click('FMT_SHORT', 'defer');
  await waitFor(() => document.querySelector('#review-panel [data-target="FMT_SHORT"] .decision-chip')
    ?.textContent === 'Deferred', 'deferred');
  findings.checks.push('Defer recorded on the Short draft');
  await check(() => document.getElementById('review-panel').textContent.includes('Review status: Pending human review'),
    'Review stays pending while items are open');
  await capture('p22-story-review.png');
  assert.deepEqual(findings.pageErrors, []);
  assert.deepEqual(findings.externalRequests, []);
  fs.writeFileSync(path.join(outDir, 'review-results.json'), JSON.stringify(findings, null, 2));
})().catch(async error => {
  console.error(error);
  if (page) await capture('review-failure.png').catch(() => {});
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close({silent: true});
});
