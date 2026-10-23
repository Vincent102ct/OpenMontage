// Local Chrome playback and actual default 16:9 composition regression.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const resolve = name => require(require.resolve(name, {paths:[path.resolve('remotion-composer')]}));
const {openBrowser, selectComposition, renderStill} = resolve('@remotion/renderer');
const {bundle} = resolve('@remotion/bundler');
const project = path.resolve('projects/p30-stickman-horror-preview');
const chrome = process.env.REMOTION_BROWSER_EXECUTABLE || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
let browser, server;
(async () => {
  const bytes = fs.readFileSync(path.join(project,'preview.mp4'));
  server = http.createServer((req,res) => {
    if (req.url === '/preview.mp4') {
      res.writeHead(200,{'Content-Type':'video/mp4','Content-Length':bytes.length}); res.end(bytes);
    } else {res.writeHead(200,{'Content-Type':'text/html'}); res.end('<!doctype html><video id="v" muted playsinline src="/preview.mp4"></video>');}
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  browser = await openBrowser('chrome',{browserExecutable:chrome,logLevel:'error'});
  const page = await browser.newPage({context:()=>null,logLevel:'error',indent:false,pageIndex:0,onBrowserLog:null,onLog:()=>{}});
  const external = [];
  await page._client().send('Network.enable');
  page._client().on('Network.requestWillBeSent',e => {
    if (/^https?:/.test(e.request.url) && !e.request.url.startsWith(origin+'/')) external.push(e.request.url);
  });
  await page.goto({url:origin,timeout:20000});
  const playback = await page.evaluate(async () => {
    const v = document.getElementById('v');
    return await new Promise(async (resolve,reject) => {
      const timeout = setTimeout(()=>reject(new Error('Playback timed out')),25000);
      v.onerror = () => reject(new Error(`Media error ${v.error?.code}`));
      v.onended = () => {
        clearTimeout(timeout);
        const q=v.getVideoPlaybackQuality();
        resolve({width:v.videoWidth,height:v.videoHeight,duration:v.duration,currentTime:v.currentTime,
          decodedFrames:q.totalVideoFrames,droppedFrames:q.droppedVideoFrames,ended:v.ended});
      };
      try {await v.play();} catch(e) {clearTimeout(timeout);reject(e);}
    });
  });
  assert.equal(playback.width,720); assert.equal(playback.height,1280);
  assert(playback.ended && playback.currentTime >= 10 && playback.decodedFrames >= 295);
  assert.equal(external.length,0);
  await page.close();
  const props = JSON.parse(fs.readFileSync(path.join(project,'remotion/props.json')));
  delete props.viewport; delete props.character_skin;
  props.shots[0].camera = [[0,640,360,1],[10,640,360,1]];
  const serveUrl = await bundle({entryPoint:path.resolve('remotion-composer/projects/p30-stickman-horror-preview/index.tsx'),
    publicDir:path.join(project,'remotion/public'),outDir:path.join(project,'qa-bundle'),
    enableCaching:true,gitSource:null});
  const composition = await selectComposition({serveUrl,id:'StoryVideo',inputProps:props,
    puppeteerInstance:browser,browserExecutable:chrome,logLevel:'error'});
  assert.equal(composition.width,1280); assert.equal(composition.height,720);
  await renderStill({serveUrl,composition,inputProps:props,frame:156,
    output:path.join(project,'horizontal-cartoon.png'),imageFormat:'png',
    puppeteerInstance:browser,browserExecutable:chrome,logLevel:'error'});
  const report = {playback,externalRequests:external,horizontal:{width:composition.width,
    height:composition.height,frame:156,defaultSkin:'cartoon',actualStill:'horizontal-cartoon.png'}};
  fs.writeFileSync(path.join(project,'chrome-qa.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(browser) await browser.close({silent:true});
  if(server) await new Promise(resolve=>server.close(resolve));
});
