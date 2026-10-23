// A separate visual-design review; content approval never starts production/publishing.
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
  if (!response.ok) throw new Error(data.detail?.message || data.detail || 'Visual review unavailable.');
  return data;
}
const text = (message, cls = 'field-help') => node('p', message, cls);
const ref = a => a ? {id: a.id, revision: a.revision} : null;
const value = a => a ? `${a.id}@${a.revision}` : '';
function updateOptions(wrapper, items, selected) {
  const input = wrapper.querySelector('select'); input.replaceChildren();
  for (const item of [{value: '', label: 'Unassigned — requires a decision'}, ...items]) {
    const option = node('option', item.label); option.value = item.value; option.selected = item.value === selected; input.append(option);
  }
}
function select(label, items, selected, change, name) {
  const wrapper = node('label', label), input = node('select');
  input.setAttribute('aria-label', name || label);
  for (const item of [{value: '', label: 'Unassigned — requires a decision'}, ...items]) {
    const option = node('option', item.label); option.value = item.value; option.selected = item.value === selected;
    input.append(option);
  }
  input.addEventListener('change', () => change(input.value)); wrapper.append(input); return wrapper;
}
function check(label, checked, change, name) {
  const wrapper = node('label', ` ${label}`), input = node('input'); input.type = 'checkbox'; input.checked = checked;
  input.setAttribute('aria-label', name || label);
  input.addEventListener('change', () => change(input.checked)); wrapper.prepend(input); return wrapper;
}
function button(label, action, id) {
  const b = node('button', label, 'secondary-button'); b.type = 'button'; if (id) b.id = id;
  b.addEventListener('click', async () => {b.disabled = true; try {await action();} finally {if (b.isConnected) b.disabled = false;}});
  return b;
}

let loadSequence = 0;
export async function loadVisualBible(id, panel, version) {
  const seq = ++loadSequence;
  panel.replaceChildren(text('Checking current canonical story and visual versions…'));
  try {
    const [view, catalog] = await Promise.all([api(`productions/${encodeURIComponent(id)}/visual-bible${version ? `/${version}` : ''}`), api('visual-assets')]);
    if (seq === loadSequence && panel.dataset.projectId === id) render(id, panel, view, catalog);
  } catch (error) {
    if (seq === loadSequence) panel.replaceChildren(node('h2', 'Story Visual Bible'), text(error.message, 'error-panel'));
  }
}

