import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {ActorBody, ActorHands, ActorSkin} from './Actor';
import {ActorMotion, Key, sample, stateAt} from './motion';

// Generic automatically planned story: many locations, actors and props over the
// same rig mechanics as the pilot. Everything story-specific is in the props data.
type Look = {shirt: string; skin: string; hair: string; hair_style?: string};
type Rect = {x: number; y: number; w: number; h: number; hinge?: string};
// Tracks are world coordinates; `scale` < 1 is the same rig drawn smaller about the ground
// line (children). `layer` 1 = inside a vehicle (between its interior and its body).
type VActor = {id: string; look: Look; scale?: number; root: Key[]; left_hand: Key[]; right_hand: Key[];
  left_foot: Key[]; right_foot: Key[]; facing_keys: Key[]; face: Key[]; opacity: Key[]; layer?: Key[]; posture?: Key[]};
type VItem = {id: string; kind: string; color: string | null; track: Key[]; visible: Key[]; held: Key[]; open: Key[]};
type VVehicle = {id: string; kind: string; color: string | null; track: Key[]; door?: Key[]};
type VInsert = {start: number; end: number; kind: string; color: string | null; text: string};
type VShot = {id: string; start_seconds: number; end_seconds: number; view: 'title' | 'world';
  location: string | null; camera: Key[]; light: Key[]; door: Key[]; weather: string | null;
  actors: VActor[]; items: VItem[]; vehicles: VVehicle[]; inserts?: VInsert[]};
type VLocation = {kind: string; svg: string; outdoor: boolean; door: Rect | null; window: Rect | null;
  atmosphere?: 'tense_apartment'};
export type StoryVideoProps = {duration_seconds: number; fps: number; title: string;
  character_skin?: ActorSkin; viewport?: {width: number; height: number};
  locations: Record<string, VLocation>; shots: VShot[];
  narration: {id: string; path: string; text: string; start_seconds: number; end_seconds: number}[];
  sfx: {id: string; path: string; start_seconds: number; duration_seconds: number; volume: number}[]};

const NO_PROP = {id: 'none', track: [[0, 0, 0, 0]], grip_seconds: null, release_seconds: null,
  handle_offset: [0, 0] as [number, number]};
const stepAt = (keys: Key[], t: number) => {
  let v = keys[0][1];
  for (const k of keys) if (k[0] <= t + 1e-9) v = k[1];
  return v;
};
const val = (keys: Key[], t: number) => sample(keys, t)[0];

const GROUND = 620;
export const actorState = (a: VActor, t: number) => {
  const facing = stepAt(a.facing_keys, t) < 0 ? -1 : 1;
  const s = a.scale ?? 1;
  // World -> rig space (inverse of the draw transform below); exact per frame.
  const body = (k: Key[]): Key[] => {
    const [x, y] = sample(k, t);
    return [[0, x / s, GROUND + (y - GROUND) / s]];
  };
  const actor = {...a, ...a.look, facing, root: body(a.root), left_hand: body(a.left_hand),
    right_hand: body(a.right_hand), left_foot: body(a.left_foot), right_foot: body(a.right_foot)};
  const m: ActorMotion = {actor, prop: NO_PROP, wash_window: null};
  return stateAt(m, t);
};
const scaleTransform = (s: number) => s === 1 ? undefined : `matrix(${s} 0 0 ${s} 0 ${GROUND * (1 - s)})`;

// Long hair sits behind the head (drawn first, inside the mirrored group).
const Hair: React.FC<{x: number; y: number; color: string}> = ({x, y, color}) => {
  const hx = x + 10, hy = y - 161;
  return <path d={`M ${hx - 30} ${hy - 30} Q ${hx - 52} ${hy + 30} ${hx - 34} ${hy + 72} L ${hx - 2} ${hy + 66}
    Q ${hx + 14} ${hy + 30} ${hx + 26} ${hy - 20} Z`} fill={color} stroke="#17242b" strokeWidth="2.5" />;
};

