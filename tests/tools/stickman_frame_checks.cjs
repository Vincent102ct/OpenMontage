// Execute the actual TypeScript evaluator and SVG skin; no duplicate animator.
const fs = require('fs'), path = require('path'), Module = require('module');
const assert = require('assert'), crypto = require('crypto');
const nm = path.resolve('remotion-composer/node_modules');
const ts = require(path.join(nm, 'typescript'));
for (const ext of ['.ts', '.tsx']) Module._extensions[ext] = (m, f) => {
  m.paths.push(nm);
  m._compile(ts.transpileModule(fs.readFileSync(f, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true,
  }}).outputText, f);
};
const React = require(path.join(nm, 'react'));
const {renderToStaticMarkup} = require(path.join(nm, 'react-dom/server'));
const {actorState} = require(path.resolve('tools/character/remotion/StoryVideo.tsx'));
const {ActorBody, ActorHands} = require(path.resolve('tools/character/remotion/Actor.tsx'));
const {stateAt, sample, toWorld} = require(path.resolve('tools/character/remotion/motion.ts'));
const video = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const shot = video.shots[0], actor = shot.actors[0];
const cropDoor = process.argv.includes('--allow-door-crop');
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
let previous, maxDelta = 0, planted = 0, airborne = 0;
for (let frame = 0; frame < 300; frame++) {
  const t = frame / 30, s = actorState(actor, t);
  for (const [a,b,length] of [[s.shoulder,s.le,65],[s.le,s.left,68],[s.shoulder,s.re,65],
    [s.re,s.right,68],[s.hip,s.lk,57],[s.lk,s.lf,58],[s.hip,s.rk,57],[s.rk,s.rf,58]]) {
    assert(Math.abs(dist(a,b)-length) < .001, `Broken bone at ${frame}`);
  }
  assert(Math.max(s.lf[1],s.rf[1]) >= 619.99, `Both feet float at ${frame}`);
  assert(Math.min(s.lf[1],s.rf[1]) <= 620.001 && Math.max(s.lf[1],s.rf[1]) <= 620.001);
  if (t > 4 && t < 8.4 && Math.min(s.lf[1],s.rf[1]) < 615) airborne++;
  if (previous) {
    for (const key of ['root','left','right','lf','rf']) {
      const delta = dist(previous[key],s[key]); maxDelta = Math.max(maxDelta,delta);
      assert(delta < 15, `${key} teleported at ${frame}`);
    }
    if (t > 4 && t < 8.4 && (dist(previous.lf,s.lf) < .001 || dist(previous.rf,s.rf) < .001)) planted++;
  }
  const [cx,cy,z] = sample(shot.camera,t), scale = 1280/720*z;
  // Full head/body, both hands/feet and fixed door remain inside the vertical safe area.
  for (const p of [[s.root[0]-35,s.root[1]-201],[s.root[0]+58,s.root[1]-110],
                    s.left,s.right,s.lf,s.rf,...(cropDoor ? [] : [[555,292],[665,625]])]) {
    const x = 360+(p[0]-cx)*scale, y = 640+(p[1]-cy)*scale;
    assert(x > 16 && x < 704 && y > 40 && y < 1240, `Unsafe framing at ${frame}`);
  }
  previous = s;
}
assert(planted > 110 && airborne > 20, 'Walk lacks planted holds or leg lift');
assert(actorState(actor,1.8).face[5] < -8 && actorState(actor,3.2).face[5] > 4, 'Head turn missing');
assert.deepStrictEqual(actorState(actor,5),actorState(actor,5));
const mirrored = {...actor, facing_keys: [[0,-1]]};
for (const t of [0,1.8,5,8.4,9.9]) {
  const s = actorState(mirrored,t);
  assert(dist(toWorld(s,s.right),sample(actor.right_hand,t)) < .001, 'Mirrored wrist detached');
}
const legacy = JSON.parse(fs.readFileSync('examples/story-to-action/pilot.motion.json'));
const hashes = {'0':'f934981eb0a84bbfb6f7bd1de88939db258d88a7a1bc1625208ff56010ab3b96',
  '4':'df8a39b5e0784b66d62fa3c103179c09456859fd8d8699ac8d14aabddda0ee5b',
  '9':'772721ac21b5aec74232a453d8656395f1f382df6c6697b5647840334bd27e12'};
const markup = (s,look,t,skin) => renderToStaticMarkup(React.createElement('svg',null,
  React.createElement(ActorBody,{s,look,t,skin}),React.createElement(ActorHands,{s,look,skin})));
for (const t of [0,4,9]) {
  const s = stateAt(legacy,t), svg = markup(s,legacy.actor,t);
  assert.equal(crypto.createHash('sha256').update(svg).digest('hex'),hashes[t], 'Legacy cartoon changed');
  assert.equal(markup(s,legacy.actor,t,'cartoon'),svg);
  const stick = markup(s,legacy.actor,t,'stickman_horror');
  assert(stick.includes('data-skin="stickman_horror"') && stick !== svg);
  assert(!stick.includes(legacy.actor.shirt), 'Filled shirt leaked into stickman');
}
console.log(JSON.stringify({frames:300, planted, airborne, maxJointDelta:maxDelta,
  framing:'passed', mirroredHands:'passed', legacyCartoonHashes:'3/3 unchanged'}));
