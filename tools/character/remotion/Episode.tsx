import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {ActorBody, ActorHands} from './Actor';
import {Episode, Fridge, episodeAt} from './shots';

const Svg: React.FC<{svg: string; x: number}> = ({svg, x}) =>
  <div style={{position: 'absolute', left: x, top: 0}} dangerouslySetInnerHTML={{__html: svg}} />;

// Same cup silhouette as the pilot. A camera slightly above the counter sees the
// mouth when upright and the flat foot when inverted, so orientation is readable.
const Cup: React.FC<{cup: number[]; stain: boolean; drip: number}> = ({cup, stain, drip}) => {
  const up = Math.cos(cup[2] * Math.PI / 180);
  return <>
    <g transform={`translate(${cup[0]} ${cup[1]}) rotate(${cup[2]})`}>
      <path d="M 15 -10 C 40 -17 40 18 15 12" fill="none" stroke="#eeeade" strokeWidth="8" />
      <path d="M 15 -10 C 40 -17 40 18 15 12" fill="none" strokeWidth="2" />
      <path d="M -17 -19 L 17 -19 L 14 17 Q 0 23 -14 17 Z" fill="#f2efe5" />
      <path d="M -14.4 12 L 14.4 12 L 14 17 Q 0 23 -14 17 Z" fill="#d6d1c2" strokeWidth="1.5" />
      <path d="M -10 -11 L -8 9" stroke="#fffdf4" strokeWidth="3" />
      {up > 0 ? <g opacity={up}>
        <ellipse cx="0" cy="-19" rx="17" ry="4" fill="#acb2ae" />
        {stain ? <ellipse cx="0" cy="-18.4" rx="12.5" ry="2.2" fill="none" stroke="#7a5636" strokeWidth="1.8" /> : null}
      </g> : null}
      {up < 0 ? <g opacity={-up}>
        <ellipse cx="0" cy="19" rx="14" ry="3.6" fill="#e4e0d2" />
        <ellipse cx="0" cy="19" rx="9" ry="2" fill="none" stroke="#b9b4a5" strokeWidth="1.5" />
      </g> : null}
    </g>
    {/* Water running off the freshly washed, inverted cup onto the rack tray. */}
    {drip >= 0 && drip < 3.2 ? <g fill="#a8e3e5" stroke="none" opacity={Math.min(1, (3.2 - drip) / 0.8)}>
      {[0, 1].map(i => {
        const u = ((drip * 0.9 + i * 0.5) % 1);
        return <ellipse key={i} cx={cup[0] + (i ? 14 : -15) + (i ? -1 : 1) * u * 1.5}
          cy={cup[1] - 12 + u * 30} rx="2" ry="3" />;
      })}
      <ellipse cx={cup[0]} cy={cup[1] + 21} rx={10 + Math.min(drip, 2) * 7} ry="2.2" opacity="0.7" />
    </g> : null}
  </>;
};

