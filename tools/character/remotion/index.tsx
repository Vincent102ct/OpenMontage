import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {Scene} from './Scene';
import {EpisodeScene} from './Episode';
import {StoryVideo, StoryVideoProps} from './StoryVideo';
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
  <Composition id="StoryVideo" component={StoryVideo} fps={30}
    width={1280} height={720} durationInFrames={450} defaultProps={{} as StoryVideoProps}
    calculateMetadata={({props}) => ({durationInFrames: Math.ceil(props.duration_seconds*props.fps),
      fps:props.fps, width:1280, height:720})} />
</>;
registerRoot(Root);