const Item: React.FC<{it: VItem; t: number; rain: boolean}> = ({it, t, rain}) => {
  const [x, y, rot] = sample(it.track, t);
  const held = stepAt(it.held, t) > 0;
  const open = val(it.open, t);
  const c = it.color;
  let body: React.ReactNode = null;
  switch (it.kind) {
    case 'umbrella': {
      const fill = c ?? '#3f6f8f';
      // Open: the shaft reaches above the holder's head (grip ~ shoulder height).
      const top = -168 * open, rim = -128 * open, w = 92 * open;
      body = open > 0.05 ? <g>
        <path d={`M 0 0 V ${top}`} strokeWidth="4" />
        <path d={`M ${-w} ${rim} Q 0 ${top - 62 * open} ${w} ${rim} Q ${w / 2} ${rim - 12} 0 ${rim - 4} Q ${-w / 2} ${rim - 12} ${-w} ${rim} Z`}
          fill={fill} />
        <path d="M 0 0 q -2 10 -10 10" fill="none" strokeWidth="4" />
      </g> : <g>
        <path d="M 0 0 V 118" strokeWidth="4" />
        <path d="M -9 22 Q 0 18 9 22 L 3 108 H -3 Z" fill={fill} />
        <path d="M 0 0 q 2 -10 -8 -10" fill="none" strokeWidth="4" />
      </g>;
      break;
    }
    case 'bag': body = <g><path d="M -14 8 Q 0 -10 14 8" fill="none" strokeWidth="4" />
      <rect x="-23" y="8" width="46" height="42" rx="6" fill={c ?? '#7a5a43'} /></g>; break;
    case 'phone': body = <rect x="-6" y="-10" width="12" height="20" rx="2" fill={c ?? '#2b2f33'} />; break;
    case 'letter': body = held ? <g><rect x="-13" y="-17" width="26" height="34" fill={c ?? '#eceae0'} />
      <path d="M -8 -9 h 16 M -8 -3 h 16 M -8 3 h 12" stroke="#7a8890" strokeWidth="1.5" /></g>
      : <path d="M -18 0 L -12 -6 H 18 L 12 0 Z" fill={c ?? '#eceae0'} />; break;
    case 'book': body = held ? <path d="M 0 -14 L -22 -18 V 14 L 0 18 L 22 14 V -18 Z" fill={c ?? '#eceae0'} />
      : <rect x="-18" y="-5" width="36" height="10" fill={c ?? '#5c5a7a'} />; break;
    case 'newspaper': body = held ? <g><path d="M 0 -18 L -30 -22 V 22 L 0 26 L 30 22 V -22 Z" fill={c ?? '#e4e0d2'} />
      <path d="M -24 -12 h 18 M -24 -4 h 18 M 6 -12 h 18 M 6 -4 h 18 M 6 4 h 14" stroke="#7a8890" strokeWidth="1.5" /></g>
      : <path d="M -22 0 L -16 -5 H 22 L 16 0 Z" fill={c ?? '#e4e0d2'} />; break;
    case 'cup': body = <g><path d="M 15 -10 C 34 -14 34 14 15 10" fill="none" strokeWidth="5" />
      <path d="M -15 -17 L 15 -17 L 12 15 Q 0 20 -12 15 Z" fill={c ?? '#f2efe5'} /></g>; break;
    case 'bread': body = <g><ellipse rx="24" ry="11" fill={c ?? '#c9965a'} />
      <path d="M -12 -5 l 6 7 M 0 -8 l 6 7 M 12 -5 l 4 6" stroke="#8a5e34" strokeWidth="2" /></g>; break;
    case 'coin': body = held ? <circle r="7" fill={c ?? '#d4b25a'} /> :
      <ellipse rx="8" ry="2.6" fill={c ?? '#d4b25a'} strokeWidth="1.5" />; break;
    case 'key': body = <g><circle cx="-5" r="5" fill="none" strokeWidth="3" stroke={c ?? '#c9b46a'} />
      <path d="M 0 0 h 12 v 4" fill="none" strokeWidth="3" stroke={c ?? '#c9b46a'} /></g>; break;
    case 'box': body = <rect x="-20" y="-17" width="40" height="34" fill={c ?? '#a28d68'} />; break;
    case 'bottle': body = <path d="M -4 -25 h 8 v 10 q 8 4 8 12 v 28 h -24 v -28 q 0 -8 8 -12 Z" fill={c ?? '#8fc3cf'} />; break;
    case 'tray': body = <g><rect x="-36" y="-2" width="72" height="6" fill={c ?? '#9aa8a6'} />
      {[-22, 0, 22].map(dx => <ellipse key={dx} cx={dx} cy="-8" rx="10" ry="6" fill="#c9965a" />)}</g>; break;
    case 'flower': body = <g><path d="M 0 0 V 30" stroke="#5f8a6a" strokeWidth="3" />
      {[[-8, -6], [8, -6], [0, -14]].map(([dx, dy], i) => <circle key={i} cx={dx} cy={dy} r="7" fill={c ?? '#d98ca0'} />)}</g>; break;
    default: body = <rect x="-12" y="-12" width="24" height="24" rx="4" fill={c ?? '#a6a28a'} />;
  }
  return <g transform={`translate(${x} ${y}) rotate(${rot})`} opacity={val(it.visible, t)}>
    {body}
    {rain && open > 0.5 ? <path d="M -88 -122 v 9 M 88 -122 v 9 M -40 -150 v 7 M 40 -150 v 7" stroke="#a8e3e5" strokeWidth="2"
      opacity={0.5 + 0.5 * Math.sin(t * 20)} /> : null}
  </g>;
};

