/* P2.3 real Chrome, synthetic workspace only. No production or external requests. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {openBrowser} = require(require.resolve('@remotion/renderer', {paths: [path.resolve('remotion-composer')]}));
const [url, chrome, outDir, , projectId] = process.argv.slice(2);
const findings = {checks: [], externalRequests: [], pageErrors: [], posts: []};
let browser, page;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitFor(fn, label) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    if (await page.evaluate(fn)) { findings.checks.push(label); return; }
    await pause(80);
  }
  throw new Error(`Timed out: ${label}`);
}
async function click(selector) { await page.evaluate(s => document.querySelector(s).click(), selector); }
async function approve() {
  assert.ok(await page.evaluate(() => document.getElementById('approve-reviewed-story').disabled));
  await click('#reviewed-story-consent');
  await click('#approve-reviewed-story');
  await waitFor(() => document.querySelector('.reviewed-status')?.textContent.includes('frozen'), 'Explicit approval freezes version');
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
  await click('#list-tab');
  await waitFor(() => Boolean(document.querySelector('.open-review')), 'Synthetic production visible');
  await page.evaluate(id => document.querySelector(`.open-review[data-project-id="${id}"]`).click(), projectId);
  await waitFor(() => document.getElementById('materialize-reviewed-story'), 'Opening review does not materialize');
  assert.equal(findings.posts.length, 0);
  await click('#materialize-reviewed-story');
  await waitFor(() => document.querySelector('.reviewed-status')?.textContent.includes('v2'), 'Blocked candidate v2 saved');
  assert.ok(await page.evaluate(() => document.getElementById('approve-reviewed-story').disabled
    && document.getElementById('reviewed-story-consent').disabled
    && document.querySelector('.reviewed-blockers').textContent.includes('AMB_WRITER')));
  findings.checks.push('Unresolved question blocks approval with explanation');
  await click('[data-target="AMB_WRITER"][data-decision="preserve_ambiguity"]');
  await waitFor(() => document.querySelector('[data-target="AMB_WRITER"] .decision-chip')?.textContent
    === 'Intentionally unresolved', 'Preserve Ambiguity recorded explicitly');
  await waitFor(() => document.querySelector('.reviewed-status')?.textContent.includes('Decisions changed'), 'Old snapshot cannot be approved after decisions change');
  await click('#materialize-reviewed-story');
  await waitFor(() => document.querySelector('.reviewed-status')?.textContent.includes('v3'), 'New reviewed version v3');
  assert.ok(await page.evaluate(() => document.querySelector('.reviewed-blockers').textContent.includes('Remaining blockers: 0')
    && document.querySelector('.reviewed-hashes').textContent.includes('Package SHA-256:')
    && document.querySelector('.reviewed-hashes').textContent.includes('Manifest SHA-256:')
    && document.getElementById('reviewed-story-panel').textContent.includes('Intentionally unresolved questions')
    && document.getElementById('reviewed-story-panel').textContent.includes('Short 9:16')
    && document.getElementById('reviewed-story-panel').textContent.includes('Long 16:9')));
  findings.checks.push('Approval preview shows hashes, ambiguity, decisions and both plans');
  assert.equal(findings.posts.filter(p => p.endsWith('/approve')).length, 0);
  await approve();
  await page.evaluate(() => { document.querySelector('[data-target="AMB_WRITER"] textarea').value = 'A recorded human interpretation, without rewriting the source.'; });
  await click('[data-target="AMB_WRITER"][data-decision="answer"]');
  await waitFor(() => document.querySelector('.reviewed-status')?.textContent.includes('Decisions changed'), 'Frozen approval remains historical after a new decision');
  await click('#materialize-reviewed-story');
  await waitFor(() => document.querySelector('.reviewed-status')?.textContent.includes('v4')
    && document.querySelector('.reviewed-status').textContent.includes('Awaiting explicit approval'), 'v4 requires fresh approval');
  await approve();
  assert.deepEqual(findings.externalRequests, []);
  assert.deepEqual(findings.pageErrors, []);
  assert.equal(findings.posts.filter(p => p.endsWith('/approve')).length, 2);
  await page.evaluate(() => document.getElementById('reviewed-story-panel').scrollIntoView({block: 'start'}));
  await pause(200);
  const {value: shot} = await page._client().send('Page.captureScreenshot', {format: 'png'});
  fs.writeFileSync(path.join(outDir, 'p23-reviewed-story.png'), Buffer.from(shot.data, 'base64'));
  fs.writeFileSync(path.join(outDir, 'review-results.json'), JSON.stringify(findings, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; })
  .finally(async () => { if (browser) await browser.close({silent: true}); });
