// P3.2A: real Chrome playback of the rendered MP4s plus Remotion stills from the current sources.
// Usage: node tests/tools/asset_library_browser.cjs projects/p32a-asset-library
// Reads <library>/stills.json {entry, publicDir, playback:[{mp4,width,height}], stills:[{name,props,frame}]}.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const resolve = name => require(require.resolve(name, {paths: [path.resolve('remotion-composer')]}));
const {openBrowser, selectComposition, renderStill} = resolve('@remotion/renderer');
const {bundle} = resolve('@remotion/bundler');
const library = path.resolve(process.argv[2]);
const spec = JSON.parse(fs.readFileSync(path.join(library, 'stills.json'), 'utf8'));
const chrome = process.env.REMOTION_BROWSER_EXECUTABLE || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
let browser;

async function play(mp4, width, height) {
  const bytes = fs.readFileSync(mp4);
  const server = http.createServer((req, res) => {
    if (req.url === '/v.mp4') {res.writeHead(200, {'Content-Type': 'video/mp4', 'Content-Length': bytes.length}); res.end(bytes);}
    else {res.writeHead(200, {'Content-Type': 'text/html'}); res.end('<!doctype html><video id="v" muted playsinline src="/v.mp4"></video>');}
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0, onBrowserLog: null, onLog: () => {}});
  const external = [];
  await page._client().send('Network.enable');
  page._client().on('Network.requestWillBeSent', e => {
    if (/^https?:/.test(e.request.url) && !e.request.url.startsWith(origin + '/')) external.push(e.request.url);
  });
  await page.goto({url: origin, timeout: 20000});
  const q = await page.evaluate(async () => new Promise(async (ok, fail) => {
    const v = document.getElementById('v'), timer = setTimeout(() => fail(new Error('Playback timed out')), 25000);
    v.onerror = () => fail(new Error(`Media error ${v.error?.code}`));
    v.onended = () => {clearTimeout(timer); const p = v.getVideoPlaybackQuality();
      ok({width: v.videoWidth, height: v.videoHeight, duration: v.duration, currentTime: v.currentTime,
        decodedFrames: p.totalVideoFrames, droppedFrames: p.droppedVideoFrames, ended: v.ended});};
    try {await v.play();} catch (e) {clearTimeout(timer); fail(e);}
  }));
  await page.close();
  server.closeAllConnections();  // Chrome keeps the media socket alive; close() alone would wait forever.
  await new Promise(r => server.close(r));
  assert.equal(q.width, width); assert.equal(q.height, height);
  assert(q.ended && q.currentTime >= 10 && q.decodedFrames >= 295 && q.droppedFrames === 0);
  assert.equal(external.length, 0);
  return {mp4: path.relative(process.cwd(), mp4), ...q, externalRequests: external};
}

(async () => {
  browser = await openBrowser('chrome', {browserExecutable: chrome, logLevel: 'error'});
  const playback = [];
  for (const p of spec.playback) playback.push(await play(path.resolve(p.mp4), p.width, p.height));
  const serveUrl = await bundle({entryPoint: path.resolve(spec.entry), publicDir: path.resolve(spec.publicDir),
    outDir: path.join(library, 'qa-bundle'), enableCaching: true, gitSource: null});
  const stills = [];
  fs.mkdirSync(path.join(library, 'stills'), {recursive: true});
  for (const s of spec.stills) {
    const composition = await selectComposition({serveUrl, id: 'StoryVideo', inputProps: s.props,
      puppeteerInstance: browser, browserExecutable: chrome, logLevel: 'error'});
    const output = path.join(library, 'stills', `${s.name}.png`);
    await renderStill({serveUrl, composition, inputProps: s.props, frame: s.frame, output, imageFormat: 'png',
      puppeteerInstance: browser, browserExecutable: chrome, logLevel: 'error'});
    stills.push({name: s.name, frame: s.frame, width: composition.width, height: composition.height, compositionId: composition.id});
  }
  const report = {playback, stills};
  fs.writeFileSync(path.join(library, 'chrome-qa.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({playback: playback.length, stills: stills.length}));
})().catch(e => {console.error(e); process.exitCode = 1;}).finally(async () => {
  if (browser) await browser.close({silent: true});
});
