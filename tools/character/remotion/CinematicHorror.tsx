import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {StoryVideo, StoryVideoProps} from './StoryVideo';
import {Key, sample} from './motion';

type Pt = [number, number];
type Driver = 'constant' | 'spill' | 'flicker';
// P3.2A location-aware geometry, resolved from the asset library's environment anchors.
export type HorrorGeometry = {version: 1; preset: string; revision: number;
  negative_fill: {color: string; opacity: number};
  pools: {cx: number; cy: number; rx: number; ry: number; driver: Driver; strength: number}[];
  beams: {points: Pt[]; color: string; opacity: number; driver: Driver}[];
  lamps: {id: string; x: number; y: number; r: number; color: string; driver: Driver}[];
  seams: {x0: number; x1: number; y: number; color: string; driver: Driver}[];
  haze?: {cx: number; cy: number; rx: number; ry: number; color: string; opacity: number};
  presence?: {silhouette: string; revision: number; path: string; color: string; x: number; y: number;
    scale: number; clip: Pt[][]; backdrop?: {color: string; opacity: number}}};
export type CinematicHorrorProps = StoryVideoProps & {
  // Optional seekable environmental tracks; absent for every existing package.
  horror?: {presence: Key[]; spill: Key[]; flicker?: Key[]};
  locations: Record<string, {cinematic?: HorrorGeometry}>;
  visual_state?: {schema_version:'1.0'; review:unknown; shots:Record<string, ShotLampState>};
};
type ShotLampState = {lamps?:Record<string,Key[]>; bindings?:Record<string,{beam:number;pool:number}>};
export type HorrorLevels = {presence: number; dx: number; spill: number; flicker: number};

const poly = (points: Pt[]) => `M ${points.map(q => q.join(' ')).join(' L ')} Z`;
const level = (d: Driver, v: HorrorLevels) => d === 'spill' ? v.spill : d === 'flicker' ? v.flicker : 1;

// Pure, seekable overlay in world coordinates; every shape comes from the location geometry.
export const HorrorOverlay: React.FC<{g: HorrorGeometry; v: HorrorLevels; t: number; lampState?:ShotLampState; localTime?:number}>
  = ({g, v, t, lampState, localTime=0}) => {
  const pr = g.presence;
  // Opt-in reviewed per-fixture state. Frozen geometry and legacy drivers stay unchanged.
  const owner = (kind:'beam'|'pool', index:number) => Object.keys(lampState?.bindings ?? {})
    .find(id => lampState!.bindings![id][kind] === index);
  const emission = (id:string|undefined, driver:Driver) => id && lampState?.lamps?.[id]
    ? sample(lampState.lamps[id],localTime)[0] : level(driver,v);
  return <g data-preset={g.preset}>
    <defs>
      <radialGradient id="hz-pool"><stop stopColor="black" /><stop offset=".45" stopColor="#3a3a3a" /><stop offset=".8" stopColor="#a8a8a8" /><stop offset="1" stopColor="white" /></radialGradient>
      {/* Blurred pools: a hard gradient edge reads as a rounded dark column (a false figure). */}
      <filter id="hz-soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="38" /></filter>
      <mask id="hz-negative-fill"><rect width="1280" height="720" fill="white" />
        <g filter="url(#hz-soft)">{g.pools.map((q, i) => <ellipse key={i} cx={q.cx} cy={q.cy} rx={q.rx} ry={q.ry}
          data-lamp-pool={owner('pool',i)} fill="url(#hz-pool)" opacity={q.strength * emission(owner('pool',i),q.driver)} />)}</g></mask>
      {g.beams.map((b, i) => {
        const [a0, a1, b1, b0] = b.points;
        return <linearGradient key={i} id={`hz-beam-${i}`} gradientUnits="userSpaceOnUse"
          x1={(a0[0] + a1[0]) / 2} y1={(a0[1] + a1[1]) / 2} x2={(b0[0] + b1[0]) / 2} y2={(b0[1] + b1[1]) / 2}>
          <stop stopColor={b.color} stopOpacity={b.opacity} /><stop offset="1" stopColor={b.color} stopOpacity="0" /></linearGradient>;
      })}
      {g.lamps.map((l, i) => <radialGradient key={i} id={`hz-lamp-${i}`}><stop stopColor={l.color} stopOpacity=".55" />
        <stop offset="1" stopColor={l.color} stopOpacity="0" /></radialGradient>)}
      {pr ? <clipPath id="hz-presence-clip"><path d={pr.clip.map(poly).join(' ')} /></clipPath> : null}
    </defs>
    {pr ? <g clipPath="url(#hz-presence-clip)" data-presence={v.presence.toFixed(4)} data-silhouette={pr.silhouette}>
      {pr.backdrop ? <path d={pr.clip.map(poly).join(' ')} fill={pr.backdrop.color} opacity={pr.backdrop.opacity} /> : null}
      <path d={pr.path} fill={pr.color} opacity={v.presence}
        transform={`translate(${pr.x + v.dx} ${pr.y}) scale(${pr.scale})`} />
    </g> : null}
    <rect width="1280" height="720" fill={g.negative_fill.color} opacity={g.negative_fill.opacity} mask="url(#hz-negative-fill)" />
    {g.beams.map((b, i) => <path key={i} d={poly(b.points)} fill={`url(#hz-beam-${i})`} opacity={emission(owner('beam',i),b.driver)} data-beam={i} data-lamp-beam={owner('beam',i)} />)}
    {g.lamps.map((l, i) => <g key={i} data-lamp={l.id} opacity={emission(l.id,l.driver)}>
      <circle cx={l.x} cy={l.y} r={l.r} fill={`url(#hz-lamp-${i})`} />
      <ellipse cx={l.x} cy={l.y} rx="9" ry="4" fill="#efe2b4" opacity=".85" /></g>)}
    {g.seams.map((s, i) => <g key={i} opacity={level(s.driver, v)}>
      <path d={`M ${s.x0} ${s.y} H ${s.x1}`} stroke={s.color} strokeWidth="2" opacity=".65" />
      <path d={`M ${(s.x0 + s.x1) / 2 - 8} ${s.y + 1} l -40 45 h 70 l -13 -45 Z`} fill={s.color} opacity=".035" /></g>)}
    {g.haze ? <ellipse cx={g.haze.cx + Math.sin(t * .28) * 11} cy={g.haze.cy} rx={g.haze.rx} ry={g.haze.ry}
      fill={g.haze.color} opacity={g.haze.opacity} /> : null}
  </g>;
};

