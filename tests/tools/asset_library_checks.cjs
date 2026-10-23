// P3.2A: exercise the actual TS rig, cast artwork and location overlay at every output frame.
// Usage: node tests/tools/asset_library_checks.cjs story_video.json [other_story_video.json]
const fs = require('fs'), path = require('path'), Module = require('module');
const assert = require('node:assert/strict'), crypto = require('node:crypto');
const nm = path.resolve('remotion-composer/node_modules');
const ts = require(path.join(nm, 'typescript'));
for (const ext of ['.ts', '.tsx']) Module._extensions[ext] = (m, f) => {
  m.paths.push(nm);
  m._compile(ts.transpileModule(fs.readFileSync(f, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true}}).outputText, f);
};
const React = require(path.join(nm, 'react'));
const {renderToStaticMarkup} = require(path.join(nm, 'react-dom/server'));
const {actorState, doorHandle} = require(path.resolve('tools/character/remotion/StoryVideo.tsx'));
const {ActorBody, ActorHands} = require(path.resolve('tools/character/remotion/Actor.tsx'));
const {HorrorOverlay, horrorLevels} = require(path.resolve('tools/character/remotion/CinematicHorror.tsx'));
const {sample} = require(path.resolve('tools/character/remotion/motion.ts'));
const sha = s => crypto.createHash('sha256').update(s).digest('hex');
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const identityOf = svg => {
  const i = svg.indexOf('<g data-part="identity">');
  assert(i >= 0, 'identity group missing');
  return svg.slice(i, svg.indexOf('<g data-part="expression">', i));
};