function render(id, panel, view, catalog) {
  const base = `productions/${encodeURIComponent(id)}/visual-bible`;
  panel.replaceChildren(node('h2', 'Story Visual Bible'), text('Cinematic 2D Cartoon Supernatural Horror'));
  panel.append(text('Story content approval → visual design approval → future scene planning. Production authorization is separate. Publishing remains disabled.'));
  const errors = node('p', '', 'error-panel'); errors.hidden = true; errors.setAttribute('role', 'alert'); panel.append(errors);
  const run = async action => {errors.hidden = true; try {return await action();} catch (error) {errors.textContent = error.message; errors.hidden = false;}};
  const prepare = button('Prepare Visual Bible', () => run(async () => render(id, panel, await api(base, {}), catalog)), 'prepare-visual-bible');
  prepare.disabled = !view.canonical_ready;
  panel.append(prepare);
  if (view.state === 'missing') {
    panel.append(text(view.canonical_ready ? 'Current story content approved. Prepare a visual candidate; designs remain proposals until reviewed.'
      : 'A current explicitly approved Reviewed Story Package is required. Drafts and historical approvals are not eligible.'));
    return;
  }
  const hashBody = {package_sha256: view.package_sha256, manifest_sha256: view.manifest_sha256};
  panel.append(select('Visual version', view.versions.map(v => ({value: v, label: v})), view.version,
    v => {if (v) loadVisualBible(id, panel, v);}, 'Visual Bible version'));
  panel.append(text(`${view.version} · ${view.approval ? 'Approved for scene planning only; frozen' : 'Visual design approval pending'}${view.is_current ? '' : ' · STALE: reload current approved story and prepare a new candidate'}`, 'visual-status'));
  panel.append(text(`Pinned reviewed canon ${view.package.canonical_input.version}. Eligibility against the current story is verified separately.`, 'field-help'));
  panel.append(node('pre', `Package SHA-256: ${view.package_sha256}\nManifest SHA-256: ${view.manifest_sha256}\nLibrary: ${catalog.library.id}@${catalog.library.version} · ${catalog.library.sha256}`, 'visual-hashes'));
  const blockers = node('div', undefined, 'visual-blockers'); blockers.append(node('strong', `Visual blockers: ${view.package.blockers.length}`));
  const list = node('ul'); for (const b of view.package.blockers) list.append(node('li', b)); blockers.append(list); panel.append(blockers);
  panel.append(text('Visual choices below are creative proposals, not canonical physical facts. New artwork, wardrobe changes and unrepresented locations/props require compatible assets; no fallback room is substituted.'));
  let choices = structuredClone(view.manifest.choices), dirty = false;
  const refreshers = [];
  const editable = view.is_current; // Changing a frozen design always creates a new version.
  const parsed = v => {const a = catalog.assets.find(x => `${x.id}@${x.revision}` === v); return a ? ref(a) : null;};
  const options = kind => catalog.assets.filter(a => a.kind === kind).map(a => ({value: value(a), label: `${a.id}@${a.revision} · ${a.summary}`}));
  const markDirty = () => {dirty = true; approve.disabled = true; consent.checked = false; consent.disabled = true; status.textContent = 'Unsaved visual changes: save a new immutable candidate before approval.';};
  const card = (heading, row) => {
    const c = node('article', undefined, 'visual-card'); c.append(node('h3', heading));
    c.append(text(`Canon: ${row.provenance.description}`));
    c.append(text(`Design basis: creative proposal · ${row.provenance.canonical_ref}`));
    panel.append(c); return c;
  };
  const invalidate = (c, config) => {config.reviewed = false; const input = c.querySelector('[data-visual-review]'); if (input) input.checked = false; markDirty();};
  const acknowledgement = (c, config, canonicalId) => {const label = check('I reviewed this visual proposal for this canonical role/location/prop.', config.reviewed,
    v => {config.reviewed = v; markDirty();}, `Review visual ${canonicalId}`); label.querySelector('input').dataset.visualReview = canonicalId; c.append(label);};
  for (const row of view.package.characters) {
    const c = card(`${row.canonical_id} · ${row.label}`, row), config = choices.characters[row.canonical_id];
    c.append(select('Representation', ['character', 'silhouette', 'unseen'].map(v => ({value: v, label: v})), config.representation,
      v => {config.representation = v; config.asset = null; c.querySelectorAll('select')[1].value = ''; invalidate(c, config);}, `Representation ${row.canonical_id}`));
    c.append(select('Character / silhouette asset', [...options('character'), ...options('silhouette')], value(config.asset),
      v => {config.asset = parsed(v); invalidate(c, config);}, `Asset ${row.canonical_id}`));
    if (row.asset) c.append(text(`${row.asset.id}@${row.asset.revision} · SHA-256 ${row.asset.sha256}`, 'visual-hash'));
    if (row.appearance?.design) {
      c.append(text(`Outfit: ${row.appearance.design.outfit}; footwear: ${row.appearance.design.footwear}. Same appearance in Short and Long.`));
      for (const [name, hex] of Object.entries(row.appearance.design.palette)) c.append(node('span', `${name} ${hex}`, 'swatch'));
    }
    acknowledgement(c, config, row.canonical_id);
  }
  for (const row of view.package.locations) {
    const c = card(`${row.canonical_id} · ${row.label}`, row), config = choices.locations[row.canonical_id];
    c.append(select('Environment', options('environment'), value(config.environment), v => {config.environment = parsed(v); config.flicker_lamp = null; invalidate(c, config); refreshers.forEach(fn => fn());}, `Environment ${row.canonical_id}`));
    c.append(select('Lighting', options('lighting'), value(config.lighting), v => {config.lighting = parsed(v); config.flicker_lamp = null; invalidate(c, config); refreshers.forEach(fn => fn());}, `Lighting ${row.canonical_id}`));
    const lamps = catalog.environments[config.environment?.id]?.anchors.lamps || [];
    const lampSelect = select('Flicker lamp (optional for flickering interior)', lamps.map(l => ({value: l.id, label: l.id})), config.flicker_lamp || '',
      v => {config.flicker_lamp = v || null; invalidate(c, config);}, `Flicker lamp ${row.canonical_id}`);
    c.append(lampSelect);
    refreshers.push(() => updateOptions(lampSelect, (catalog.environments[config.environment?.id]?.anchors.lamps || []).map(l => ({value: l.id, label: l.id})), config.flicker_lamp || ''));
    const figures = view.package.characters.filter(ch => ch.representation === 'silhouette' && ch.asset);
    const anchors = Object.keys(catalog.environments[config.environment?.id]?.anchors.presence_anchors || {});
    const presence = select('Optional canonical partial presence', figures.flatMap(ch => anchors.map(a => ({value: `${ch.canonical_id}:${a}`, label: `${ch.canonical_id} at ${a}`}))),
      config.presence ? `${config.presence.character_id}:${config.presence.anchor}` : '', v => {const [character_id, anchor] = v.split(':'); config.presence = v ? {character_id, anchor} : null; invalidate(c, config);}, `Presence ${row.canonical_id}`);
    c.append(presence);
    if (row.anchors) c.append(text(`Floor ${row.anchors.floor_y}; walk range ${row.anchors.walk_range.join('–')}; ${row.anchors.doors.length} doors, ${row.anchors.windows.length} windows. Geometry/anchors remain pinned.`));
    for (const a of [row.environment, row.lighting]) if (a) c.append(text(`${a.id}@${a.revision} · SHA-256 ${a.sha256}`, 'visual-hash'));
    acknowledgement(c, config, row.canonical_id);
  }
  for (const row of view.package.props) {
    const c = card(`${row.canonical_id} · ${row.label}`, row), config = choices.props[row.canonical_id];
    c.append(text(`Bound location: ${row.location_id || 'unassigned'}; persistent: ${row.persistent}. Canonical location constraints are verified on save.`));
    c.append(select('Prop location', view.package.locations.map(l => ({value: l.canonical_id, label: `${l.canonical_id} · ${l.label}`})), config.location_id || '',
      v => {config.location_id = v || null; config.anchor = null; invalidate(c, config); refreshers.forEach(fn => fn());}, `Prop location ${row.canonical_id}`));
    c.append(select('Prop asset', options('prop'), value(config.asset), v => {config.asset = parsed(v); config.anchor = null; invalidate(c, config); refreshers.forEach(fn => fn());}, `Prop ${row.canonical_id}`));
    const env = choices.locations[config.location_id]?.environment?.id;
    const anchors = catalog.environments[env]?.prop_anchors[config.asset?.id] || {};
    const anchorSelect = select('Interaction anchor', Object.keys(anchors).map(a => ({value: a, label: `${a} (${anchors[a].join(', ')})`})), config.anchor || '',
      v => {config.anchor = v || null; invalidate(c, config);}, `Anchor ${row.canonical_id}`);
    c.append(anchorSelect);
    refreshers.push(() => {const env = choices.locations[config.location_id]?.environment?.id;
      const available = catalog.environments[env]?.prop_anchors[config.asset?.id] || {};
      updateOptions(anchorSelect, Object.keys(available).map(a => ({value: a, label: `${a} (${available[a].join(', ')})`})), config.anchor || '');});
    acknowledgement(c, config, row.canonical_id);
  }
  const continuity = node('details'); continuity.append(node('summary', 'Canonical continuity and intentional uncertainty'));
  continuity.append(text(view.package.continuity.uncertainty_policy));
  for (const rule of view.package.continuity.canonical_rules) continuity.append(text(`${rule.id}: ${rule.rule}`));
  for (const q of view.package.continuity.canonical_ambiguities) continuity.append(text(`${q.id}: ${q.question} · ${q.status} · ${q.production_guidance}`));
  continuity.append(text('Short and Long share the exact character appearance and environment hashes. Shot framing/pacing may vary; identity and persistent design may not.'));
  panel.append(continuity, check('I reviewed shared Short/Long identity, clothing, props and canonical uncertainty.', choices.continuity_reviewed,
    v => {choices.continuity_reviewed = v; markDirty();}, 'Review visual continuity'));
  const status = text('', 'visual-dirty-status'); panel.append(status);
  const actions = node('div', undefined, 'visual-actions');
  const save = button('Save new visual version', () => run(async () => render(id, panel, await api(base,
    {base_version: view.version, ...hashBody, choices}), catalog)), 'save-visual-bible');
  const preview = button('Preview reference visuals', () => run(async () => {
    if (dirty) throw new Error('Save the new visual version before previewing.');
    status.textContent = 'Rendering local reference PNGs with the existing StoryVideo/IK/Remotion pipeline…';
    const report = await api(`${base}/${view.version}/references`, hashBody);
    const grid = node('div', undefined, 'visual-preview-grid');
    for (const r of report.references) {const figure = node('figure'), img = node('img'); img.alt = r.label;
      img.src = `/studio/api/${base}/references/${report.key}/${r.file}`; figure.append(img, node('figcaption', r.label)); grid.append(figure);}
    previews.replaceChildren(grid); status.textContent = 'Reference stills only. No story video or audio was generated.';
  }), 'preview-visual-bible');
  save.disabled = preview.disabled = !editable; actions.append(save, preview); panel.append(actions);
  const consentWrap = check('I approve the exact displayed visual package/manifest hashes for future scene planning only. This does not authorize production, narration or publishing.', false,
    v => {approve.disabled = !v || dirty || !editable || Boolean(view.package.blockers.length) || Boolean(view.approval);}, 'Approve visual design consent');
  consentWrap.className = 'visual-consent'; const consent = consentWrap.querySelector('input');
  consent.disabled = !editable || Boolean(view.package.blockers.length) || Boolean(view.approval);
  const approve = button('Approve Visual Bible', () => run(async () => render(id, panel,
    await api(`${base}/${view.version}/approve`, hashBody), catalog)), 'approve-visual-bible');
  approve.className = 'primary-button'; approve.disabled = true;
  panel.append(consentWrap, approve);
  const previews = node('div'); previews.id = 'visual-reference-previews'; panel.append(previews);
  panel.append(text(`Known limitations: ${catalog.limitations.join('; ')}. Structural approval does not certify cinematic or listening quality.`));
  if (!editable) panel.querySelectorAll('.visual-card input,.visual-card select,[aria-label="Review visual continuity"]').forEach(el => {el.disabled = true;});
}
