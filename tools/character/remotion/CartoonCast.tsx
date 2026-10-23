import React from 'react';
import {Point, stateAt} from './motion';

// P3.2A data-driven cast artwork over the shared two-bone IK. The design comes from
// the asset library (tools/character/horror_assets.py); no solver or clock lives here.
type State = ReturnType<typeof stateAt>;
type Feature = {d: string; fill?: string; stroke?: string; width?: number; opacity?: number};
export type CastDesign = {
  id: string; revision: number;
  palette: {skin: string; hair: string; top: string; top_shade: string; bottom: string; shoes: string; accent: string};
  build: {shoulder: number; hip: number; sleeve: number; leg: number; head: number; hand: number};
  outfit: 'long_coat' | 'cardigan'; footwear: 'boots' | 'shoes';
  face: {outline: string; shade: string; ear: Point; nose: string; mouth: [number, number, number];
    eyes: {shape: 'almond' | 'round'; left: [number, number, number]; right: [number, number, number]; iris: string};
    brow: {width: number; color?: string}};
  hair: {back?: string; front: string; highlight?: string};
  features: Feature[];
};
const chain = (a: Point, b: Point, c: Point) => `M ${a} L ${b} L ${c}`;
const angle = (a: Point, b: Point) => Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI - 90;
const INK = '#111b22';

const Limb: React.FC<{a: Point; b: Point; c: Point; width: number; color: string; shade?: boolean}> = ({a, b, c, width, color, shade}) => <>
  <path d={chain(a, b, c)} fill="none" stroke={INK} strokeWidth={width + 5} />
  <path d={chain(a, b, c)} fill="none" stroke={color} strokeWidth={width} />
  {shade ? <path d={chain(a, b, c)} fill="none" stroke="#0d171d" strokeOpacity=".34" strokeWidth={width} /> : null}
</>;

const Foot: React.FC<{f: Point; k: Point; d: CastDesign; far: boolean}> = ({f, k, d, far}) => {
  const fill = far ? '#151417' : d.palette.shoes;
  return <g>
    {d.footwear === 'boots' ? <path d={`M ${f[0] - 9} ${f[1] - 26} L ${f[0] + 8} ${f[1] - 24} L ${f[0] + 9} ${f[1] - 8} L ${f[0] - 10} ${f[1] - 8} Z`}
      fill={fill} transform={`rotate(${Math.max(-25, Math.min(25, angle(k, f) * .4))} ${f[0]} ${f[1] - 8})`} /> : null}
    <path d={`M ${f[0] - 11} ${f[1] - 10} q 9 -4 18 1 l 12 5 q 5 3 3 8 h -34 Z`} fill={fill} />
    <path d={`M ${f[0] - 11} ${f[1] + 2} h 33`} stroke={d.footwear === 'boots' ? '#3a3534' : '#5d4d40'} strokeWidth="3" />
  </g>;
};

