import React from 'react';
import {Motion, Point, stateAt} from './motion';
import {CartoonHorrorBody, CartoonHorrorHands} from './CartoonHorror';
import {CastBody, CastDesign, CastHands} from './CartoonCast';

// Minh v1 drawing, shared by the single-shot pilot and multi-shot episodes.
// With a neutral face the emitted SVG is identical to the original pilot rig.
type State = ReturnType<typeof stateAt>;
type Look = Pick<Motion['actor'], 'shirt' | 'skin' | 'hair'> & {treatment?: 'cinematic'; design?: CastDesign};
export type ActorSkin = 'cartoon' | 'stickman_horror' | 'cartoon_horror';

const line = (a: Point, b: Point) => `M ${a.join(' ')} L ${b.join(' ')}`;
export const chain = (a: Point, b: Point, c: Point) => `${line(a, b)} L ${c.join(' ')}`;

const StickmanBody: React.FC<{s: State; t: number}> = ({s, t}) => {
  const [brow, gx, gy, mouth, lid, tilt] = s.face;
  const [hx, hy] = s.head;
  const blink = t % 4.9 > 4.72 || lid > 0.8;
  return <g data-skin="stickman_horror" fill="none" stroke="#e3e8e3" strokeLinecap="round" strokeLinejoin="round">
    <ellipse cx={(s.lf[0] + s.rf[0]) / 2} cy={Math.max(s.lf[1], s.rf[1]) + 4}
      rx="34" ry="5" fill="#03080d" stroke="none" opacity="0.55" />
    <path d={chain(s.hip, s.lk, s.lf)} stroke="#91a6ae" strokeWidth="8" />
    <path d={chain(s.shoulder, s.le, s.left)} stroke="#91a6ae" strokeWidth="7" />
    <path d={line(s.shoulder, s.hip)} strokeWidth="10" />
    <path d={chain(s.hip, s.rk, s.rf)} strokeWidth="8" />
    <path d={chain(s.shoulder, s.re, s.right)} strokeWidth="7" />
    {[s.lf, s.rf].map((p, i) => <path key={i} d={`M ${p[0] - 5} ${p[1]} h 14`} strokeWidth="6" />)}
    {[s.lk, s.rk, s.le, s.re].map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="3" fill="#edf1e9" stroke="none" />)}
    <path d={`M ${s.shoulder[0]} ${s.shoulder[1]} L ${hx} ${hy + 31}`} strokeWidth="7" />
    <g transform={`rotate(${tilt} ${hx} ${hy + 31})`}>
      <circle cx={hx} cy={hy} r="32" fill="#14212c" strokeWidth="7" />
      {blink ? <path d={`M ${hx + 1} ${hy - 1} h 6 M ${hx + 15} ${hy - 1} h 6`} strokeWidth="2" /> : <>
        <circle cx={hx + 4 + gx} cy={hy - 2 + gy} r={brow > 1 ? 3.5 : 2.7} fill="#f5eed8" stroke="none" />
        <circle cx={hx + 18 + gx} cy={hy - 2 + gy} r={brow > 1 ? 3.5 : 2.7} fill="#f5eed8" stroke="none" />
      </>}
      <path d={`M ${hx} ${hy - 11} l 8 ${-brow * 2} M ${hx + 14} ${hy - 11 - brow * 2} l 9 ${brow * 2}`}
        strokeWidth="2" />
      {mouth < -0.65 ? <ellipse cx={hx + 10} cy={hy + 15} rx="3.5" ry={3 - mouth * 4} strokeWidth="2" />
        : <path d={`M ${hx + 7} ${hy + 13} q 5 ${mouth * 3} 10 0`} strokeWidth="2" />}
    </g>
  </g>;
};