// Vehicles stand on the near lane (ground y 600). Geometry must match VEHICLE in story_planner.py.
const BUS = {x0: -380, x1: 380, top: -382, bottom: -22, door: [-340, -270], doorTop: -370, doorBottom: -28};
const VehicleBack: React.FC<{v: VVehicle; t: number}> = ({v, t}) => {
  const x = sample(v.track, t)[0];
  if (v.kind !== 'bus') return null;
  return <g transform={`translate(${x} 600)`}>
    <rect x={BUS.x0 + 6} y={BUS.top + 6} width={BUS.x1 - BUS.x0 - 12} height={BUS.bottom - BUS.top - 6} fill="#26343c" />
    <rect x={BUS.x0 + 6} y={BUS.doorBottom - 6} width={BUS.x1 - BUS.x0 - 12} height="10" fill="#3b4a52" />
  </g>;
};
const VehicleFront: React.FC<{v: VVehicle; t: number}> = ({v, t}) => {
  const x = sample(v.track, t)[0];
  const door = v.door ? sample(v.door, t)[0] : 0;
  if (v.kind === 'car') {
    return <g transform={`translate(${x} 600)`} stroke="#17242b" strokeWidth="3">
      <path d="M -150 -14 V -54 L -100 -60 L -60 -100 H 60 L 100 -60 L 150 -54 V -14 Z" fill={v.color ?? '#8a4a40'} />
      <path d="M -52 -92 H 52 L 84 -62 H -84 Z" fill="#9fb4b8" />
      {[-90, 90].map(dx => <circle key={dx} cx={dx} cy="-14" r="20" fill="#22282c" />)}
    </g>;
  }
  // Side-view bus travelling right to left: front and door on the left. The body has a real
  // door opening (evenodd) and see-through windows so a passenger behind it stays visible.
  const [d0, d1] = BUS.door;
  const body = `M ${BUS.x0} ${BUS.top + 20} Q ${BUS.x0} ${BUS.top} ${BUS.x0 + 20} ${BUS.top} H ${BUS.x1 - 20}
    Q ${BUS.x1} ${BUS.top} ${BUS.x1} ${BUS.top + 20} V ${BUS.bottom} H ${BUS.x0} Z
    M ${d0} ${BUS.doorTop} V ${BUS.doorBottom} H ${d1} V ${BUS.doorTop} Z`;
  const windows = [-240, -130, -20, 90, 200];
  const leaf = (d1 - d0) / 2 * (1 - 0.85 * door);
  return <g transform={`translate(${x} 600)`} stroke="#17242b" strokeWidth="3">
    <path d={`${body} ${windows.map(w => `M ${w} -350 V -200 H ${w + 92} V -350 Z`).join(' ')}
      M ${BUS.x0 + 10} -350 V -230 H ${BUS.x0 + 44} V -350 Z`} fill={v.color ?? '#3f7fa3'} fillRule="evenodd" />
    {windows.map(w => <rect key={w} x={w} y="-350" width="92" height="150" fill="#a9c3cf" fillOpacity="0.42" />)}
    <rect x={BUS.x0 + 10} y="-350" width="34" height="120" fill="#a9c3cf" fillOpacity="0.42" />
    <rect x={BUS.x0} y="-110" width={BUS.x1 - BUS.x0} height="14" fill="#e8dcae" stroke="none" />
    {/* Two folding door leaves close toward the middle of the opening. */}
    <rect x={d0} y={BUS.doorTop} width={leaf} height={BUS.doorBottom - BUS.doorTop} fill="#2f4752" fillOpacity="0.9" />
    <rect x={d1 - leaf} y={BUS.doorTop} width={leaf} height={BUS.doorBottom - BUS.doorTop} fill="#2f4752" fillOpacity="0.9" />
    <rect x={d0 - 6} y="-8" width={d1 - d0 + 12} height="8" fill="#8d9592" />
    {[-250, 250].map(dx => <g key={dx}><circle cx={dx} cy="-20" r="34" fill="#22282c" /><circle cx={dx} cy="-20" r="13" fill="#8d9592" /></g>)}
  </g>;
};