export const CastBody: React.FC<{s: State; d: CastDesign; t: number}> = ({s, d, t}) => {
  const [x, y] = s.hip, [sx, sy] = s.shoulder, [hx, hy] = s.head;
  const [brow, gx, gy, mouth, lid, tilt] = s.face;
  const p = d.palette, b = d.build, W = b.shoulder, H = b.hip;
  const blink = t % 4.9 > 4.72 || lid > .8;
  const head = `translate(${hx} ${hy}) rotate(${tilt} 0 29) scale(${b.head})`;
  const kneeY = (s.lk[1] + s.rk[1]) / 2, kneeL = Math.min(s.lk[0], s.rk[0]), kneeR = Math.max(s.lk[0], s.rk[0]);
  const sleeve = (e: Point, w: Point, far: boolean) => <g>
    <Limb a={s.shoulder} b={e} c={w} width={b.sleeve} color={p.top} shade={far} />
    <path d={chain(s.shoulder, e, w)} fill="none" stroke="#a0a495" strokeOpacity=".16" strokeWidth="1.2" />
    <g transform={`translate(${w}) rotate(${angle(e, w)})`}>
      <path d={`M ${-b.sleeve / 2 - 1} -12 H ${b.sleeve / 2 + 1} V -3 H ${-b.sleeve / 2 - 1} Z`} fill={p.top_shade} strokeWidth="1.4" />
    </g>
  </g>;
  const eyeH = d.face.eyes.shape === 'almond' ? 3.2 + Math.max(0, brow) * 1.1 : 2.7 + Math.max(0, brow) * .9;
  const [mx, my, mw] = d.face.mouth;
  return <g data-skin="cartoon_horror" data-character={d.id} data-revision={d.revision}
    stroke={INK} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round">
    <ellipse cx={(s.lf[0] + s.rf[0]) / 2} cy={Math.max(s.lf[1], s.rf[1]) + 4} rx={30 + H / 2} ry="6"
      fill="#03080e" opacity=".65" stroke="none" />
    {d.hair.back ? <g transform={head} data-part="hair-back"><path d={d.hair.back} fill={p.hair} /></g> : null}
    {[{k: s.lk, f: s.lf, far: true}, {k: s.rk, f: s.rf, far: false}].map(({k, f, far}, i) => <g key={i}>
      <Limb a={s.hip} b={k} c={f} width={b.leg} color={p.bottom} shade={far} />
      <Foot f={f} k={k} d={d} far={far} />
    </g>)}
    {sleeve(s.le, s.left, true)}
    {d.outfit === 'long_coat' ? <g data-part="coat-skirt">
      <path d={`M ${x - H} ${y - 6} L ${kneeL - 15} ${kneeY + 14} Q ${(kneeL + kneeR) / 2} ${kneeY + 20} ${kneeR + 17} ${kneeY + 12} L ${x + H + 2} ${y - 4} Z`}
        fill={p.top} />
      <path d={`M ${x + 3} ${y + 2} L ${(kneeL + kneeR) / 2 + 4} ${kneeY + 17}`} fill="none" stroke={p.top_shade} strokeWidth="1.6" />
    </g> : null}
    <path data-part="torso" d={d.outfit === 'cardigan'
      ? `M ${sx - W} ${sy - 7} Q ${sx} ${sy - 19} ${sx + W + 2} ${sy - 4} Q ${x + H + 8} ${(sy + y) / 2 + 6} ${x + H} ${y + 8} Q ${x} ${y + 17} ${x - H} ${y + 6} Z`
      : `M ${sx - W} ${sy - 7} Q ${sx} ${sy - 19} ${sx + W + 2} ${sy - 4} L ${x + H} ${y + 2} Q ${x} ${y + 10} ${x - H} ${y} Z`}
      fill={p.top} />
    <path d={`M ${sx - W + 2} ${sy + 2} Q ${sx - 9} ${sy + 33} ${x - H + 6} ${y} L ${x - H} ${y} Z`} fill={p.top_shade} opacity=".55" stroke="none" />
    <path d={`M ${sx + 8} ${sy - 7} L ${sx + W + 1} ${sy - 4} L ${x + H} ${y + 3} L ${x + 1} ${y + 7} Z`} fill="#08171c" opacity=".42" stroke="none" />
    {d.outfit === 'long_coat' ? <g data-part="coat">
      <path d={`M ${sx - 9} ${sy - 4} L ${sx + 2} ${sy + 32} L ${sx + 13} ${sy - 3}`} fill={p.top_shade} strokeWidth="1.6" />
      <path d={`M ${x - H + 1} ${y - 19} Q ${x} ${y - 13} ${x + H} ${y - 17}`} fill="none" stroke={p.accent} strokeWidth="5" />
      <rect x={x + 2} y={y - 22} width="8" height="9" rx="1" fill="none" stroke="#b49a62" strokeWidth="1.4" />
    </g> : <g data-part="cardigan">
      <path d={`M ${sx - 8} ${sy - 5} L ${sx + 2} ${sy + 12} L ${sx + 12} ${sy - 5} Z`} fill={p.accent} strokeWidth="1.4" />
      <path d={`M ${sx + 2} ${sy + 12} L ${x + 4} ${y + 12}`} fill="none" stroke={p.top_shade} strokeWidth="2.4" />
      {[0.35, 0.58, 0.8].map(u => <circle key={u} cx={sx + 2 + (x + 4 - sx - 2) * u + 4} cy={sy + 12 + (y - sy) * u}
        r="2.1" fill="#2a2418" strokeWidth="1" />)}
      <path d={`M ${x - H + 2} ${y + 1} Q ${x} ${y + 11} ${x + H} ${y + 3}`} fill="none" stroke={p.top_shade} strokeWidth="4" />
      <path d={`M ${sx - W + 8} ${sy + 22} q 8 3 14 0 M ${sx - W + 6} ${sy + 46} q 8 3 14 0`} fill="none" stroke="#7d6c48" strokeWidth="1.1" opacity=".5" />
    </g>}
    {sleeve(s.re, s.right, false)}
    <path d={`M ${sx - 8} ${sy - 5} L ${hx - 8} ${hy + 26 * b.head} H ${hx + 9} L ${sx + 11} ${sy - 5} Q ${sx + 2} ${sy + 6} ${sx - 8} ${sy - 5}`}
      fill={p.skin} />
    <g transform={head} data-part="face">
      {/* Identity: everything here is fixed per character revision (no expression input). */}
      <g data-part="identity">
        <defs><clipPath id={`cast-face-${d.id}`}><path d={d.face.outline} /></clipPath></defs>
        <path d={d.face.outline} fill={p.skin} />
        <path d={d.face.shade} fill="#7d5a4c" opacity=".42" stroke="none" clipPath={`url(#cast-face-${d.id})`} />
        <ellipse cx={d.face.ear[0]} cy={d.face.ear[1]} rx="7" ry="10" fill={p.skin} />
        <path d={`M ${d.face.ear[0] - 3} ${d.face.ear[1] - 2} q 6 -5 6 5`} fill="none" stroke="#8e6a5c" strokeWidth="1.4" />
        <path d={d.hair.front} fill={p.hair} data-part="hair" />
        {d.hair.highlight ? <path d={d.hair.highlight} fill="none" stroke="#d8d2c4" strokeOpacity=".22" strokeWidth="2" /> : null}
        <path d={d.face.nose} fill="none" stroke="#7d5a4f" strokeWidth="1.5" />
        {d.features.map((f, i) => <path key={i} d={f.d} fill={f.fill ?? 'none'} stroke={f.stroke ?? 'none'}
          strokeWidth={f.width ?? 1} opacity={f.opacity ?? 1} />)}
      </g>
      <g data-part="expression">
        {[{e: d.face.eyes.left, dx: 0}, {e: d.face.eyes.right, dx: 1}].map(({e, dx}) => {
          const [ex, ey] = e;
          return <path key={dx} d={dx ? `M ${ex - 6} ${ey - 11 - brow * 4} l 10 ${3 + brow * 3}` : `M ${ex - 7} ${ey - 11 - brow * 3} l 11 ${-2 - brow * 2}`}
            fill="none" stroke={d.face.brow.color ?? p.hair} strokeWidth={d.face.brow.width} />;
        })}
        {blink ? <path d={`M ${d.face.eyes.left[0] - 6} ${d.face.eyes.left[1]} h 11 M ${d.face.eyes.right[0] - 5} ${d.face.eyes.right[1]} h 10`}
          fill="none" strokeWidth="2.4" /> : <g data-part="eyes">
          {[d.face.eyes.left, d.face.eyes.right].map(([ex, ey, rx], i) => <g key={i}>
            {d.face.eyes.shape === 'almond'
              ? <path d={`M ${ex - rx} ${ey} Q ${ex} ${ey - eyeH * 1.8} ${ex + rx} ${ey} Q ${ex} ${ey + eyeH * 1.65} ${ex - rx} ${ey} Z`} fill="#bfc4b8" strokeWidth="1.4" />
              : <ellipse cx={ex} cy={ey} rx={rx} ry={eyeH * 1.15} fill="#c4c6bc" strokeWidth="1.4" />}
            <ellipse cx={ex + gx * .42} cy={ey + gy * .5} rx="2.4" ry="2.9" fill={d.face.eyes.iris} stroke="none" />
            <ellipse cx={ex + gx * .42} cy={ey + gy * .5} rx="1.3" ry="2.2" fill="#0d151d" stroke="none" />
            <circle cx={ex - 1 + gx * .42} cy={ey - 1.6 + gy * .5} r=".6" fill="#f6eddb" stroke="none" />
            {lid > .01 ? <path d={`M ${ex - rx - 1} ${ey - eyeH * 1.8} h ${2 * rx + 2} v ${eyeH * 1.8 * lid} h ${-2 * rx - 2} Z`}
              fill={p.skin} stroke="none" /> : null}
          </g>)}
        </g>}
        {mouth < -.65 ? <path d={`M ${mx - 6} ${my} Q ${mx} ${my - 3} ${mx + 6} ${my - 1} L ${mx + 5} ${my + 3} Q ${mx} ${my + 1} ${mx - 5} ${my + 4} Z`}
          fill="#443335" strokeWidth="1.2" data-expression="held-breath" />
          : <path d={`M ${mx - mw / 2} ${my} Q ${mx} ${my - 2 + mouth * 9} ${mx + mw / 2} ${my - 1}`} fill="none" stroke="#5e4644" strokeWidth="2" />}
      </g>
      <path d="M 12 -33 L 31 -17 L 32 -1 L 39 7 L 31 12 L 27 27 L 13 39 L 3 36 L 14 24 L 9 13 L 15 7 L 11 -5 Z"
        fill="#0b2028" opacity=".38" stroke="none" clipPath={`url(#cast-face-${d.id})`} data-part="directional-face-shadow" />
    </g>
  </g>;
};

export const CastHands: React.FC<{s: State; d: CastDesign}> = ({s, d}) => <g data-part="hands" data-character={d.id}
  stroke="#292a30" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round">
  {[{p: s.left, e: s.le}, {p: s.right, e: s.re}].map(({p, e}, i) =>
    <g key={i} transform={`translate(${p}) rotate(${angle(e, p)}) scale(${d.build.hand})`}>
      <path d="M -6 -3 L -7 5 Q -6 10 -4 13 Q -2 15 0 12 L -1 4 L 2 12 Q 4 13 5 10 L 4 1 L 8 3 Q 11 2 9 -1 L 5 -5 Z" fill={d.palette.skin} />
      <path d="M -4 4 l 6 1 M -3 8 l 5 1" fill="none" stroke="#a07969" strokeWidth="1" />
    </g>)}
</g>;