function check(file) {
  const video = JSON.parse(fs.readFileSync(file, 'utf8'));
  const {width: vw, height: vh} = video.viewport ?? {width: 1280, height: 720};
  const [mx, my] = vh > vw ? [16, 40] : [24, 18];
  assert.equal(video.character_skin, 'cartoon_horror');
  const out = {file: path.basename(path.dirname(file)), viewport: [vw, vh], frames: 0, identity: {}, appearance: {}, planted: 0,
    maxPlantedFootDrift: 0,
    lifted: 0, maxJointDelta: 0, contacts: [], shots: [], overlay: []};
  let previous = null;
  for (const shot of video.shots) {
    const loc = video.locations[shot.location], g = loc.cinematic;
    assert(g, `${shot.id}: library locations carry cinematic geometry`);
    const frames = Math.round((shot.end_seconds - shot.start_seconds) * video.fps);
    for (let f = 0; f < frames; f++) {
      const local = f / video.fps, t = shot.start_seconds + local;
      const [cx, cy, z] = sample(shot.camera, local), scale = vh / 720 * z;
      for (const actor of shot.actors) {
        const s = actorState(actor, local), d = actor.look.design, hs = d.build.head;
        // Fixed bone lengths from the shared IK.
        for (const [a, b, len] of [[s.shoulder, s.le, 65], [s.le, s.left, 68], [s.shoulder, s.re, 65], [s.re, s.right, 68],
          [s.hip, s.lk, 57], [s.lk, s.lf, 58], [s.hip, s.rk, 57], [s.rk, s.rf, 58]])
          assert(Math.abs(dist(a, b) - len) < 1e-6, `${shot.id}: bone length changed at ${t}`);
        for (const foot of [s.lf, s.rf]) assert(foot[1] <= 620 + 1e-6 && foot[1] >= 606, `${shot.id}: foot leaves floor band`);
        if (s.lf[1] === 620 && s.rf[1] === 620) out.planted++; else out.lifted++;
        // Whole drawn figure (hair, coat hem, shoes, hands) inside the safe area of this viewport.
        const pts = [[s.head[0] - 50 * hs, s.head[1] - 58 * hs], [s.head[0] + 45 * hs, s.head[1] + 84 * hs],
          [s.hip[0] - d.build.hip - 4, s.hip[1] + 12], [s.hip[0] + d.build.hip + 4, s.hip[1] + 12],
          [Math.min(s.lk[0], s.rk[0]) - 18, (s.lk[1] + s.rk[1]) / 2 + 22], [Math.max(s.lk[0], s.rk[0]) + 20, (s.lk[1] + s.rk[1]) / 2 + 22],
          [s.le[0] - d.build.sleeve, s.le[1]], [s.re[0] + d.build.sleeve, s.re[1]],
          [s.lf[0] - 14, s.lf[1] + 9], [s.rf[0] + 27, s.rf[1] + 9], [s.left[0] - 15, s.left[1] - 15], [s.right[0] + 15, s.right[1] + 15]];
        for (const p of pts) {
          const x = vw / 2 + (p[0] - cx) * scale, y = vh / 2 + (p[1] - cy) * scale;
          assert(x > mx && x < vw - mx && y > my && y < vh - my, `${shot.id}: figure clipped at ${t.toFixed(3)} (${x.toFixed(0)},${y.toFixed(0)})`);
        }
        if (previous) for (const k of ['root', 'left', 'right', 'lf', 'rf'])
          if (previous.shot === shot.id) out.maxJointDelta = Math.max(out.maxJointDelta, dist(previous.s[k], s[k]));
        if (previous?.shot === shot.id) for (const k of ['lf', 'rf'])
          if (Math.abs(previous.s[k][1] - 620) < 1e-6 && Math.abs(s[k][1] - 620) < 1e-6)
            out.maxPlantedFootDrift = Math.max(out.maxPlantedFootDrift, Math.abs(previous.s[k][0] - s[k][0]));
        previous = {shot: shot.id, s};
        const svg = renderToStaticMarkup(React.createElement('svg', null,
          React.createElement(ActorBody, {s, look: actor.look, t, skin: video.character_skin}),
          React.createElement(ActorHands, {s, look: actor.look, skin: video.character_skin})));
        assert(svg.includes(`data-character="${d.id}"`) && !/NaN|Infinity/.test(svg), `${shot.id}: bad cast SVG`);
        const id = sha(identityOf(svg));
        out.identity[d.id] = out.identity[d.id] ?? id;
        assert.equal(out.identity[d.id], id, `${d.id} identity drawing changed at ${t}`);
        const appearance = sha(JSON.stringify(actor.look));
        out.appearance[d.id] = out.appearance[d.id] ?? appearance;
        assert.equal(out.appearance[d.id], appearance, `${d.id} body/costume/appearance changed between shots`);
        assert.deepEqual(actorState(actor, local), actorState(actor, local), 'Seek is not deterministic');
      }
      // Overlay: renders from geometry only, no NaN, lamps/presence follow their tracks.
      const v = horrorLevels(video.horror, t);
      const overlay = renderToStaticMarkup(React.createElement('svg', null, React.createElement(HorrorOverlay, {g, v, t})));
      assert(!/NaN|Infinity/.test(overlay), 'Overlay produced NaN');
      assert.equal((overlay.match(/data-lamp=/g) ?? []).length, g.lamps.length);
      if (g.presence) assert(overlay.includes(`data-presence="${v.presence.toFixed(4)}"`));
      else assert(!overlay.includes('data-silhouette='), 'Unexpected supernatural silhouette');
      out.frames++;
    }
    // Final beat: the reaching hand holds the door's real (StoryVideo) handle with planted feet.
    const actor = shot.actors[0], handle = doorHandle(loc.door, 0);
    const anchor = loc.anchors.doors.find(d => d.interactive).handle;
    assert(dist(handle, anchor) < 1e-9, 'Environment door anchor differs from the rendered handle');
    let held = 0, drift = 0;
    for (let f = 0; f < frames; f++) {
      const local = f / video.fps, s = actorState(actor, local);
      const e = dist(s.right, handle);
      if (e < 1e-6) {
        held++; drift = Math.max(drift, e);
        const screen = vw / 2 + (handle[0] - sample(shot.camera, local)[0]) * vh / 720 * sample(shot.camera, local)[2];
        assert(screen > mx && screen < vw - mx, 'Door contact out of frame');
      }
    }
    out.contacts.push({shot: shot.id, heldFrames: held, maxDrift: drift});
    out.shots.push({id: shot.id, character: actor.look.design.id, revision: actor.look.design.revision,
      environment: loc.asset.environment, preset: g.preset});
  }
  assert(out.maxJointDelta < 25, `Teleport: ${out.maxJointDelta.toFixed(2)} world units in one frame`);
  assert(out.maxPlantedFootDrift < .05, `Planted foot slides ${out.maxPlantedFootDrift.toFixed(3)} world units`);
  // Geometry is derived from this environment's anchors, not the P3.1 test room.
  const loc = video.locations[video.shots[0].location], g = loc.cinematic, feat = loc.anchors;
  for (const seam of g.seams) assert(feat.doors.some(d => Math.abs(d.seam[2] - seam.y) < 1e-9 && d.seam[0] === seam.x0));
  for (const lamp of g.lamps) assert(feat.lamps.some(l => l.x === lamp.x && l.y === lamp.y), 'Lamp glow off its fixture');
  if (g.preset === 'cold_moonlight') {
    const w = feat.windows[0].rect, [a, b] = g.beams[0].points;
    assert(a[0] === w.x && b[0] === w.x + w.w && a[1] >= w.y && b[1] >= w.y, 'Moonlight beam not at the window');
  }
  if (g.presence) {
    const clip = g.presence.clip.flat(), xs = clip.map(q => q[0]), ys = clip.map(q => q[1]);
    assert(g.presence.x > Math.min(...xs) && g.presence.x < Math.max(...xs), 'Presence outside its opening');
    const bottom = g.presence.y + 62 * g.presence.scale;
    assert(bottom <= Math.max(...ys) + 1e-6, 'Presence extends below its opening');
    out.overlay.push({presence: g.presence.silhouette, clipBox: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]});
  }
  out.overlay.push({preset: g.preset, beams: g.beams.length, pools: g.pools.length, lamps: g.lamps.length, seams: g.seams.length});
  return out;
}

const results = process.argv.slice(2).map(check);
const appearances = {};
for (const r of results) for (const [id, hash] of Object.entries(r.appearance)) {
  assert(!appearances[id] || appearances[id] === hash, `${id} changed appearance across stories/environments`);
  appearances[id] = hash;
}
if (results.length === 2) {
  const [a, b] = results.map(r => Object.entries(r.identity));
  assert(a.length === 1 && b.length === 1 && a[0][0] !== b[0][0] && a[0][1] !== b[0][1], 'Stories must cast different identities');
}
console.log(JSON.stringify(results));
