import React from 'react';
import {Motion, Point, stateAt} from './motion';

// Artwork over the shared two-bone IK. No independent animation clock or solver.
type State = ReturnType<typeof stateAt>;
type Look = Pick<Motion['actor'], 'shirt' | 'skin' | 'hair'> & {treatment?: 'cinematic'};
const chain = (a: Point, b: Point, c: Point) => `M ${a} L ${b} L ${c}`;
const angle = (a: Point, b: Point) => Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI - 90;

export const CartoonHorrorBody: React.FC<{s: State; look: Look; t: number}> = ({s, look, t}) => {
  const [x, y] = s.hip, [sx, sy] = s.shoulder, [hx, hy] = s.head;
  const [brow, gx, gy, mouth, lid, tilt] = s.face;
  const cinematic = look.treatment === 'cinematic';
  const blink = t % 4.9 > 4.72 || lid > .8;
  const eyeHeight = cinematic ? 3.2 + Math.max(0, brow) * 1.1 : 5.5 + Math.max(0, brow) * 2.3;
  const sleeve = (elbow: Point, wrist: Point, far: boolean) => <g>
    <path d={chain(s.shoulder, elbow, wrist)} fill="none" stroke="#101b24" strokeWidth="24" />
    <path d={chain(s.shoulder, elbow, wrist)} fill="none" stroke={look.shirt} strokeWidth="19" />
    {far ? <path d={chain(s.shoulder, elbow, wrist)} fill="none" stroke="#15232b" strokeOpacity=".32" strokeWidth="19" /> : null}
    {cinematic ? <path d={chain(s.shoulder,elbow,wrist)} fill="none" stroke="#a0a495" strokeOpacity=".19" strokeWidth="1.2" /> : null}
    <g transform={`translate(${wrist}) rotate(${angle(elbow, wrist)})`}>
      <path d="M -9 -12 H 9 V -3 H -9 Z" fill="#463e43" strokeWidth="1.5" />
      <path d="M -6 -10 V -5 M -2 -10 V -5 M 2 -10 V -5 M 6 -10 V -5" stroke="#a28178" strokeWidth=".7" />
    </g>
  </g>;
  return <g data-skin="cartoon_horror" stroke="#131f29" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round">
    <ellipse cx={(s.lf[0] + s.rf[0]) / 2} cy={Math.max(s.lf[1], s.rf[1]) + 4}
      rx="39" ry="6" fill="#03080e" opacity=".65" stroke="none" />
    {[{k:s.lk, f:s.lf, far:true}, {k:s.rk, f:s.rf, far:false}].map(({k,f,far}, i) => <g key={i}>
      <path d={chain(s.hip,k,f)} fill="none" stroke="#111d28" strokeWidth="27" />
      <path d={chain(s.hip,k,f)} fill="none" stroke={far ? '#293747' : '#3d4b5a'} strokeWidth="22" />
      <path d={`M ${k[0]-5} ${k[1]-8} l 9 3`} fill="none" stroke="#697581" strokeWidth="1.3" opacity=".5" />
      <path d={`M ${f[0]-11} ${f[1]-11} q 9 -4 18 1 l 12 5 q 5 3 3 8 h -34 Z`} fill={far ? '#29323c' : '#42464d'} />
      <path d={`M ${f[0]-11} ${f[1]+2} h 33`} stroke="#a4aaa7" strokeWidth="3" />
      <path d={`M ${f[0]+2} ${f[1]-8} l 5 2 m -2 -5 l 5 2`} stroke="#a0a6a4" strokeWidth="1.3" />
    </g>)}
    {sleeve(s.le,s.left,true)}
    {/* Shoulder and hem follow posture independently; clothing stays attached on a flinch/lean. */}
    <path d={`M ${sx-23} ${sy-7} Q ${sx} ${sy-19} ${sx+25} ${sy-4}
      L ${x+26} ${y+5} Q ${x} ${y+16} ${x-26} ${y+3} Z`} fill={look.shirt} />
    <path d={`M ${sx-21} ${sy+2} Q ${sx-9} ${sy+33} ${x-18} ${y+3} L ${x-26} ${y+3} Z`}
      fill="#172731" opacity=".3" stroke="none" />
    {cinematic ? <path d={`M ${sx+8} ${sy-7} L ${sx+24} ${sy-4} L ${x+26} ${y+5} L ${x+1} ${y+9} Z`}
      fill="#08171c" opacity=".5" stroke="none" /> : null}
    <path d={`M ${x-22} ${y-24} Q ${x} ${y-12} ${x+21} ${y-24} L ${x+16} ${y-8} H ${x-17} Z`}
      fill="#433d42" opacity=".5" strokeWidth="1" />
    <path d={`M ${x-25} ${y+1} Q ${x} ${y+9} ${x+25} ${y+2}`} fill="none" stroke="#bd8877" strokeWidth="2" opacity=".55" />
    <path d={`M ${sx-10} ${sy-1} Q ${sx} ${sy+12} ${sx+12} ${sy-1}`} fill="none" stroke="#4a393d" strokeWidth="10" />
    <path d={`M ${sx-11} ${sy+4} l 1 27 M ${sx+10} ${sy+4} l 1 24`} stroke="#d6bc9e" strokeWidth="1.8" />
    {sleeve(s.re,s.right,false)}
    <path d={`M ${sx-8} ${sy-5} L ${hx-9} ${hy+26} H ${hx+9} L ${sx+11} ${sy-5} Q ${sx+2} ${sy+6} ${sx-8} ${sy-5}`}
      fill={look.skin} />
    <g transform={`translate(${hx} ${hy}) rotate(${tilt} 0 29)${cinematic ? ' translate(0 29) scale(.87 .98) translate(0 -29)' : ''}`} data-part="face">
      <path d={cinematic ? 'M -30 -17 Q -27 -42 3 -41 Q 32 -40 33 -15 L 32 -1 L 39 7 L 31 12 L 27 27 L 13 39 L -3 36 L -23 20 L -31 7 Z'
        : 'M -30 -17 Q -27 -42 3 -41 Q 32 -40 33 -15 L 33 -1 L 40 7 L 32 12\n        Q 30 35 11 40 Q -15 39 -27 20 L -31 7 Z'} fill={look.skin} />
      <path d="M 24 -25 Q 37 -12 31 16 Q 28 31 12 38 Q 29 38 32 12 L 40 7 L 33 -1 L 33 -15 Z"
        fill="#9d7063" opacity=".45" stroke="none" />
      <ellipse cx="-29" cy="7" rx="7" ry="10" fill={look.skin} />
      <path d="M -32 5 q 6 -5 6 5" fill="none" stroke="#a27668" strokeWidth="1.4" />
      <path d="M -33 7 L -38 -15 L -33 -29 L -39 -35 L -24 -35 L -20 -46 L -10 -42
        Q 10 -54 29 -37 L 38 -23 L 29 -20 L 21 -29 L 13 -19 L 5 -26 L -6 -18 L -16 -24 L -22 3 L -27 0 L -28 12 Z"
        fill={look.hair} data-part="hair" />
      <path d="M -27 -30 Q -13 -43 0 -36 M 3 -39 Q 16 -40 25 -29" fill="none" stroke="#6e7378" strokeWidth="2" opacity={cinematic ? '.28' : '.55'} />
      <path d={`M -4 ${-14-brow*3} l 11 ${-2-brow*2} M 18 ${-17-brow*4} l 10 ${3+brow*3}`}
        fill="none" stroke={look.hair} strokeWidth="3.4" />
      {blink ? <path d="M -3 -1 l 11 1 M 18 -1 l 10 -1" fill="none" strokeWidth="2.4" /> : <g data-part="eyes">
        {[{x:3,y:-2,rx:7.4},{x:24,y:-3,rx:6.2}].map((e,i) => <g key={i}>
          {cinematic ? <path d={`M ${e.x-e.rx} ${e.y} Q ${e.x} ${e.y-eyeHeight*1.8} ${e.x+e.rx} ${e.y}
            Q ${e.x} ${e.y+eyeHeight*1.65} ${e.x-e.rx} ${e.y} Z`} fill="#b9c0b3" strokeWidth="1.5" />
            : <ellipse cx={e.x} cy={e.y} rx={e.rx} ry={eyeHeight} fill="#d8ddd3" strokeWidth="1.6" />}
          <ellipse cx={e.x+gx*.42} cy={e.y+gy*.5} rx={cinematic ? '2.5' : '3.2'} ry={cinematic ? '3' : '4.6'} fill="#465957" stroke="none" />
          <ellipse cx={e.x+gx*.42} cy={e.y+gy*.5} rx={cinematic ? '1.4' : '1.8'} ry={cinematic ? '2.5' : '3.3'} fill="#101923" stroke="none" />
          <circle cx={e.x-1+gx*.42} cy={e.y-2+gy*.5} r={cinematic ? '.6' : '1.1'} fill="#f6eddb" stroke="none" />
        </g>)}
        {lid > .01 ? <path d={`M -4 ${-2-eyeHeight} h 14 v ${eyeHeight*lid} H -4 Z M 18 ${-3-eyeHeight} h 12 v ${eyeHeight*lid} H 18 Z`}
          fill={look.skin} stroke="none" /> : null}
      </g>}
      <path d="M 13 -2 l -1 12 6 1" fill="none" stroke="#8e655b" strokeWidth="1.5" />
      <path d="M -2 12 l 7 1 M 22 12 l 6 -1" stroke="#936d66" strokeWidth="1.2" opacity=".65" />
      {mouth < -.65 ? cinematic ? <path d="M 8 25 Q 14 22 21 24 L 20 28 Q 14 26 9 29 Z"
        fill="#443335" strokeWidth="1.2" data-expression="held-breath" />
        : <ellipse cx="14" cy="26" rx="5" ry={3-mouth*4} fill="#4b3034" strokeWidth="1.6" data-expression="gasp" />
        : <path d={`M 7 26 Q 15 ${24+mouth*9} 24 25`} fill="none" stroke="#654a49" strokeWidth="2" />}
      {cinematic ? <g data-part="directional-face-shadow" stroke="none">
        <path d="M 12 -33 L 31 -17 L 32 -1 L 39 7 L 31 12 L 27 27 L 13 39 L 3 36 L 14 24 L 9 13 L 15 7 L 11 -5 Z"
          fill="#0b2028" opacity=".43" />
        <path d="M -7 9 l 11 2 M 19 9 l 10 -2 M 2 16 l 4 4" stroke="#655d55" strokeWidth="1" opacity=".7" />
      </g> : null}
      <path d="M -21 -9 Q -25 -19 -19 -25" fill="none" stroke="#a8c7ce" strokeWidth="2.5" opacity=".45" />
    </g>
  </g>;
};

export const CartoonHorrorHands: React.FC<{s: State; look: Look}> = ({s,look}) => <g data-part="hands"
  stroke="#292a30" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round">
  {[{p:s.left,e:s.le},{p:s.right,e:s.re}].map(({p,e},i) =>
    <g key={i} transform={`translate(${p}) rotate(${angle(e,p)})`}>
      <path d={look.treatment === 'cinematic'
        ? 'M -6 -3 L -7 5 Q -6 10 -4 13 Q -2 15 0 12 L -1 4 L 2 12 Q 4 13 5 10 L 4 1 L 8 3 Q 11 2 9 -1 L 5 -5 Z'
        : 'M -6 -3 Q -8 3 -6 9 Q -4 14 1 13 L 5 10 L 6 2 Q 11 0 9 -3 Q 8 -5 4 -2 L 4 -4 Z'} fill={look.skin} />
      <path d="M -4 4 l 6 1 M -3 8 l 5 1" fill="none" stroke="#a07969" strokeWidth="1" />
    </g>)}
</g>;