export const ActorBody: React.FC<{s: State; look: Look; t: number; skin?: ActorSkin}> = ({s, look, t, skin}) => {
  if (skin === 'stickman_horror') return <StickmanBody s={s} t={t} />;
  if (skin === 'cartoon_horror') return look.design ? <CastBody s={s} d={look.design} t={t} />
    : <CartoonHorrorBody s={s} look={look} t={t} />;
  const x = s.root[0], y = s.root[1];
  const headX = x + 10, headY = y - 161;
  const blink = (t % 4.9) > 4.72;
  const [brow, gx, gy, mouth, lid, tilt] = s.face;
  const base = `translate(${headX} ${headY}) scale(1.18) translate(${-headX} ${-headY})`;
  const headTransform = tilt ? `rotate(${tilt} ${headX} ${headY + 30}) ${base}` : base;
  return <>
    <ellipse cx={x} cy={s.lf[1]+6} rx="47" ry="8" fill="#101d23" opacity="0.35" stroke="none" />
    {/* Far limbs, filled trousers, then torso and near limbs. */}
    <path d={chain(s.hip, s.lk, s.lf)} fill="none" stroke="#233541" strokeWidth="22" />
    <path d={chain(s.hip, s.rk, s.rf)} fill="none" stroke="#334550" strokeWidth="22" />
    {[s.lf,s.rf].map((p,i) => <path key={i} d={`M ${p[0]-10} ${p[1]-4} q 13 -4 28 1 l 2 7 h -32 z`} fill="#5b4c42" />)}
    <path d={chain(s.shoulder, s.le, s.left)} fill="none" stroke="#305b5d" strokeWidth="17" />
    <path d={`M ${x-15} ${y-107} Q ${x+4} ${y-116} ${x+24} ${y-99} L ${x+22} ${y+5} Q ${x} ${y+15} ${x-23} ${y+3} Z`}
      fill={look.shirt} />
    <path d={`M ${x+14} ${y-91} L ${x+13} ${y-8}`} stroke="#355f62" strokeWidth="2" />
    <path d={`M ${x-18} ${y-6} Q ${x+1} ${y} ${x+21} ${y-6}`} fill="none" stroke="#93a2a0" strokeWidth="2" />
    <path d={chain(s.shoulder, s.re, s.right)} fill="none" stroke="#17242b" strokeWidth="21" />
    <path d={chain(s.shoulder, s.re, s.right)} fill="none" stroke={look.shirt} strokeWidth="16" />
    <path d={`M ${headX-10} ${headY+30} v 21 q 10 11 19 0 v -21`} fill={look.skin} />
    <g transform={headTransform}>
    <path d={`M ${headX-30} ${headY-12} Q ${headX-29} ${headY-43} ${headX+3} ${headY-42} Q ${headX+35} ${headY-40} ${headX+33} ${headY-9} l 7 15 -10 4 Q ${headX+29} ${headY+35} ${headX+6} ${headY+38} Q ${headX-25} ${headY+32} ${headX-29} ${headY+9} Z`}
      fill={look.skin} />
    <ellipse cx={headX-27} cy={headY+4} rx="7" ry="10" fill={look.skin} />
    <path d={`M ${headX-32} ${headY+1} Q ${headX-43} ${headY-33} ${headX-19} ${headY-42} Q ${headX+5} ${headY-60} ${headX+32} ${headY-29} L ${headX+18} ${headY-30} ${headX+2} ${headY-22} ${headX-16} ${headY-26} ${headX-24} ${headY+4} Z`}
      fill={look.hair} />
    <path d={`M ${headX+1} ${headY-11} l 10 ${-1-3*brow} M ${headX+19} ${headY-13-3*brow} l 8 ${2+3*brow}`} strokeWidth="3" />
    {blink ? <path d={`M ${headX+2} ${headY-2} h 8 M ${headX+21} ${headY-3} h 6`} /> : <g>
      <ellipse cx={headX+7+gx} cy={headY-1+gy} rx="3.5" ry="6" fill="#17242b" />
      <ellipse cx={headX+24+gx} cy={headY-2+gy} rx="3" ry="6" fill="#17242b" />
    </g>}
    {/* Heavy upper lids cover the top of each eye; omitted when fully open. */}
    {!blink && lid > 0.01 ? <path d={`M ${headX+2} ${headY-8} h 10 v ${12*lid} h -10 Z M ${headX+20} ${headY-9} h 9 v ${12*lid} h -9 Z`}
      fill={look.skin} stroke="none" /> : null}
    <path d={`M ${headX+9} ${headY+24} q 7 ${-1+3*mouth} 13 0`} fill="none" strokeWidth="2" />
    <path d={`M ${headX-8} ${headY+12} q 4 4 8 0`} opacity="0.25" fill="none" />
    </g>
  </>;
};

export const ActorHands: React.FC<{s: State; look: Look; skin?: ActorSkin}> = ({s, look, skin}) => skin === 'cartoon_horror'
  ? look.design ? <CastHands s={s} d={look.design} /> : <CartoonHorrorHands s={s} look={look} /> : skin === 'stickman_horror'
  ? <>{[s.left, s.right].map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="4" fill="#e3e8e3" />)}</> : <>
  {[s.left,s.right].map((p,i) => <g key={i} transform={`translate(${p[0]} ${p[1]})`}>
    <ellipse rx="8" ry="10" fill={look.skin} />
    <path d="M 0 -4 l 4 1 M 0 0 l 4 1" stroke="#a77f65" strokeWidth="1" />
  </g>)}
</>;
