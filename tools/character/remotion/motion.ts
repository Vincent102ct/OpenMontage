// Pure, seekable skeletal mechanics. Artwork, identity and choreography are data.
export type Point = [number, number];
export type Key = number[];
export type Attachment = {hand: 'left' | 'right'; item: string; from: number; to: number};
export type Motion = {
  duration_seconds: number; fps: number; background_svg: string; foreground_svg: string;
  actor: {id: string; root: Key[]; left_hand: Key[]; right_hand: Key[];
    left_foot: Key[]; right_foot: Key[]; shirt: string; skin: string; hair: string;
    // Optional: -1 mirrors the rig to face left; face keys are [t, brow, gazeX, gazeY, mouth, lid, tilt].
    facing?: number; face?: Key[];
    // Opt-in upper-body acting: [t, shoulder dx/dy, head dx/dy] in rig units.
    posture?: Key[]};
  // Null grip/release means the prop is never held in this motion.
  prop: {id: string; track: Key[]; grip_seconds: number | null; release_seconds: number | null; handle_offset: Point};
  wash_window: [number, number] | null;
  attachments?: Attachment[];
  narration: {path: string; text: string; start_seconds: number; end_seconds: number}[];
};
export type ActorMotion = Pick<Motion, 'actor' | 'prop' | 'wash_window' | 'attachments'>;
// World-space handle position of a non-actor item (e.g. a door handle) at time t.
export type Handles = (item: string, t: number) => Point;
export const NEUTRAL_FACE = [0, 0, 0, 0, 0, 0];

export function sample(keys: Key[], t: number): number[] {
  if (t <= keys[0][0]) return keys[0].slice(1);
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i][0]) {
      const a = keys[i - 1], b = keys[i];
      let u = (t - a[0]) / (b[0] - a[0]);
      u = u * u * (3 - 2 * u);
      return a.slice(1).map((v, j) => v + (b[j + 1] - v) * u);
    }
  }
  return keys[keys.length - 1].slice(1);
}

export function joint(a: Point, b: Point, upper: number, lower: number, bend: number): Point {
  const dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy);
  if (d > upper + lower + 0.001 || d < Math.abs(upper - lower) + 0.001) {
    throw new Error(`Unreachable limb: ${d.toFixed(3)} for ${upper}+${lower}`);
  }
  const along = (upper * upper - lower * lower + d * d) / (2 * d);
  const side = Math.sqrt(Math.max(0, upper * upper - along * along)) * bend;
  return [a[0] + dx * along / d - dy * side / d,
    a[1] + dy * along / d + dx * side / d];
}

// Limb points are returned in the rig's local (right-facing) frame. With
// facing -1 the renderer mirrors that frame about root x; toWorld maps back.
export function toWorld(s: {root: Point; facing: number}, p: Point): Point {
  return s.facing > 0 ? p : [2 * s.root[0] - p[0], p[1]];
}

export function stateAt(m: ActorMotion, t: number, handles?: Handles) {
  const root = sample(m.actor.root, t) as Point;
  const facing = (m.actor.facing ?? 1) < 0 ? -1 : 1;
  const local = (p: Point): Point => facing > 0 ? p : [2 * root[0] - p[0], p[1]];
  const posture = m.actor.posture ? sample(m.actor.posture, t) : [5, -99, 10, -160];
  const shoulder: Point = [root[0] + posture[0], root[1] + posture[1]];
  const hip: Point = [root[0], root[1]];
  const cup = sample(m.prop.track, t);
  const rad = cup[2] * Math.PI / 180, [ox, oy] = m.prop.handle_offset;
  const grip: Point = [cup[0] + ox * Math.cos(rad) - oy * Math.sin(rad),
    cup[1] + ox * Math.sin(rad) + oy * Math.cos(rad)];
  const {grip_seconds: g, release_seconds: r} = m.prop;
  const held = g != null && r != null && t >= g && t <= r;
  let right = held ? grip : sample(m.actor.right_hand, t) as Point;
  let left = sample(m.actor.left_hand, t) as Point;
  for (const a of m.attachments ?? []) {
    if (!handles || t < a.from || t > a.to) continue;
    if (a.hand === 'right') right = handles(a.item, t); else left = handles(a.item, t);
  }
  right = local(right); left = local(left);
  const lf = local(sample(m.actor.left_foot, t) as Point);
  const rf = local(sample(m.actor.right_foot, t) as Point);
  const face = m.actor.face ? sample(m.actor.face, t) : NEUTRAL_FACE;
  return {root, shoulder, hip, cup, grip, held, left, right, lf, rf, facing, face,
    head: [root[0] + posture[2], root[1] + posture[3]] as Point,
    le: joint(shoulder, left, 65, 68, 1), re: joint(shoulder, right, 65, 68, 1),
    lk: joint(hip, lf, 57, 58, -1), rk: joint(hip, rf, 57, 58, -1),
    owner: g == null || t < g ? 'counter' : r == null || t <= r ? m.actor.id : 'rack',
    water: m.wash_window != null && t >= m.wash_window[0] && t < m.wash_window[1]};
}
