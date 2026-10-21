import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Motion, stateAt} from './motion';
import {ActorBody, ActorHands} from './Actor';

export const Scene: React.FC<Motion> = (m) => {
  const frame = useCurrentFrame(), {fps} = useVideoConfig(), t = frame / fps;
  const s = stateAt(m, t);
  const caption = m.narration.find(n => t >= n.start_seconds && t < n.end_seconds);
  return <AbsoluteFill style={{background: '#172630'}}>
    <div style={{position: 'absolute', inset: 0}} dangerouslySetInnerHTML={{__html: m.background_svg}} />
    <svg width="1280" height="720" viewBox="0 0 1280 720" style={{position: 'absolute', inset: 0}}>
      <g stroke="#17242b" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round">
        {s.water ? <g stroke="#a8e3e5" fill="none" opacity="0.8">
          <path d="M 516 420 L 516 487" strokeWidth="5" />
          {[0, 1, 2, 3, 4].map(i => <path key={i} strokeWidth="2"
            d={`M ${503+i*6} ${480+((t*55+i*9)%13)} l ${i-2} 6`} />)}
        </g> : null}
        <ActorBody s={s} look={m.actor} t={t} />
        {/* One prop node for the whole shot; no duplicate cup at release. */}
        <g id={m.prop.id} transform={`translate(${s.cup[0]} ${s.cup[1]}) rotate(${s.cup[2]})`}>
          <path d="M 15 -10 C 40 -17 40 18 15 12" fill="none" stroke="#eeeade" strokeWidth="8" />
          <path d="M 15 -10 C 40 -17 40 18 15 12" fill="none" strokeWidth="2" />
          <path d="M -17 -19 L 17 -19 L 14 17 Q 0 23 -14 17 Z" fill="#f2efe5" />
          <ellipse cx="0" cy="-19" rx="17" ry="4" fill="#acb2ae" />
          <path d="M -10 -11 L -8 12" stroke="#fffdf4" strokeWidth="3" />
        </g>
        <ActorHands s={s} look={m.actor} />
      </g>
    </svg>
    <div style={{position:'absolute', inset:0, pointerEvents:'none'}} dangerouslySetInnerHTML={{__html:m.foreground_svg}} />
    {caption ? <div style={{position:'absolute', bottom:24, left:100, right:100, textAlign:'center',
      fontFamily:'Arial, sans-serif', fontSize:29, fontWeight:500, color:'#f8f6ed'}}>
      <span style={{background:'rgba(9,16,22,.88)', padding:'9px 20px', borderRadius:5}}>{caption.text}</span>
    </div> : null}
    {m.narration.map((n,i) => <Sequence key={i} from={Math.round(n.start_seconds*fps)}
      durationInFrames={Math.ceil((n.end_seconds-n.start_seconds)*fps)} layout="none">
      <Audio src={staticFile(n.path)} />
    </Sequence>)}
  </AbsoluteFill>;
};
