// Pure, seekable multi-shot evaluation built on the single-shot rig mechanics.
// One persistent world (apartment, actor, cup, chair, fridge); shots only choose
// time, camera and light. Story content and choreography stay in data.
import {ActorMotion, Key, Point, sample, stateAt} from './motion';

export type Layer = {svg: string; x: number};
export type Fridge = {hinge_x: number; width: number; top: number; bottom: number;
  handle_inset: number; handle_y: number};
export type Chair = {x: number; y: number};
export type Shot = {
  id: string; start_seconds: number; end_seconds: number;
  // 'insert' shows a full-frame close-up illustration instead of the world.
  view: 'world' | 'insert'; insert_svg?: string;
  camera: Key[];            // [t, cx, cy, zoom] in shot-local seconds
  light: Key[];             // [t, day 0..1, black fade 0..1]
  motion: ActorMotion;      // actor + cup, in motion time = local + motion_offset
  motion_offset: number;
  actor_visible: boolean;
  chair_b: Key[];           // [t, dx, rotation] from the tucked position
  fridge_door: Key[];       // [t, opening angle in degrees]
  stain_until: number | null; // motion time when the dried ring is washed off
  drip_from: number | null; // motion time when the washed cup starts dripping
};
export type Episode = {
  duration_seconds: number; fps: number;
  world: {x0: number; width: number; layers: Layer[]; items_over: Layer[];
    // SVG path of scenery in front of the cup (near basin wall); clips only the cup.
    cup_occluder: string; foreground: Layer[]; day_window: Layer; fridge: Fridge; chair_a: Chair; chair_b: Chair};
  look: {shirt: string; skin: string; hair: string};
  shots: Shot[];
  narration: {id: string; path: string; text: string; start_seconds: number; end_seconds: number}[];
  sfx: {id: string; path: string; start_seconds: number; duration_seconds: number; volume: number}[];
};

export function shotAt(ep: Episode, t: number): Shot {
  const shots = ep.shots;
  for (const shot of shots) if (t < shot.end_seconds) return shot;
  return shots[shots.length - 1];
}

export function fridgeHandle(f: Fridge, angle: number): Point {
  return [f.hinge_x + (f.width - f.handle_inset) * Math.cos(angle * Math.PI / 180), f.handle_y];
}

export function episodeAt(ep: Episode, t: number) {
  const shot = shotAt(ep, t);
  const local = Math.min(t, shot.end_seconds) - shot.start_seconds;
  const mt = local + shot.motion_offset;
  const door = sample(shot.fridge_door, local)[0];
  const doorAt = (lt: number) => sample(shot.fridge_door, lt - shot.motion_offset)[0];
  // Attachment targets are evaluated on the same shot-local clock as the door.
  const handles = (item: string, at: number): Point => {
    if (item !== 'fridge_door') throw new Error(`Unknown attachment item ${item}`);
    return fridgeHandle(ep.world.fridge, doorAt(at));
  };
  const actor = stateAt(shot.motion, mt, handles);
  const [cx, cy, zoom] = sample(shot.camera, local);
  const [day, dark] = sample(shot.light, local);
  const [chairDx, chairRot] = sample(shot.chair_b, local);
  const drip = shot.drip_from == null ? -1 : mt - shot.drip_from;
  return {shot, local, mt, actor, camera: [cx, cy, zoom] as [number, number, number],
    day, dark, door, chair: [chairDx, chairRot], drip};
}