export const horrorLevels = (h: NonNullable<CinematicHorrorProps['horror']>, t: number): HorrorLevels => {
  const [presence, dx] = sample(h.presence, t);
  return {presence, dx: dx ?? 0, spill: sample(h.spill, t)[0], flicker: h.flicker ? sample(h.flicker, t)[0] : 1};
};

// Add light and depth over the existing world without changing its actor/motion layers.
export const DirectedStoryVideo: React.FC<CinematicHorrorProps> = p => {
  const frame=useCurrentFrame(), {fps,width,height}=useVideoConfig(), t=frame/fps;
  const shot=p.shots.find(s=>t<s.end_seconds) ?? p.shots[p.shots.length-1];
  const loc=shot?.location ? p.locations[shot.location] : null;
  if(!p.horror || !loc || p.character_skin!=='cartoon_horror') return <StoryVideo {...p} />;
  const local=Math.min(t,shot.end_seconds)-shot.start_seconds;
  const [cx,cy,z]=sample(shot.camera,local), scale=z*height/720;
  const geometry=loc.cinematic;
  if(geometry) return <><StoryVideo {...p} />
    <AbsoluteFill style={{pointerEvents:'none',overflow:'hidden'}}>
      <svg width="1280" height="720" viewBox="0 0 1280 720" data-treatment="cinematic-horror"
        style={{position:'absolute',transformOrigin:'0 0',
          transform:`translate(${width/2}px, ${height/2}px) scale(${scale}) translate(${-cx}px, ${-cy}px)`}}>
        <HorrorOverlay g={geometry} v={horrorLevels(p.horror,t)} t={t} localTime={local} lampState={p.visual_state?.shots[shot.id]} />
      </svg>
    </AbsoluteFill>
  </>;
  // Legacy P3.1 v2 overlay: packages without location geometry keep their exact drawing.
  const [presence,dx]=sample(p.horror.presence,t), [spill]=sample(p.horror.spill,t);
  const win=loc.window, door=loc.door;
  return <><StoryVideo {...p} />
    <AbsoluteFill style={{pointerEvents:'none',overflow:'hidden'}}>
      <svg width="1280" height="720" viewBox="0 0 1280 720" data-treatment="cinematic-horror"
        style={{position:'absolute',transformOrigin:'0 0',
          transform:`translate(${width/2}px, ${height/2}px) scale(${scale}) translate(${-cx}px, ${-cy}px)`}}>
        <defs>
          <radialGradient id="horror-light-pool"><stop stopColor="black" />
            <stop offset=".48" stopColor="#292929"/><stop offset="1" stopColor="white"/></radialGradient>
          <mask id="horror-negative-fill"><rect width="1280" height="720" fill="white"/>
            <ellipse cx="427" cy="445" rx="185" ry="223" fill="url(#horror-light-pool)"/></mask>
          <linearGradient id="horror-beam" x2="1" y2="1"><stop stopColor="#8da7a0" stopOpacity=".13"/>
            <stop offset="1" stopColor="#668185" stopOpacity="0"/></linearGradient>
          <linearGradient id="horror-foreground"><stop stopColor="#02070b" stopOpacity=".96"/>
            <stop offset="1" stopColor="#050c11" stopOpacity=".4"/></linearGradient>
          {win ? <clipPath id="horror-window-panes">
            <path d={`M ${win.x+2} ${win.y+2} h ${win.w/2-7} v ${win.h/2-7} h ${7-win.w/2} Z
              M ${win.x+win.w/2+4} ${win.y+2} h ${win.w/2-6} v ${win.h/2-7} h ${6-win.w/2} Z
              M ${win.x+2} ${win.y+win.h/2+4} h ${win.w/2-7} v ${win.h/2-6} h ${7-win.w/2} Z
              M ${win.x+win.w/2+4} ${win.y+win.h/2+4} h ${win.w/2-6} v ${win.h/2-6} h ${6-win.w/2} Z`}/>
          </clipPath> : null}
        </defs>
        {win ? <g clipPath="url(#horror-window-panes)">
          <rect x={win.x} y={win.y} width={win.w} height={win.h} fill="#384b50" opacity=".47"/>
          <g opacity={presence} transform={`translate(${win.x+win.w*.55+dx} ${win.y+win.h*.42})`}
            data-presence={presence.toFixed(4)}>
            {/* No face or eyes. The mullions occlude most of this exterior shape. */}
            <path d="M -10 -7 Q -11 -26 1 -29 Q 15 -28 13 -10 L 9 5 Q 29 14 29 62 H -27 Q -26 18 -9 7 Z"
              fill="#02080d"/>
          </g>
          <path d={`M ${win.x} ${win.y+win.h*.2} l ${win.w} -11 M ${win.x} ${win.y+win.h*.7} l ${win.w} -16`}
            stroke="#91a2a1" strokeWidth="3" opacity=".12"/>
        </g> : null}
        {/* Negative fill retains the lit face and costume rather than blacking out the scene. */}
        <rect width="1280" height="720" fill="#02080e" opacity=".46" mask="url(#horror-negative-fill)"/>
        <path d="M 294 288 L 345 276 L 523 622 L 438 622 Z" fill="url(#horror-beam)" opacity={.65+spill*.35}/>
        {door ? <g>
          <path d={`M ${door.x+3} ${door.y+door.h-1} H ${door.x+door.w-3}`} stroke="#c5ad72" strokeWidth="2"
            opacity={spill*.65}/>
          <path d={`M ${door.x+door.w*.42} ${door.y+door.h} l -40 45 h 70 l -13 -45 Z`}
            fill="#b49a60" opacity={spill*.035}/>
        </g> : null}
        {/* Near doorway framing gives the small room a visible foreground plane. */}
        <path d="M 0 0 H 1280 V 205 H 0 Z M 0 205 H 289 V 720 H 0 Z" fill="url(#horror-foreground)"/>
        <path d="M 671 205 H 1280 V 720 H 671 Z" fill="#02070c" opacity=".94"/>
        <path d="M 289 205 H 671 M 291 205 V 720 M 670 205 V 720" stroke="#566166" strokeWidth="2" opacity=".22"/>
        <ellipse cx={478+Math.sin(t*.28)*11} cy="606" rx="158" ry="22" fill="#75918f" opacity=".025"/>
      </svg>
    </AbsoluteFill>
  </>;
};
