import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {Scene} from './Scene';
import {EpisodeScene} from './Episode';
import {DirectedStoryVideo, CinematicHorrorProps} from './CinematicHorror';
import type {Motion} from './motion';
import type {Episode} from './shots';

const Root = () => <>
  <Composition id="StoryAction" component={Scene} fps={30}
    width={1280} height={720} durationInFrames={450} defaultProps={{} as Motion}
    calculateMetadata={({props}) => ({durationInFrames: Math.ceil(props.duration_seconds*props.fps),
      fps:props.fps, width:1280, height:720})} />
  <Composition id="StoryEpisode" component={EpisodeScene} fps={30}
    width={1280} height={720} durationInFrames={450} defaultProps={{} as Episode}
    calculateMetadata={({props}) => ({durationInFrames: Math.ceil(props.duration_seconds*props.fps),
      fps:props.fps, width:1280, height:720})} />
  <Composition id="StoryVideo" component={DirectedStoryVideo} fps={30}
    width={1280} height={720} durationInFrames={450} defaultProps={{} as CinematicHorrorProps}
    calculateMetadata={({props}) => ({durationInFrames: Math.ceil(props.duration_seconds*props.fps),
      fps:props.fps, width:props.viewport?.width ?? 1280, height:props.viewport?.height ?? 720})} />
</>;
registerRoot(Root);
