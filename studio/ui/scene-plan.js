// Scene-plan review: canonical source fields are read-only; staging is an editable proposal.
// Approval covers scene planning only and never starts narration, rendering or publishing.
const node = (tag, text, className) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
};
async function api(path, body) {
  const response = await fetch(`/studio/api/${path}`, body === undefined ? undefined : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail || {};
    const blockers = Array.isArray(detail.blockers) && detail.blockers.length ? ` (${detail.blockers.length} blockers)` : '';
    throw new Error((detail.message || data.detail || 'Scene planning unavailable.') + blockers);
  }
  return data;
}
const text = (message, cls = 'field-help') => node('p', message, cls);
function select(label, values, selected, change, name) {
  const wrapper = node('label', label), input = node('select');
  input.setAttribute('aria-label', name);
  for (const v of values) {
    const option = node('option', v.label || v); option.value = v.value || v; option.selected = option.value === selected;
    input.append(option);
  }
  input.addEventListener('change', () => change(input.value)); wrapper.append(input); return wrapper;
}
function check(label, checked, change, name) {
  const wrapper = node('label', ` ${label}`), input = node('input'); input.type = 'checkbox'; input.checked = checked;
  input.setAttribute('aria-label', name);
  input.addEventListener('change', () => change(input.checked)); wrapper.prepend(input); return wrapper;
}
function button(label, action, id) {
  const b = node('button', label, 'secondary-button'); b.type = 'button'; if (id) b.id = id;
  b.addEventListener('click', async () => {b.disabled = true; try {await action();} finally {if (b.isConnected) b.disabled = false;}});
  return b;
}
const badge = status => node('span', status.replaceAll('_', ' '), `capability capability-${status}`);
const optionLabel = (vocab, key) => vocab && vocab[key] ? `${key} · ${vocab[key].status.replaceAll('_', ' ')}` : key;

let loadSequence = 0;
export async function loadScenePlan(id, panel, version) {
  const seq = ++loadSequence;
  panel.replaceChildren(text('Checking approved story, Visual Bible and scene-plan versions…'));
  try {
    const view = await api(`productions/${encodeURIComponent(id)}/scene-plan${version ? `/${version}` : ''}`);
    if (seq === loadSequence && panel.dataset.projectId === id) render(id, panel, view);
  } catch (error) {
    if (seq === loadSequence) {
      panel.replaceChildren(node('h2', 'Scene Plans'), text(error.message, 'error-panel'),
        button('Reload scene plans', () => loadScenePlan(id, panel), 'refresh-scene-plan'));
    }
  }
}

