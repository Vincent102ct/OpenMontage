import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {StoryVideo, StoryVideoProps} from './StoryVideo';
import {Key, sample} from './motion';

export type CinematicHorrorProps = StoryVideoProps & {
  // Optional seekable environmental tracks; absent for every existing package.
  horror?: {presence: Key[]; spill: Key[]};
};

// Add light and depth over the existing world without changing its actor/motion layers.
export const DirectedStoryVideo: React.FC<CinematicHorrorProps> = p => {
  const frame=useCurrentFrame(), {fps,width,height}=useVideoConfig(), t=frame/fps;
  const shot=p.shots.find(s=>t<s.end_seconds) ?? p.shots[p.shots.length-1];
  const loc=shot?.location ? p.locations[shot.location] : null;
  if(!p.horror || !loc || p.character_skin!=='cartoon_horror') return <StoryVideo {...p} />;
  const local=Math.min(t,shot.end_seconds)-shot.start_seconds;
  const [cx,cy,z]=sample(shot.camera,local), scale=z*height/720;
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