export const doorHandle = (d: Rect, open: number): [number, number] => {
  const w = d.w * (1 - 0.82 * open), x = d.hinge === 'left' ? d.x : d.x + d.w - w;
  return [d.hinge === 'left' ? x + w - 16 : x + 16, d.y + 120];
};
const Door: React.FC<{d: Rect; open: number; detailed?: boolean}> = ({d, open, detailed}) => {
  const w = d.w * (1 - 0.82 * open);
  const x = d.hinge === 'left' ? d.x : d.x + d.w - w;
  const [hx, hy] = doorHandle(d, open);
  return <g stroke="#1d303b" strokeWidth="3">
    <rect x={x} y={d.y} width={w} height={d.h} fill={detailed ? '#263237' : open > 0.02 ? '#3e4f58' : '#4c5d64'} />
    {detailed ? <g opacity="0.8">
      <path d={`M ${x+8} ${d.y+8} h ${w-16} v ${d.h-18} h ${16-w} Z`} stroke="#5a625a" strokeWidth="1" fill="none" />
      <rect x={x+24} y={d.y+18} width={Math.max(1,w-34)} height="82" rx="2" fill="#1c292e" strokeWidth="1" />
      <rect x={x+24} y={d.y+150} width={Math.max(1,w-34)} height="145" rx="2" fill="#202b2e" strokeWidth="1" />
      <path d={`M ${x+6} ${d.y+d.h-1} h ${w-12}`} stroke="#ca9952" strokeWidth="2" />
      <ellipse cx={hx} cy={hy} rx="8" ry="12" fill="#162026" stroke="#766d55" strokeWidth="1" />
    </g> : null}
    {open < 0.5 ? <circle data-door-handle="true" cx={hx} cy={hy} r="5" fill="#c9cfc6" /> : null}
  </g>;
};

const RainStreaks: React.FC<{t: number; x0: number; y0: number; w: number; h: number; n: number; seed: number}> =
  ({t, x0, y0, w, h, n, seed}) => <g stroke="#b8d6dc" strokeWidth="2" opacity="0.55">
    {Array.from({length: n}, (_, i) => {
      const px = (i * 97.13 + seed * 31) % w, speed = 900 + (i * 53) % 300;
      const py = ((i * 61.7 + t * speed) % (h + 40)) - 20;
      return <path key={i} d={`M ${x0 + px} ${y0 + py} l -4 16`} />;
    })}
  </g>;