// Chair in side view; mirror=true has its back on the right.
const Chair: React.FC<{x: number; y: number; mirror: boolean; rot: number}> = ({x, y, mirror, rot}) =>
  <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${mirror ? -1 : 1} 1)`}
    stroke="#1b2e38" strokeWidth="3" strokeLinejoin="round">
    <path d="M -4 0 V -132" stroke="#3a3230" strokeWidth="9" />
    <path d="M -2 -128 Q 8 -126 10 -100 V -62 H -2 Z" fill="#6d5a4c" />
    <path d="M -6 -56 H 42 V -46 H -6 Z" fill="#7f6957" />
    <path d="M 0 -46 V 0 M 38 -46 V 0" stroke="#3a3230" strokeWidth="7" />
  </g>;

const FridgeDoor: React.FC<{f: Fridge; angle: number}> = ({f, angle}) => {
  const th = angle * Math.PI / 180, c = Math.cos(th), s = Math.sin(th);
  const xe = f.hinge_x + f.width * c, d = 10 * s, h = f.hinge_x;
  const open = Math.min(1, angle / 25);
  return <g stroke="#1d303b" strokeLinejoin="round">
    {open > 0 ? <g opacity={open}>
      <rect x={h + 4} y={f.top + 2} width={f.width - 8} height={f.bottom - f.top - 4} fill="#dfe7da" strokeWidth="3" />
      <path d={`M ${h + 6} ${f.top + 66} H ${h + f.width - 6} M ${h + 6} ${f.top + 128} H ${h + f.width - 6} M ${h + 6} ${f.top + 186} H ${h + f.width - 6}`}
        stroke="#9fb2b0" strokeWidth="4" />
      {/* The 2 L bottle on the middle shelf, two thirds full, as in the insert. */}
      <path d={`M ${h + 66} ${f.top + 128} V ${f.top + 86} Q ${h + 66} ${f.top + 80} ${h + 71} ${f.top + 76} V ${f.top + 70} H ${h + 77} V ${f.top + 76} Q ${h + 82} ${f.top + 80} ${h + 82} ${f.top + 86} V ${f.top + 128} Z`}
        fill="#e8eff0" fillOpacity=".7" strokeWidth="2" />
      <path d={`M ${h + 67} ${f.top + 127} V ${f.top + 98} H ${h + 81} V ${f.top + 127} Z`} fill="#8fc3cf" stroke="none" />
      <rect x={h + 18} y={f.top + 98} width="34" height="30" rx="4" fill="#c9d1cb" strokeWidth="2" />
      <rect x={h + 100} y={f.top + 156} width="28" height="30" rx="3" fill="#a28d68" strokeWidth="2" />
    </g> : null}
    <path d={`M ${h} ${f.top} L ${xe} ${f.top - d} L ${xe} ${f.bottom + d} L ${h} ${f.bottom} Z`}
      fill={c >= 0 ? '#9aa8a6' : '#c4cdc7'} strokeWidth="3" />
    {c < 0 ? <path d={`M ${h} ${f.top + 70} L ${xe} ${f.top + 70 - d * .7} M ${h} ${f.top + 150} L ${xe} ${f.top + 150 - d * .4}`}
      stroke="#8a9a98" strokeWidth="4" /> : null}
    {c > 0.08 ? <path d={`M ${h + (f.width - f.handle_inset) * c} ${f.handle_y - 40} V ${f.handle_y + 40}`}
      stroke="#d3d8cf" strokeWidth={2 + 4 * c} strokeLinecap="round" /> : null}
  </g>;
};

export const EpisodeScene: React.FC<Episode> = (ep) => {
  const frame = useCurrentFrame(), {fps} = useVideoConfig(), t = frame / fps;
  const e = episodeAt(ep, t), s = e.actor, w = ep.world, shot = e.shot;
  const [cx, cy, zoom] = e.camera;
  const camera = `translate(640px, 360px) scale(${zoom}) translate(${-cx}px, ${-cy}px)`;
  const caption = ep.narration.find(n => t >= n.start_seconds && t < n.end_seconds);
  const mirror = s.facing < 0 ? `matrix(-1 0 0 1 ${2 * s.root[0]} 0)` : undefined;
  const glow = Math.min(1, e.door / 70);
  const viewBox = `${w.x0} 0 ${w.width} 720`;
  return <AbsoluteFill style={{background: '#0b141a', overflow: 'hidden'}}>
    {shot.view === 'insert' ? <div style={{position: 'absolute', left: 0, top: 0, width: 1280, height: 720,
      transformOrigin: '0 0', transform: camera}} dangerouslySetInnerHTML={{__html: shot.insert_svg ?? ''}} /> :
    <div style={{position: 'absolute', left: 0, top: 0, width: 1280, height: 720, transformOrigin: '0 0', transform: camera}}>
      {w.layers.map((l, i) => <Svg key={i} {...l} />)}
      <div style={{position: 'absolute', left: 0, top: 0, opacity: e.day}}><Svg {...w.day_window} /></div>
      <svg width={w.width} height="720" viewBox={viewBox} style={{position: 'absolute', left: w.x0, top: 0}}>
        <Chair x={w.chair_a.x} y={w.chair_a.y} mirror={false} rot={0} />
        <Chair x={w.chair_b.x + e.chair[0]} y={w.chair_b.y} mirror rot={e.chair[1]} />
        <FridgeDoor f={w.fridge} angle={e.door} />
      </svg>
      {w.items_over.map((l, i) => <Svg key={i} {...l} />)}
      <svg width={w.width} height="720" viewBox={viewBox} style={{position: 'absolute', left: w.x0, top: 0}}>
        <defs>
          <clipPath id="ep-cup-clip"><path clipRule="evenodd"
            d={`M ${w.x0} 0 h ${w.width} v 720 h ${-w.width} Z ${w.cup_occluder}`} /></clipPath>
          <radialGradient id="ep-fridge-glow"><stop stopColor="#e9f3ea" stopOpacity=".42" />
          <stop offset="1" stopColor="#e9f3ea" stopOpacity="0" /></radialGradient>
        </defs>
        <g stroke="#17242b" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round">
          {s.water ? <g stroke="#a8e3e5" fill="none" opacity="0.8">
            <path d="M 516 420 L 516 487" strokeWidth="5" />
            {[0, 1, 2, 3, 4].map(i => <path key={i} strokeWidth="2"
              d={`M ${503+i*6} ${480+((e.mt*55+i*9)%13)} l ${i-2} 6`} />)}
          </g> : null}
          {shot.actor_visible ? <g transform={mirror}><ActorBody s={s} look={ep.look} t={e.mt} /></g> : null}
          <g clipPath="url(#ep-cup-clip)"><Cup cup={s.cup} stain={shot.stain_until != null && e.mt < shot.stain_until} drip={e.drip} /></g>
          {shot.actor_visible ? <g transform={mirror}><ActorHands s={s} look={ep.look} /></g> : null}
        </g>
        {glow > 0 ? <ellipse cx={w.fridge.hinge_x + w.fridge.width + 40} cy={(w.fridge.top + w.fridge.bottom) / 2}
          rx="190" ry="240" fill="url(#ep-fridge-glow)" opacity={glow} style={{mixBlendMode: 'screen'}} /> : null}
      </svg>
      {w.foreground.map((l, i) => <Svg key={i} {...l} />)}
    </div>}
    {/* Morning grade: cool daylight lift; the approved night look is the zero point. */}
    {e.day > 0 ? <div style={{position: 'absolute', inset: 0, background: '#e9e1cc', mixBlendMode: 'soft-light',
      opacity: 0.55 * e.day}} /> : null}
    {shot.view === 'insert' && e.day < 1 ? <div style={{position: 'absolute', inset: 0, background: '#0b1620',
      opacity: 0.55 * (1 - e.day)}} /> : null}
    {e.dark > 0 ? <div style={{position: 'absolute', inset: 0, background: '#000', opacity: e.dark}} /> : null}
    {caption ? <div style={{position: 'absolute', bottom: 24, left: 100, right: 100, textAlign: 'center',
      fontFamily: 'Arial, sans-serif', fontSize: 29, fontWeight: 500, color: '#f8f6ed'}}>
      <span style={{background: 'rgba(9,16,22,.88)', padding: '9px 20px', borderRadius: 5}}>{caption.text}</span>
    </div> : null}
    {ep.narration.map((n, i) => <Sequence key={`n${i}`} from={Math.round(n.start_seconds * fps)}
      durationInFrames={Math.ceil((n.end_seconds - n.start_seconds) * fps)} layout="none">
      <Audio src={staticFile(n.path)} />
    </Sequence>)}
    {ep.sfx.map((x, i) => <Sequence key={`s${i}`} from={Math.round(x.start_seconds * fps)}
      durationInFrames={Math.max(1, Math.ceil(x.duration_seconds * fps))} layout="none">
      <Audio src={staticFile(x.path)} volume={x.volume} />
    </Sequence>)}
  </AbsoluteFill>;
};
