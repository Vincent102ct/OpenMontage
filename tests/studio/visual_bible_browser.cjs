/* Real Studio interactions with synthetic inputs only; separate story/visual approval actions. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {openBrowser} = require(require.resolve('@remotion/renderer', {paths: [path.resolve('remotion-composer')]}));
const [url, chrome, outDir] = process.argv.slice(2);
const findings = {checks: [], externalRequests: [], pageErrors: [], posts: []};
let browser, page;
const pause = ms => new Promise(r => setTimeout(r, ms));
async function wait(fn, label, seconds = 35) {
  const end = Date.now() + seconds * 1000;
  while (Date.now() < end) {if (await page.evaluate(fn)) {findings.checks.push(label); return;} await pause(80);}
  throw new Error(`Timeout: ${label}`);
}
const click = selector => page.evaluate(s => {const el = document.querySelector(s); assertElement(el); el.click();
  function assertElement(e) {if (!e || e.disabled) throw new Error(`Unavailable ${s}`);}}, selector);
const set = (label, value) => page.evaluate(({label, value}) => {const el = document.querySelector(`[aria-label="${label}"]`);
  if (!el || el.disabled) throw new Error(`Missing control ${label}`);
  if (el.type === 'checkbox') el.checked = value; else el.value = value;
  el.dispatchEvent(new Event('change', {bubbles: true}));}, {label, value});
async function screenshot(name) {
  await page.evaluate(() => document.getElementById('visual-bible-panel').scrollIntoView({block: 'start'}));
  await pause(150); const {value: shot} = await page._client().send('Page.captureScreenshot', {format: 'png'});
  fs.writeFileSync(path.join(outDir, name + '.png'), Buffer.from(shot.data, 'base64'));
}
async function visualApprove() {
  assert(await page.evaluate(() => document.getElementById('approve-visual-bible').disabled));
  await set('Approve visual design consent', true); await click('#approve-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('frozen'), 'Separate explicit visual approval freezes candidate');
}
(async () => {
  fs.mkdirSync(outDir, {recursive: true});
  browser = await openBrowser('chrome', {browserExecutable: chrome, logLevel: 'error'});
  page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0, onBrowserLog: null, onLog: () => {}});
  await page.setViewport({width: 1440, height: 1100, deviceScaleFactor: 1});
  page.on('error', e => findings.pageErrors.push(String(e)));
  page._client().on('Runtime.exceptionThrown', e => findings.pageErrors.push(e.exceptionDetails.text));
  await page._client().send('Network.enable');
  page._client().on('Network.requestWillBeSent', e => {
    if (e.request.method === 'POST') findings.posts.push(e.request.url);
    if (/^https?:/.test(e.request.url) && !e.request.url.startsWith(new URL(url).origin + '/')) findings.externalRequests.push(e.request.url);
  });
  await page.goto({url, timeout: 20000}); await click('#list-tab');
  await wait(() => document.querySelector('.open-visual-bible'), 'Production has a Visual Bible entry');
  await click('.open-visual-bible');
  await wait(() => document.getElementById('approve-reviewed-story') && document.getElementById('prepare-visual-bible'), 'Existing story and new visual workflows load');
  assert(await page.evaluate(() => document.getElementById('prepare-visual-bible').disabled));
  assert.equal(findings.posts.length, 0); findings.checks.push('Page loads do not prepare or approve anything');
  await screenshot('01-story-approval-required');
  await click('#reviewed-story-consent'); await click('#approve-reviewed-story');
  await wait(() => Boolean(document.getElementById('prepare-visual-bible')) && !document.getElementById('prepare-visual-bible').disabled, 'P2.3 explicit story approval enables visual preparation');
  await click('#prepare-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('v1'), 'Initial candidate is immutable v1');
  assert(await page.evaluate(() => document.getElementById('approve-visual-bible').disabled));
  await set('Environment LOC_ROOM', 'old_apartment_room@1'); await set('Lighting LOC_ROOM', 'cold_moonlight@1');
  await set('Environment LOC_HALL', 'dark_apartment_corridor@1'); await set('Lighting LOC_HALL', 'cold_moonlight@1');
  await set('Prop OBJ_DOOR', 'interior_door@1'); await set('Anchor OBJ_DOOR', 'doors.room_door.handle');
  await set('Prop OBJ_LAMP', 'ceiling_lamp@1'); await set('Anchor OBJ_LAMP', 'lamps.lamp_mid.bulb');
  for (const id of ['CHR_AN','CHR_BINH','LOC_ROOM','LOC_HALL','OBJ_DOOR','OBJ_LAMP']) await set('Review visual ' + id, true);
  await set('Review visual continuity', true); await click('#save-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('v2'), 'Edits create new version without overwriting v1');
  assert(await page.evaluate(() => document.querySelector('.visual-blockers').textContent.includes('INCOMPATIBLE_LIGHTING')
    && document.getElementById('approve-visual-bible').disabled));
  findings.checks.push('Incompatible corridor moonlight is a visible blocker, with no room fallback'); await screenshot('02-lighting-blocker');
  await set('Lighting LOC_HALL', 'dim_corridor@1'); await set('Review visual LOC_HALL', true); await click('#save-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('v3')
    && document.querySelector('.visual-blockers')?.textContent.includes('Visual blockers: 0'), 'Compatible reviewed bindings resolve all blockers');
  await screenshot('03-ready-for-visual-review');
  await click('#preview-visual-bible');
  await wait(() => document.querySelectorAll('#visual-reference-previews img').length === 10
    && [...document.querySelectorAll('#visual-reference-previews img')].every(i => i.complete && i.naturalWidth > 0), 'Ten real renderer reference PNGs load locally', 150);
  await page.evaluate(() => document.getElementById('visual-reference-previews').scrollIntoView({block:'start'}));
  await pause(150); const {value: shot} = await page._client().send('Page.captureScreenshot', {format:'png'});
  fs.writeFileSync(path.join(outDir, '04-reference-visuals.png'), Buffer.from(shot.data, 'base64'));
  await visualApprove(); await screenshot('05-approved-for-scene-planning');
  await set('Asset CHR_AN', 'victor_hale@1'); await set('Review visual CHR_AN', true); await click('#save-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('v4')
    && document.querySelector('.visual-blockers')?.textContent.includes('CONFLICTING_IDENTITY'), 'Conflicting identity creates blocked new version; old approval stays frozen');
  await set('Asset CHR_BINH', 'nora_vale@1'); await set('Review visual CHR_BINH', true); await click('#save-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('v5')
    && document.querySelector('.visual-blockers')?.textContent.includes('Visual blockers: 0'), 'Cross-environment recast is consistent but requires another approval');
  await visualApprove();
  await click('[data-target="AMB_SOURCE"][data-decision="preserve_ambiguity"]');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('STALE'), 'A new canonical decision invalidates visual readiness');
  assert(await page.evaluate(() => document.getElementById('prepare-visual-bible').disabled));
  await screenshot('06-stale-canon');
  await click('#materialize-reviewed-story');
  await wait(() => document.querySelector('.reviewed-status')?.textContent.includes('v3')
    && !document.getElementById('reviewed-story-consent').disabled, 'New canon requires another explicit story approval');
  await click('#reviewed-story-consent'); await click('#approve-reviewed-story');
  await wait(() => Boolean(document.getElementById('prepare-visual-bible')) && !document.getElementById('prepare-visual-bible').disabled, 'New current story approval restored');
  await click('#prepare-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('v6'), 'New canon creates fresh unapproved visual candidate');
  await set('Environment LOC_ROOM', 'old_apartment_room@1'); await set('Lighting LOC_ROOM', 'cold_moonlight@1');
  await set('Environment LOC_HALL', 'dark_apartment_corridor@1'); await set('Lighting LOC_HALL', 'dim_corridor@1');
  await set('Prop OBJ_DOOR', 'interior_door@1'); await set('Anchor OBJ_DOOR', 'doors.room_door.handle');
  await set('Prop OBJ_LAMP', 'ceiling_lamp@1'); await set('Anchor OBJ_LAMP', 'lamps.lamp_mid.bulb');
  for (const id of ['CHR_AN','CHR_BINH','LOC_ROOM','LOC_HALL','OBJ_DOOR','OBJ_LAMP']) await set('Review visual ' + id, true);
  await set('Review visual continuity', true); await click('#save-visual-bible');
  await wait(() => document.querySelector('.visual-status')?.textContent.includes('v7')
    && document.querySelector('.visual-blockers')?.textContent.includes('Visual blockers: 0'), 'Fresh canonical snapshot is ready for visual review');
  await visualApprove(); await screenshot('07-current-approved-visual-bible');
  assert.deepEqual(findings.externalRequests, []); assert.deepEqual(findings.pageErrors, []);
  fs.writeFileSync(path.join(outDir, 'visual-results.json'), JSON.stringify(findings, null, 2));
})().catch(e => {console.error(e); process.exitCode = 1;})
  .finally(async () => {if (browser) await browser.close({silent:true});});
