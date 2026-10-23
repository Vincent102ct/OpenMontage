// Exercise the actual rig and artwork at every output frame, plus the legacy checks.
const fs = require('fs'), path = require('path'), Module = require('module');
const assert = require('node:assert/strict'), cp = require('node:child_process');
const crypto = require('node:crypto');
const baseline = JSON.parse(cp.execFileSync(process.execPath,
  ['tests/tools/stickman_frame_checks.cjs',process.argv[2],
    ...(JSON.parse(fs.readFileSync(process.argv[2],'utf8')).horror ? ['--allow-door-crop'] : [])], {encoding:'utf8'}));
const nm = path.resolve('remotion-composer/node_modules');
const ts = require(path.join(nm,'typescript'));
for (const ext of ['.ts','.tsx']) Module._extensions[ext] = (m,f) => {
  m.paths.push(nm);
  m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'), {compilerOptions:{
    module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true,
  }}).outputText,f);
};
const React = require(path.join(nm,'react'));
const {renderToStaticMarkup} = require(path.join(nm,'react-dom/server'));
const {actorState,doorHandle} = require(path.resolve('tools/character/remotion/StoryVideo.tsx'));
const {ActorBody,ActorHands} = require(path.resolve('tools/character/remotion/Actor.tsx'));
const {sample} = require(path.resolve('tools/character/remotion/motion.ts'));
const video = JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const shot=video.shots[0], actor=shot.actors[0], door=video.locations[shot.location].door;
assert.equal(video.character_skin,'cartoon_horror');
let contactFrames=0, maxPostContactDrift=0;
for(let frame=0;frame<300;frame++) {
  const t=frame/30,s=actorState(actor,t),[cx,cy,z]=sample(shot.camera,t),scale=1280/720*z;
  // Include shoes, clothing thickness, elbows and the tilted hair silhouette.
  for(const p of [[s.head[0]-48,s.head[1]-57],[s.head[0]+48,s.head[1]+47],
    [s.hip[0]-28,s.hip[1]+12],s.le,s.re,
    ...(actor.look.treatment==='cinematic' ? [[s.le[0]-12,s.le[1]],[s.re[0]+12,s.re[1]]] : []),
    [s.lf[0]-14,s.lf[1]+9],[s.rf[0]+27,s.rf[1]+9],
    [s.left[0]-15,s.left[1]-15],[s.right[0]+15,s.right[1]+15]]) {
    const x=360+(p[0]-cx)*scale,y=640+(p[1]-cy)*scale;
    assert(x>16 && x<704 && y>40 && y<1240,`Cartoon clipped: frame ${frame} (${x},${y})`);
  }
  const svg=renderToStaticMarkup(React.createElement('svg',null,
    React.createElement(ActorBody,{s,look:actor.look,t,skin:video.character_skin}),
    React.createElement(ActorHands,{s,look:actor.look,skin:video.character_skin})));
  assert(svg.includes('data-skin="cartoon_horror"') && svg.includes(actor.look.shirt));
  assert(svg.includes('data-part="hair"') && svg.includes('data-part="face"'));
  assert(!svg.includes('NaN') && !svg.includes('Infinity'));
  if(t>=9.35) {
    const knob=doorHandle(door,0), screenX=360+(knob[0]-cx)*scale;
    assert(screenX>30 && screenX<690,'Door contact cropped');
    const error=Math.hypot(...s.right.map((v,i)=>v-doorHandle(door,0)[i]));
    maxPostContactDrift=Math.max(maxPostContactDrift,error);contactFrames++;
    assert(error<.001,'Hand misses the real door handle');
    for(const limb of ['left_foot','right_foot'])
      assert.deepEqual(sample(actor[limb],t),sample(actor[limb],8.4),'Foot slides during reach');
  }
}
assert(actorState(actor,1.6).shoulder[0]<actorState(actor,1.2).shoulder[0]-8,'Recoil missing');
assert(actorState(actor,1.6).face[3]<-.65,'Gasp missing');
assert(actorState(actor,9.7).head[0]>actorState(actor,8.4).head[0]+4,'Reach lean missing');
assert.deepEqual(actorState(actor,5.2),actorState(actor,5.2),'Seek changed state');
if(actor.look.treatment==='cinematic') {
  // The freeze is real world-space contact, not a hold added only in an edit report.
  for(const limb of ['root','left_foot','right_foot'])
    assert.deepEqual(sample(actor[limb],6.4),sample(actor[limb],6.8),'Listening freeze missing');
  assert(sample(video.horror.presence,6.4)[0]>.5 && sample(video.horror.presence,7.3)[0]===0);
  assert(sample(video.horror.spill,6.4)[0]<sample(video.horror.spill,5.5)[0]);
  assert(actorState(actor,6.4).face[1]<-5,'Window gaze missing');
} else {
  const originalHashes={'0':'3551a17b7080ff77e1a232eee2a740e1c18ca6f83c6cb74647e5521428f63e49',
    '1.8':'18ca67ea26dacbbc34617a5e335736d36a8bf77045876fe35be31d83f403f31c',
    '5.2':'a426b1716d618d29a182f4eaf064457ea26aa707bccf00e22a276fdc4c30d240',
    '9.9':'b3e5405e6a51aeff65b3d079e826df961021ca3e01bf71044cdbc807e3021eeb'};
  for(const t of [0,1.8,5.2,9.9]) {
    const s=actorState(actor,t), svg=renderToStaticMarkup(React.createElement('svg',null,
      React.createElement(ActorBody,{s,look:actor.look,t,skin:video.character_skin}),
      React.createElement(ActorHands,{s,look:actor.look,skin:video.character_skin})));
    assert.equal(crypto.createHash('sha256').update(svg).digest('hex'),originalHashes[t],'P3.1 v1 artwork changed');
  }
}
console.log(JSON.stringify({...baseline,cartoonArtworkFrames:300,cartoonFraming:'passed',
  contactFrames,maxPostContactDrift,posture:'recoil and lean',defaultSkin:'unchanged'}));