function render(id, panel, view) {
  const base = `productions/${encodeURIComponent(id)}/scene-plan`;
  panel.replaceChildren(node('h2', 'Scene Plans'), text('Short 9:16 and Long 16:9 from one approved story and one approved Visual Bible.'));
  panel.append(text('Story approval → Visual Bible approval → scene-plan approval. Narration (TTS), rendering, production and publishing are separate and not started here.'));
  const errors = node('p', '', 'error-panel'); errors.hidden = true; errors.setAttribute('role', 'alert'); panel.append(errors);
  const run = async action => {errors.hidden = true; try {return await action();} catch (error) {errors.textContent = error.message; errors.hidden = false;}};
  const top = node('div', undefined, 'scene-actions');
  const prepare = button('Prepare Scene Plans', () => run(async () => render(id, panel, await api(base, {}))), 'prepare-scene-plan');
  prepare.disabled = !view.visual_ready;
  top.append(prepare, button('Reload scene plans', () => loadScenePlan(id, panel), 'refresh-scene-plan'));
  panel.append(top);
  if (!view.visual_ready) panel.append(text(view.not_ready_reason || 'Approved inputs are required.', 'scene-not-ready'));
  if (view.state === 'missing') {
    if (view.visual_ready) panel.append(text('Inputs are approved. Prepare an immutable candidate; it stays unapproved until reviewed.'));
    return;
  }
  const plan = view.package, vocab = view.vocabulary;
  const hashBody = {package_sha256: view.package_sha256, manifest_sha256: view.manifest_sha256};
  panel.append(select('Scene-plan version', view.versions, view.version, v => loadScenePlan(id, panel, v), 'Scene plan version'));
  panel.append(text(`${view.version} · ${view.approval ? 'Approved for scene planning only; frozen' : 'Scene-plan approval pending'}`
    + `${view.is_current ? '' : ' · STALE: story, Visual Bible or a newer plan changed; prepare a new version'}`, 'scene-status'));
  const pins = plan.inputs;
  panel.append(node('pre', `Package SHA-256: ${view.package_sha256}\nManifest SHA-256: ${view.manifest_sha256}\n`
    + `Reviewed story ${pins.reviewed_story.version} · ${pins.reviewed_story.package_sha256}\n`
    + `Visual Bible ${pins.visual_bible.version} · ${pins.visual_bible.package_sha256}\n`
    + `Library ${pins.library.id}@${pins.library.version} · ${pins.library.sha256}`, 'scene-hashes'));
  const blockers = node('div', undefined, 'scene-blockers'); blockers.append(node('strong', `Scene-plan blockers: ${plan.blockers.length}`));
  const list = node('ul'); for (const b of plan.blockers) list.append(node('li', b)); blockers.append(list); panel.append(blockers);
  for (const w of plan.warnings) panel.append(text(`Warning: ${w}`, 'scene-warning'));
  const coverage = node('div', undefined, 'scene-coverage');
  for (const [fmt, cov] of Object.entries(plan.coverage.formats)) {
    const extra = cov.working_text ? ` · story text narrated ${cov.working_text.covered}/${cov.working_text.non_whitespace_characters}`
      : ` · sources within Long: ${cov.sources_within_long}`;
    coverage.append(text(`${fmt}: ${cov.allocated_beats}/${cov.reviewed_beats} beats allocated · ${cov.narrative_shots + cov.reaction_shots} shots · `
      + `${cov.scenes} scenes · order preserved ${cov.beat_order_preserved}${extra}`));
  }
  panel.append(coverage);
  const report = node('pre', '', 'scene-report'); report.id = 'scene-report'; report.hidden = true;
  panel.append(button('Show coverage report', () => run(async () => {
    report.textContent = (await api(`${base}/${view.version}/report`)).markdown; report.hidden = false;
  }), 'scene-report-button'), report);

  let choices = structuredClone(view.manifest.choices), dirty = false;
  const editable = view.is_current && !view.approval;
  const status = text('', 'scene-dirty-status');
  const markDirty = () => {dirty = true; approve.disabled = true; consent.checked = false; consent.disabled = true;
    status.textContent = 'Unsaved staging changes: save a new immutable version before approval.';};
  for (const [fmt, fp] of Object.entries(plan.formats)) {
    const section = node('section', undefined, 'scene-format'); section.dataset.format = fmt;
    section.append(node('h3', `${fmt === 'short' ? 'Short' : 'Long'} · ${fp.aspect_ratio} · ${fp.viewport.width}×${fp.viewport.height}`));
    const t = fp.timing;
    section.append(text(`Provisional estimate ${t.estimated_seconds.toFixed(1)} s (narration ${t.estimated_narration_seconds.toFixed(1)} s, silence `
      + `${t.planned_silence_seconds.toFixed(1)} s, action/framing ${t.action_and_framing_seconds.toFixed(1)} s). Pending measured narration (P3.5).`
      + (t.target ? ` Target ${t.target.min}–${t.target.max} s: estimate ${t.target.estimate_relation}; never enforced by cutting story content.` : '')));
    const fc = choices.formats[fmt];
    for (const chapter of fp.chapters) {
      section.append(node('h4', `${chapter.chapter_id} · ${chapter.title}`));
      for (const sceneId of chapter.scene_ids) {
        const scene = fp.scenes.find(s => s.scene_id === sceneId), sc = fc.scenes[sceneId];
        const card = node('article', undefined, 'scene-card'); card.dataset.scene = sceneId;
        card.append(node('h5', `${sceneId} · ${scene.location_id} · ${scene.environment ? `${scene.environment.id}@${scene.environment.revision}` : 'no environment'}`
          + ` · ${scene.lighting ? `${scene.lighting.id}@${scene.lighting.revision}` : 'no lighting'}`));
        card.append(select('Transition into scene', vocab.transitions, sc.transition, v => {sc.transition = v; unreviewScene(card, sc); markDirty();},
          `Transition ${sceneId}`));
        if (scene.canonical_time_markers.length) card.append(text(`Canonical time markers: ${scene.canonical_time_markers.join('; ')}`));
        const review = check('I reviewed this scene: its structured motion plans represent the reviewed narration and staging; descriptive text is not executable.',
          sc.reviewed, v => {sc.reviewed = v; markDirty();}, `Review scene ${sceneId}`);
        const unreview = () => {sc.reviewed = false; review.querySelector('input').checked = false; markDirty();};
        for (const shotId of scene.shot_ids) card.append(shotView(fp.shots.find(s => s.shot_id === shotId), fc.shots[shotId], vocab, unreview));
        card.append(review);
        section.append(card);
      }
    }
    panel.append(section);
  }
  const continuity = node('details', undefined, 'scene-continuity'); continuity.append(node('summary', 'Continuity and canonical uncertainty'));
  for (const [fmt, c] of Object.entries(plan.continuity.formats)) {
    continuity.append(text(`${fmt} final props: ${Object.entries(c.final_state.props).map(([k, v]) => `${k}=${v.state}`).join(', ')}`));
    for (const n of c.notes) continuity.append(text(n));
  }
  for (const rule of plan.continuity.canonical_rules) continuity.append(text(`${rule.id}: ${rule.rule}`));
  for (const q of plan.continuity.canonical_ambiguities) continuity.append(text(`${q.id}: ${q.question} · ${q.status}`));
  continuity.append(text(`Shared events checked: ${plan.continuity.shared_events_checked.join(', ')}; Short/Long mismatches: ${plan.continuity.format_mismatches.length}.`));
  panel.append(continuity);
  panel.append(check('I reviewed Short and Long story-to-shot coverage.', choices.coverage_reviewed,
    v => {choices.coverage_reviewed = v; markDirty();}, 'Review scene-plan coverage'));
  panel.append(check('I reviewed character, prop, lighting and revelation continuity across both formats.', choices.continuity_reviewed,
    v => {choices.continuity_reviewed = v; markDirty();}, 'Review scene-plan continuity'));
  panel.append(status);
  const save = button('Save new scene-plan version', () => run(async () => render(id, panel,
    await api(base, {base_version: view.version, ...hashBody, choices}))), 'save-scene-plan');
  save.disabled = !editable; panel.append(save);
  const consentWrap = check('I approve the exact displayed scene-plan package/manifest hashes for scene planning only. This does not start narration, rendering, production or publishing.',
    false, v => {approve.disabled = !v || dirty || !editable || Boolean(plan.blockers.length);}, 'Approve scene plan consent');
  consentWrap.className = 'scene-consent'; const consent = consentWrap.querySelector('input');
  consent.disabled = !editable || Boolean(plan.blockers.length);
  const approve = button('Approve Scene Plans', () => run(async () => render(id, panel,
    await api(`${base}/${view.version}/approve`, hashBody))), 'approve-scene-plan');
  approve.className = 'primary-button'; approve.disabled = true;
  panel.append(consentWrap, approve);
  if (!editable) panel.querySelectorAll('.scene-card select,.scene-card input,[aria-label="Review scene-plan coverage"],[aria-label="Review scene-plan continuity"]')
    .forEach(el => {el.disabled = true;});
}

