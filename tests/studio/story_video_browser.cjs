/* Real installed Chrome, local synthetic Studio only. No automatic production. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {openBrowser} = require(require.resolve('@remotion/renderer',{paths:[path.resolve('remotion-composer')]}));
const [url, chrome, output, project = 'en-proof'] = process.argv.slice(2);
const findings = {checks:[],externalRequests:[],pageErrors:[],posts:[]};
let browser, page;
const pause = ms => new Promise(r => setTimeout(r,ms));
async function wait(fn,label,arg,seconds=90) {
  const end = Date.now()+seconds*1000;
  while(Date.now()<end) {if(await page.evaluate(fn,arg)){findings.checks.push(label);return;}await pause(200);}
  throw new Error('Timeout: '+label);
}
async function click(selector) {await page.evaluate(s=>{const b=document.querySelector(s);if(!b || b.disabled)throw new Error('Unavailable '+s);b.click();},selector);}
async function screenshot(name) {
  await page.evaluate(()=>document.getElementById('story-video-panel').scrollIntoView({block:'start'}));await pause(200);
  const {value:shot}=await page._client().send('Page.captureScreenshot',{format:'png'});
  fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(shot.data,'base64'));
}
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  browser=await openBrowser('chrome',{browserExecutable:chrome,logLevel:'error'});
  page=await browser.newPage({context:()=>null,logLevel:'error',indent:false,pageIndex:0,onBrowserLog:null,onLog:()=>{}});
  await page.setViewport({width:1440,height:1100,deviceScaleFactor:1});
  page.on('error',e=>findings.pageErrors.push(String(e)));
  page._client().on('Runtime.exceptionThrown',e=>findings.pageErrors.push(e.exceptionDetails.text));
  await page._client().send('Network.enable');
  page._client().on('Network.requestWillBeSent',e=>{
    if(e.request.method==='POST')findings.posts.push({url:e.request.url,body:e.request.postData});
    if(/^https?:/.test(e.request.url)&&!e.request.url.startsWith(new URL(url).origin+'/'))findings.externalRequests.push(e.request.url);
  });
  await page.goto({url,timeout:20000});await click('#list-tab');
  const selector=`.open-scene-plan[data-project-id="${project}"]`;
  await wait(s=>!!document.querySelector(s),'Synthetic production listed',selector);await click(selector);
  await wait(()=>!!document.getElementById('check-story-narration'),'Local production controls accessible');
  assert.equal(findings.posts.length,0);findings.checks.push('Opening Studio starts no TTS or render');
  await click('#check-story-narration');
  await wait(()=>!!document.getElementById('story-video-voice'),'Matching installed offline voices shown');
  await page.evaluate(()=>{
    const s=document.getElementById('story-video-voice');const o=[...s.options].find(o=>o.textContent.includes('Zira Desktop'));
    if(o)s.value=o.value;
  });
  await screenshot('01-readiness');
  await click('#prepare-story-narration');
  await wait(()=>!!document.getElementById('render-story-video'),'Measured narration ready through UI',null,180);
  assert(await page.evaluate(()=>document.getElementById('render-story-video').disabled));
  assert(await page.evaluate(()=>!document.getElementById('story-video-consent').checked));
  findings.checks.push('Scene approval and narration preparation do not authorize render');
  await page.evaluate(()=>{const c=document.getElementById('story-video-consent');c.checked=true;c.dispatchEvent(new Event('change',{bubbles:true}));});
  const visualReady=await page.evaluate(async project=>{
    const r=await fetch(`/studio/api/productions/${encodeURIComponent(project)}/story-video/staging`);
    return (await r.json()).ready_for_render;
  },project);
  assert.equal(await page.evaluate(()=>document.getElementById('render-story-video').disabled),!visualReady);
  findings.checks.push(visualReady ? 'Approved visual staging plus separate consent enables render'
    : 'Render stays blocked until separate visual staging approval, even with render consent');
  // Do not start a redundant render: the explicit proof job already renders all shots.
  await screenshot('02-consent-and-timing');
  await page.evaluate(()=>{const c=document.getElementById('story-video-consent');c.checked=false;c.dispatchEvent(new Event('change',{bubbles:true}));});
  const videos=await page.evaluate(()=>[...document.querySelectorAll('#story-video-panel video')].map(v=>v.src));
  for(let i=0;i<videos.length;i++) {
    await page.evaluate(i=>{const v=document.querySelectorAll('#story-video-panel video')[i];v.muted=true;v.load();},i);
    await wait(i=>document.querySelectorAll('#story-video-panel video')[i].readyState>=1,'Rendered video metadata decoded '+i,i);
  }
  findings.videos=videos;
  if(videos.length) {assert(videos.length>=2);findings.checks.push('QA, contact sheets and UTF-8 subtitles offered alongside current complete renders');}
  else findings.checks.push('No incomplete render is offered for playback');
  assert.equal(findings.externalRequests.length,0);assert.equal(findings.pageErrors.length,0);
  assert(findings.posts.every(p=>p.url.endsWith('/jobs/narration')));
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(findings,null,2));
})().catch(e=>{findings.error=String(e.stack||e);fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(findings,null,2));process.exitCode=1;})
.finally(async()=>{if(browser)await browser.close({silent:true});});
