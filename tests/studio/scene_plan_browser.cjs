/* Real Studio scene-plan review with synthetic inputs only; every approval is an explicit UI action. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {openBrowser} = require(require.resolve('@remotion/renderer', {paths: [path.resolve('remotion-composer')]}));
const [url, chrome, outDir] = process.argv.slice(2);
const findings = {checks: [], externalRequests: [], pageErrors: [], posts: []};
let browser, page;
const pause = ms => new Promise(r => setTimeout(r, ms));
async function wait(fn, label, arg, seconds = 60) {
  const end = Date.now() + seconds * 1000;
  while (Date.now() < end) {if (await page.evaluate(fn, arg)) {findings.checks.push(label); return;} await pause(100);}
  throw new Error(`Timeout: ${label}`);
}
const click = selector => page.evaluate(s => {const el = document.querySelector(s);
  if (!el || el.disabled) throw new Error(`Unavailable ${s}`); el.click();}, selector);
const set = (label, value) => page.evaluate(({label, value}) => {const el = document.querySelector(`[aria-label="${label}"]`);
  if (!el || el.disabled) throw new Error(`Missing control ${label}`);
  if (el.type === 'checkbox') el.checked = value; else {
    if (![...el.options].some(o => o.value === value)) throw new Error(`No option ${value} for ${label}`); el.value = value;}
  el.dispatchEvent(new Event('change', {bubbles: true}));}, {label, value});
const status = () => page.evaluate(() => document.querySelector('.scene-status')?.textContent || '');
const blockers = () => page.evaluate(() => [...document.querySelectorAll('.scene-blockers li')].map(li => li.textContent));
async function atVersion(v) {
  await wait(v => (document.querySelector('.scene-status')?.textContent || '').startsWith(v), `Scene plan ${v} rendered`, v);
}
async function screenshot(name, selector = '#scene-plan-panel') {
  await page.evaluate(s => document.querySelector(s).scrollIntoView({block: 'start'}), selector);
  await pause(200); const {value: shot} = await page._client().send('Page.captureScreenshot', {format: 'png'});
  fs.writeFileSync(path.join(outDir, name + '.png'), Buffer.from(shot.data, 'base64'));
}
const openShot = id => page.evaluate(id => {const d = document.querySelector(`[data-shot="${id}"]`); d.open = true;}, id);
const SCENES = ['SC_S_01', 'SC_S_02', 'SC_S_03', 'SC_L_01', 'SC_L_02', 'SC_L_03', 'SC_L_04', 'SC_L_05', 'SC_L_06'];
const EDITORIAL = ['SH_L_004', 'SH_L_007', 'SH_L_011', 'SH_L_018', 'SH_S_005', 'SH_S_012'];
async function reviewAll() {
  for (const id of EDITORIAL) await set(`Editorial ${id}`, true);
  for (const id of SCENES) await set(`Review scene ${id}`, true);
  await set('Review scene-plan coverage', true); await set('Review scene-plan continuity', true);
}
async function approveCurrent() {
  assert(await page.evaluate(() => document.getElementById('approve-scene-plan').disabled));
  await set('Approve scene plan consent', true); await click('#approve-scene-plan');
  await wait(() => (document.querySelector('.scene-status')?.textContent || '').includes('frozen'), 'Separate explicit scene-plan approval freezes the version');
}
(async () => {
  fs.mkdirSync(outDir, {recursive: true});
  browser = await openBrowser('chrome', {browserExecutable: chrome, logLevel: 'error'});
  page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0, onBrowserLog: null, onLog: () => {}});
  await page.setViewport({width: 1440, height: 1200, deviceScaleFactor: 1});
  page.on('error', e => findings.pageErrors.push(String(e)));
  page._client().on('Runtime.exceptionThrown', e => findings.pageErrors.push(e.exceptionDetails.text));
  await page._client().send('Network.enable');
  page._client().on('Network.requestWillBeSent', e => {
    if (e.request.method === 'POST') findings.posts.push(e.request.url);
    if (/^https?:/.test(e.request.url) && !e.request.url.startsWith(new URL(url).origin + '/')) findings.externalRequests.push(e.request.url);
  });
  await page.goto({url, timeout: 20000}); await click('#list-tab');
  await wait(() => document.querySelector('.open-scene-plan'), 'Production offers a Scene Plans entry');
  await click('.open-scene-plan');
  await wait(() => document.getElementById('prepare-scene-plan') && !document.getElementById('prepare-scene-plan').disabled,
    'Approved story + Visual Bible enable Prepare Scene Plans');
  assert.equal(findings.posts.length, 0); findings.checks.push('Page loads do not prepare or approve anything');
  await screenshot('01-ready-to-prepare');
  // 1. Immutable candidate with honest capability gaps.
  await click('#prepare-scene-plan'); await atVersion('v1');
  assert(await page.evaluate(() => document.getElementById('approve-scene-plan').disabled));
  assert((await blockers()).some(b => b.includes('DLG_WHO') && b.includes('REQUIRES_NEW_CAPABILITY')));
  assert(await page.evaluate(() => document.querySelectorAll('[data-format="long"] .shot-row[data-shot^="SH_L_"]').length === 20
    && document.querySelectorAll('[data-format="short"] .shot-row').length === 13));
  findings.checks.push('Short and Long show every chapter, scene and shot; lip-sync gap is a blocker');
  await openShot('SH_L_004'); await screenshot('02-v1-shots-and-capability', '[data-shot="SH_L_004"]');
  // 2. Request what the reviewed staging describes; unsupported actions become explicit blockers.
  await set('Interaction SH_L_007 OBJ_ROOM_DOOR', 'open_door'); await set('Interaction SH_S_005 OBJ_ROOM_DOOR', 'open_door');
  await set('Performance SH_L_014 CHR_OWEN', 'grasp_object');
  assert(await page.evaluate(() => document.getElementById('approve-scene-plan').disabled));
  await click('#save-scene-plan'); await atVersion('v2');
  const gaps = (await blockers()).filter(b => b.includes('REQUIRES_NEW_CAPABILITY'));
  assert.equal(gaps.length, 5, gaps.join('\n')); findings.checks.push('Door opening, grasp and lip-sync are explicit capability blockers');
  await openShot('SH_L_007'); await screenshot('03-capability-blockers', '[data-shot="SH_L_007"]');
  // 3. Supported/editorial alternatives without deleting or rewriting any beat.
  await set('Interaction SH_L_007 OBJ_ROOM_DOOR', 'reach_then_opened_across_cut');
  await set('Interaction SH_S_005 OBJ_ROOM_DOOR', 'reach_then_opened_across_cut');
  await set('Interaction SH_L_018 OBJ_ROOM_DOOR', 'door_closed_across_cut');
  await set('Interaction SH_S_012 OBJ_ROOM_DOOR', 'door_closed_across_cut');
  await set('Performance SH_L_014 CHR_OWEN', 'startled_reaction');
  await set('Dialogue SH_L_004 DLG_WHO', 'voice_over_narration'); await set('Dialogue SH_L_011 DLG_HEARD', 'voice_over_narration');
  await set('Transition SC_L_02', 'continuous');
  await click('#save-scene-plan'); await atVersion('v3');
  assert(!(await blockers()).some(b => b.includes('REQUIRES_NEW_CAPABILITY')));
  assert((await blockers()).some(b => b.includes('EDITORIAL_REVIEW')));
  findings.checks.push('Alternatives clear capability gaps; editorial representations still need acknowledgement');
  await reviewAll(); await click('#save-scene-plan'); await atVersion('v4');
  assert.equal((await blockers()).length, 0, (await blockers()).join('\n'));
  findings.checks.push('All scenes, coverage, continuity and editorial choices explicitly reviewed: zero blockers');
  await openShot('SH_L_007'); await screenshot('04-resolved-shot', '[data-shot="SH_L_007"]');
  await click('#scene-report-button');
  await wait(() => (document.getElementById('scene-report')?.textContent || '').includes('Retained story text narrated'), 'Coverage report shown');
  await screenshot('05-coverage-report', '#scene-report');
  await approveCurrent(); await screenshot('06-approved-scene-plan');
  // 4. A new Visual Bible version makes the approved plan stale.
  await set('Flicker lamp LOC_HALL', 'lamp_west'); await set('Review visual LOC_HALL', true); await click('#save-visual-bible');
  await wait(() => (document.querySelector('.visual-status')?.textContent || '').startsWith('v3'), 'New Visual Bible candidate saved');
  await click('#refresh-scene-plan');
  await wait(() => (document.querySelector('.scene-status')?.textContent || '').includes('STALE'), 'Approved plan is stale after the visual change');
  assert(await page.evaluate(() => document.getElementById('prepare-scene-plan').disabled));
  await screenshot('07-stale-after-visual-change');
  await set('Approve visual design consent', true); await click('#approve-visual-bible');
  await wait(() => (document.querySelector('.visual-status')?.textContent || '').includes('frozen'), 'New Visual Bible explicitly approved');
  await click('#refresh-scene-plan');
  await wait(() => document.getElementById('prepare-scene-plan') && !document.getElementById('prepare-scene-plan').disabled, 'Preparation re-enabled');
  await click('#prepare-scene-plan'); await atVersion('v5');
  assert((await blockers()).some(b => b.includes('UNREVIEWED_SCENE')));
  findings.checks.push('Rebased plan keeps staging but requires fresh review');
  await screenshot('08-rebased-requires-review');
  await reviewAll(); await click('#save-scene-plan'); await atVersion('v6');
  assert.equal((await blockers()).length, 0); await approveCurrent();
  await screenshot('09-reapproved-current-plan');
  fs.writeFileSync(path.join(outDir, 'scene-plan-results.json'), JSON.stringify(findings, null, 2));
  await browser.close({silent: true});
})().catch(async error => {
  findings.error = String(error.stack || error);
  fs.mkdirSync(outDir, {recursive: true});
  fs.writeFileSync(path.join(outDir, 'scene-plan-results.json'), JSON.stringify(findings, null, 2));
  try {await screenshot('99-failure');} catch {}
  if (browser) await browser.close({silent: true});
  console.error(error); process.exit(1);
});