// Full-frame close-up of a written item showing the words the story gives for it.
const Insert: React.FC<{ins: VInsert; t: number}> = ({ins, t}) => {
  const {width, height} = useVideoConfig();
  const portrait = height > width;
  const a = Math.min(1, (t - ins.start) / 0.35, (ins.end - t) / 0.25);
  if (a <= 0) return null;
  const paper = ins.color ?? '#efe9d8';
  return <AbsoluteFill style={{opacity: a, background: 'linear-gradient(#6f5a48, #4d3d31)'}}>
    <div style={{position: 'absolute', left: portrait ? 40 : 300, top: portrait ? height * 0.2 : 120,
      width: portrait ? width - 80 : 680, height: portrait ? height * 0.5 : 420, background: paper,
      transform: `rotate(-2.5deg) scale(${1 + 0.03 * Math.min(1, (t - ins.start) / 3)})`,
      boxShadow: '0 18px 40px rgba(0,0,0,.45)', borderRadius: 4,
      backgroundImage: 'repeating-linear-gradient(transparent 0 58px, rgba(90,110,130,.25) 58px 60px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60, boxSizing: 'border-box'}}>
      <div style={{fontFamily: '"Bradley Hand", "Chalkboard SE", "Snell Roundhand", cursive', fontSize: 50,
        color: '#2a3550', lineHeight: 1.35, textAlign: 'center'}}>{ins.text}</div>
    </div>
  </AbsoluteFill>;
};

type Drawn = {a: VActor; s: ReturnType<typeof actorState>; o: number; inside: boolean; y: number};
const People: React.FC<{states: Drawn[]; items: VItem[]; t: number; rain: boolean; skin?: ActorSkin}> = ({states, items, t, rain, skin}) => <>
  {states.map(({a, s, o}) => {
    const mirror = s.facing < 0 ? `matrix(-1 0 0 1 ${2 * s.root[0]} 0)` : undefined;
    return o > 0.001 ? <g key={a.id} opacity={o} transform={scaleTransform(a.scale ?? 1)}><g transform={mirror}>
      {skin !== 'stickman_horror' && a.look.hair_style === 'long' ? <Hair x={s.root[0]} y={s.root[1]} color={a.look.hair} /> : null}
      <ActorBody s={s} look={a.look} t={t + a.id.length * 0.7} skin={skin} />
    </g></g> : null;
  })}
  {items.map(it => <Item key={it.id} it={it} t={t} rain={rain} />)}
  {states.map(({a, s, o}) => o > 0.001 ? <g key={a.id} opacity={o} transform={scaleTransform(a.scale ?? 1)}>
    <g transform={s.facing < 0 ? `matrix(-1 0 0 1 ${2 * s.root[0]} 0)` : undefined}>
      <ActorHands s={s} look={a.look} skin={skin} /></g></g> : null)}
</>;

const World: React.FC<{shot: VShot; loc: VLocation; t: number; skin?: ActorSkin}> = ({shot, loc, t, skin}) => {
  const dark = sample(shot.light, t)[0];
  const rain = shot.weather === 'rain';
  const win = loc.window;
  // Depth order: whoever stands further back (planted foot higher on screen) is drawn first.
  const foot = (a: VActor) => Math.max(sample(a.left_foot, t)[1], sample(a.right_foot, t)[1]);
  const states = shot.actors.map(a => ({a, s: actorState(a, t), o: val(a.opacity, t),
    inside: a.layer ? stepAt(a.layer, t) > 0 : false, y: foot(a)}))
    .sort((p, q) => p.y - q.y);
  return <>
    <div style={{position: 'absolute', inset: 0}} dangerouslySetInnerHTML={{__html: loc.svg}} />
    <svg width="1280" height="720" viewBox="0 0 1280 720" style={{position: 'absolute', inset: 0}}>
      {win ? <g>
        <rect x={win.x} y={win.y} width={win.w} height={win.h}
          fill={dark > 0.15 ? '#1c304a' : rain ? '#8a9ba6' : '#a9c3cf'} />
        {rain ? <RainStreaks t={t} x0={win.x} y0={win.y} w={win.w} h={win.h} n={Math.round(win.w / 9)} seed={3} /> : null}
        <path d={`M ${win.x + win.w / 2} ${win.y} V ${win.y + win.h} M ${win.x} ${win.y + win.h / 2} H ${win.x + win.w}`}
          stroke="#4e696d" strokeWidth="7" />
      </g> : null}
      {loc.door ? <Door d={loc.door} open={val(shot.door, t)} detailed={loc.atmosphere === 'tense_apartment'} /> : null}
      {shot.vehicles.map(v => <VehicleBack key={v.id} v={v} t={t} />)}
      <g stroke="#17242b" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round">
        <People states={states.filter(x => x.inside)} items={[]} t={t} rain={false} skin={skin} />
      </g>
      {loc.atmosphere === 'tense_apartment' ? <g pointerEvents="none">
        <defs><radialGradient id="apartment-vignette"><stop offset="0.32" stopColor="#03090e" stopOpacity="0" />
          <stop offset="1" stopColor="#03070b" stopOpacity="0.78" /></radialGradient></defs>
        <rect width="1280" height="720" fill="url(#apartment-vignette)" stroke="none" />
      </g> : null}
      {shot.vehicles.map(v => <VehicleFront key={v.id} v={v} t={t} />)}
      <g stroke="#17242b" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round">
        {/* Items resting on furniture are behind people; held items go between body and hands. */}
        {shot.items.filter(it => stepAt(it.held, t) <= 0).map(it => <Item key={it.id} it={it} t={t} rain={false} />)}
        <People states={states.filter(x => !x.inside)} items={shot.items.filter(it => stepAt(it.held, t) > 0)}
          t={t} rain={rain && loc.outdoor} skin={skin} />
      </g>
    </svg>
  </>;
};

export const StoryVideo: React.FC<StoryVideoProps> = (p) => {
  const frame = useCurrentFrame(), {fps, width, height} = useVideoConfig(), t = frame / fps;
  const worldScale = height / 720;
  const shot = p.shots.find(s => t < s.end_seconds) ?? p.shots[p.shots.length - 1];
  const local = Math.min(t, shot.end_seconds) - shot.start_seconds;
  const [cx, cy, zoom] = sample(shot.camera, local);
  const [dark, fade] = sample(shot.light, local);
  const loc = shot.location ? p.locations[shot.location] : null;
  const caption = p.narration.find(n => t >= n.start_seconds && t < n.end_seconds);
  const rainOut = shot.weather === 'rain' && loc?.outdoor;
  return <AbsoluteFill style={{background: '#0b141a', overflow: 'hidden'}}>
    {shot.view === 'title' || !loc ? <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
      <div style={{fontFamily: 'Georgia, serif', fontSize: 68, color: '#f1ead8', letterSpacing: 1}}>{p.title}</div>
    </AbsoluteFill> : <div style={{position: 'absolute', left: 0, top: 0, width: 1280, height: 720, transformOrigin: '0 0',
      transform: `translate(${width / 2}px, ${height / 2}px) scale(${zoom * worldScale}) translate(${-cx}px, ${-cy}px)`}}>
      <World shot={shot} loc={loc} t={local} skin={p.character_skin} />
    </div>}
    {rainOut ? <svg width={width} height={height} style={{position: 'absolute', inset: 0}}>
      <RainStreaks t={local} x0={0} y0={0} w={width} h={height} n={150} seed={7} /></svg> : null}
    {(shot.inserts ?? []).filter(i => local >= i.start && local < i.end).map((i, k) =>
      <Insert key={k} ins={i} t={local} />)}
    {dark > 0 ? <div style={{position: 'absolute', inset: 0, background: '#050c16', opacity: dark}} /> : null}
    {fade > 0 ? <div style={{position: 'absolute', inset: 0, background: '#000', opacity: fade}} /> : null}
    {caption ? <div style={{position: 'absolute', bottom: height > width ? 64 : 24,
      left: height > width ? 40 : 90, right: height > width ? 40 : 90, textAlign: 'center',
      fontFamily: 'Arial, sans-serif', fontSize: 29, fontWeight: 500, color: '#f8f6ed', lineHeight: 1.5}}>
      <span style={{background: 'rgba(9,16,22,.88)', padding: '6px 18px', borderRadius: 5,
        boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone'}}>{caption.text}</span>
    </div> : null}
    {p.narration.map((n, i) => <Sequence key={`n${i}`} from={Math.round(n.start_seconds * fps)}
      durationInFrames={Math.ceil((n.end_seconds - n.start_seconds) * fps)} layout="none">
      <Audio src={staticFile(n.path)} />
    </Sequence>)}
    {p.sfx.map((x, i) => <Sequence key={`s${i}`} from={Math.round(x.start_seconds * fps)}
      durationInFrames={Math.max(1, Math.ceil(x.duration_seconds * fps))} layout="none">
      <Audio src={staticFile(x.path)} volume={x.volume} />
    </Sequence>)}
  </AbsoluteFill>;
};