function unreviewScene(card, scene) {
  scene.reviewed = false;
  const box = card.querySelector('[aria-label^="Review scene "]'); if (box) box.checked = false;
}

function shotView(shot, pick, vocab, unreview) {
  let editorial = null;
  const changed = () => {pick.editorial_acknowledged = false; if (editorial) editorial.querySelector('input').checked = false; unreview();};
  const row = node('details', undefined, 'shot-row'); row.dataset.shot = shot.shot_id;
  const summary = node('summary', `${shot.shot_id} · ${shot.kind.replace('_', ' ')} · ${shot.source.beat_id} · ${shot.timing.estimated_seconds.toFixed(2)} s `);
  summary.append(badge(shot.capability.status)); row.append(summary);
  const src = shot.source;
  if (shot.kind === 'narrative') {
    const quote = node('blockquote', src.narration.text, 'shot-narration');
    row.append(quote, text(`Source: ${src.narration.sources.map(s => `${s.segment_id}[${s.char_start}:${s.char_end}]`).join(', ')} · ${src.narration.attribution.replaceAll('_', ' ')}`));
  } else {
    row.append(text(`Silence hold after ${src.beat_id}: ${shot.timing.planned_silence_seconds} s; no narration.`));
  }
  row.append(text(`Events ${src.event_ids.join(', ')} · characters ${src.character_ids.join(', ') || 'none'} · objects ${src.object_ids.join(', ') || 'none'} · sounds ${src.sound_cue_ids.join(', ') || 'none'}`));
  for (const d of src.dialogue) row.append(text(`Dialogue ${d.id} (${d.speaker_id || 'unattributed'}): ${d.text}`));
  if (src.ambiguity_ids.length) row.append(text(`Preserve uncertainty: ${src.ambiguity_ids.join(', ')} · ${shot.staging.reveal.uncertainty || 'no extra guidance'}`));
  row.append(text(`Reviewed staging (descriptive, not executable): ${shot.descriptive_proposal.text}`, 'shot-descriptive'));
  const st = shot.staging;
  row.append(text(`Proposal · camera keys ${st.camera.keys.map(k => `[${k.join(', ')}]`).join(' → ')} · framed: ${st.camera.framed_subjects.join(', ') || 'set only'}`
    + (st.camera.framed_out.length ? ` · framed out: ${st.camera.framed_out.join(', ')}` : '')));
  row.append(select('Shot size', vocab.shot_sizes, pick.shot_size, v => {pick.shot_size = v; changed();}, `Shot size ${shot.shot_id}`));
  row.append(select('Camera move', Object.keys(vocab.camera_moves).map(k => ({value: k, label: optionLabel(vocab.camera_moves, k)})),
    pick.camera_move, v => {pick.camera_move = v; changed();}, `Camera ${shot.shot_id}`));
  row.append(select('Lighting state', Object.keys(vocab.lighting_states).map(k => ({value: k, label: optionLabel(vocab.lighting_states, k)})),
    pick.lighting_state, v => {pick.lighting_state = v; changed();}, `Lighting ${shot.shot_id}`));
  if (src.character_ids.some(c => st.presence?.character_id === c) || pick.presence === 'visible_partial' || shot.capability.items.some(i => i.requirement === 'presence'))
    row.append(select('Partial presence (identity never revealed)', vocab.presence, pick.presence, v => {pick.presence = v; changed();}, `Presence ${shot.shot_id}`));
  for (const c of st.cast) {
    const cp = pick.cast[c.character_id], box = node('div', undefined, 'shot-cast');
    box.append(node('strong', `${c.character_id} · ${c.asset.id}@${c.asset.revision} · ${c.entry} · ${c.start_mark || ''} → ${c.end_mark} · facing ${c.facing}${c.visible ? '' : ' · framed out'}`));
    box.append(select('Performance', Object.keys(vocab.performances).map(k => ({value: k, label: optionLabel(vocab.performances, k)})),
      cp.performance, v => {cp.performance = v; changed();}, `Performance ${shot.shot_id} ${c.character_id}`));
    box.append(select('Emotion (intent)', vocab.emotions, cp.emotion, v => {cp.emotion = v; changed();}, `Emotion ${shot.shot_id} ${c.character_id}`));
    if ('mark' in cp) {
      box.append(select('Blocking mark', Object.keys(shot.options?.marks || {}).length ? Object.keys(shot.options.marks) : [cp.mark], cp.mark,
        v => {cp.mark = v; changed();}, `Mark ${shot.shot_id} ${c.character_id}`));
      box.append(select('Entry', vocab.entries, cp.entry, v => {cp.entry = v; changed();}, `Entry ${shot.shot_id} ${c.character_id}`));
      if (c.end_mark !== cp.mark) box.append(text(`End mark ${c.end_mark} is set by the prop interaction; the selected mark is kept for other interactions.`));
    }
    row.append(box);
  }
  for (const p of st.props) {
    const interactions = vocab.prop_interactions[p.asset?.id] || {visible_in_set: {status: 'supported_direct'}};
    row.append(select(`Prop ${p.object_id} (${p.asset ? `${p.asset.id}@${p.asset.revision}` : 'unbound'} at ${p.anchor || 'no anchor'})`,
      Object.keys(interactions).map(k => ({value: k, label: optionLabel(interactions, k)})), pick.props[p.object_id],
      v => {pick.props[p.object_id] = v; changed();}, `Interaction ${shot.shot_id} ${p.object_id}`));
  }
  for (const [did, mode] of Object.entries(pick.dialogue)) {
    row.append(select(`Dialogue delivery ${did}`, Object.keys(vocab.dialogue_delivery).map(k => ({value: k, label: optionLabel(vocab.dialogue_delivery, k)})),
      mode, v => {pick.dialogue[did] = v; changed();}, `Dialogue ${shot.shot_id} ${did}`));
  }
  for (const cue of st.sound.cues) row.append(text(`Sound ${cue.id} (${cue.kind}, ${cue.placement}): ${cue.canonical_treatment}`));
  if (st.sound.silence_seconds) row.append(text(`Planned silence ${st.sound.silence_seconds} s (${st.sound.silence_role.replaceAll('_', ' ')}).`));
  const steps = shot.motion_plan.actors.flatMap(a => a.steps.map(s => `${a.character_id} ${s.preset} ${s.t0}–${s.t1} s`));
  row.append(text(`Executable motion plan (dry-run with P3.2A presets): ${steps.join('; ') || 'no actor motion'}`, 'shot-motion'));
  const items = node('ul', undefined, 'shot-capability');
  for (const i of shot.capability.items.filter(i => i.status !== 'supported_direct'))
    items.append(node('li', `${i.status.replaceAll('_', ' ')} · ${i.requirement} ${i.subject}${i.value ? ` (${i.value})` : ''}: ${i.basis}`));
  row.append(items);
  for (const n of shot.continuity.notes) row.append(text(`Continuity: ${n}`, 'shot-continuity'));
  for (const b of shot.blockers) row.append(text(`Blocker: ${b}`, 'shot-blocker'));
  editorial = check('Editorial acknowledgement: I accept this representation (e.g. voice-over or an action implied across a cut).',
    pick.editorial_acknowledged, v => {pick.editorial_acknowledged = v; unreview();}, `Editorial ${shot.shot_id}`);
  if (shot.capability.items.some(i => i.status === 'editorial_review') || pick.editorial_acknowledged) row.append(editorial);
  return row;
}
