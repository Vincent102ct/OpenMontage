// Scene approval, measured narration and explicit synthetic render consent are separate.
const el = (tag, text) => {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n;};
async function api(id, suffix = '', body) {
  const r = await fetch(`/studio/api/productions/${encodeURIComponent(id)}/story-video${suffix}`, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail?.message || String(data.detail || 'Production unavailable'));
  return data;
}
function button(label, action, id) {
  const b = el('button', label); b.type = 'button'; b.id = id; b.className = 'secondary-button';
  b.addEventListener('click', async () => {b.disabled = true; try {await action();} finally {b.disabled = false;}}); return b;
}
export async function loadStoryVideo(id, panel) {
  const current = () => panel.dataset.projectId === id && panel.isConnected;
  panel.replaceChildren(el('h2', 'Local synthetic story video'));
  const message = el('p', 'Checking current approvals…'); panel.append(message);
  try {
    const state = await api(id);
    if (!current()) return;
    if (state.production_started) {
      document.querySelectorAll('[data-production-status]').forEach(n => {
        if (n instanceof HTMLElement && n.dataset.productionStatus === id) n.textContent = 'Local synthetic production requested';
      });
      panel.parentElement.querySelectorAll('.status-chip').forEach(n => {
        if (n.textContent === 'Production not started') n.textContent = 'Preproduction review';
      });
    }
    message.textContent = 'Synthetic fixtures only. Publishing disabled. Artistic and audio acceptance pending.';
    if (!state.eligible) {panel.append(el('p', state.blockers.map(b => b.message).join(' '))); return;}
    const errors = el('p'); errors.className = 'error-panel'; errors.hidden = true; panel.append(errors);
    const guard = action => async () => {errors.hidden = true; try {await action();} catch (e) {errors.textContent = e.message; errors.hidden = false;}};
    const jobs = el('div'); jobs.className = 'story-video-jobs';
    const running = state.jobs.some(j => ['queued', 'running'].includes(j.state));
    const latest = [...state.jobs].reverse().find(j => j.kind === 'narration' && j.state === 'complete' && j.is_current);
    const controls = el('div'); controls.className = 'story-video-controls'; panel.append(controls, jobs);
    const staging = await api(id, '/staging');
    if (!current()) return;
    const review = el('section'); review.append(el('h3', 'Visual staging review · separate approval'));
    const stagingReady = staging.ready_for_render && latest && staging.manifest.narration.manifest_sha256 === latest.result.manifest_sha256;
    review.append(el('p', staging.status === 'not_prepared'
      ? 'Render blocked: prepare and explicitly review per-lamp and seated staging first.'
      : `${staging.version} · ${staging.status}. Original Scene Plan, Visual Bible and measured WAVs remain frozen.`));
    if (staging.package) {
      const checked = new Set();
      const consentLabel = el('label', ' I approve this exact visual execution extension after reviewing every affected shot and cut.');
      const approveConsent = el('input'); approveConsent.type = 'checkbox'; approveConsent.id = 'staging-approve-consent'; consentLabel.prepend(approveConsent);
      const approve = button('Approve visual staging version', guard(async () => {
        await api(id, `/staging/${staging.version}/approve`, {package_sha256: staging.reference.package_sha256,
          manifest_sha256: staging.reference.manifest_sha256, reviewed_items: [...checked], consent: approveConsent.checked});
        await loadStoryVideo(id, panel);
      }), 'approve-visual-staging'); approve.disabled = true;
      const update = () => {approve.disabled = !!staging.approval || !approveConsent.checked || checked.size !== staging.review_items.length;};
      for (const item of staging.review_items) {
        const d = el('details'), title = el('summary', item); d.dataset.stagingItem = item; d.append(title);
        const row = staging.changes.find(r => r.item === item);
        const proposal = row ? {before: row.before, before_motion: row.before_motion,
          before_lamp_emissions: row.before_lamp_emissions, proposed: row.proposed}
          : staging.package.cut_relocations[item.split('/')[0]].find(r => item.includes(`/cut/${r.from}/${r.to}/${r.character_id}`));
        d.append(el('pre', JSON.stringify(proposal, null, 2)));
        const label = el('label', ' Reviewed source evidence and before/after state '), input = el('input'); input.type = 'checkbox';
        input.setAttribute('aria-label', `Review visual staging ${item}`);
        input.addEventListener('change', () => {if (input.checked) checked.add(item); else checked.delete(item); update();});
        label.prepend(input); d.append(label); review.append(d);
      }
      approveConsent.addEventListener('change', update); review.append(consentLabel, approve);
    }
    if (latest) {
      const editor = el('textarea'); editor.rows = 12; editor.setAttribute('aria-label', 'Visual staging proposal JSON');
      editor.value = JSON.stringify(staging.package ? {overrides: staging.package.overrides, cut_relocations: staging.package.cut_relocations}
        : {overrides: {short: {}, long: {}}, cut_relocations: {short: [], long: []}}, null, 2);
      const edit = el('details'); edit.append(el('summary', 'Prepare a new immutable staging candidate'),
        el('p', 'Use verified lamp IDs, chair anchors and exact source quotes. Saving creates a candidate and grants no approval.'), editor,
        button('Save new visual staging candidate', guard(async () => {
          const proposal = JSON.parse(editor.value);
          await api(id, '/staging', {plan: state.plan, narration: {job_id: latest.job_id, manifest_sha256: latest.result.manifest_sha256},
            base_version: staging.version || null, overrides: proposal.overrides, cut_relocations: proposal.cut_relocations});
          await loadStoryVideo(id, panel);
        }), 'save-visual-staging'));
      review.append(edit);
    }
    controls.append(review);
    controls.append(button('Check offline narration readiness', guard(async () => {
      const ready = await api(id, '/readiness');
      if (!current()) return;
      const info = el('p', ready.blockers.map(b => b.message).join(' ') || `Matching installed voices: ${ready.language}`);
      controls.append(info);
      if (!ready.ready) return;
      const label = el('label', 'Offline voice '), select = el('select'); select.id = 'story-video-voice';
      ready.voices.forEach((v, i) => {const o = el('option', `${v.voice || v.provider} · ${v.language}`); o.value = String(i); select.append(o);});
      label.append(select); controls.append(label);
      const prepare = button('Prepare measured narration', guard(async () => {
        const v = ready.voices[Number(select.value)];
        await api(id, '/jobs/narration', {plan: ready.plan, voice: {provider: v.provider, voice: v.voice, rate: null}});
        await loadStoryVideo(id, panel);
      }), 'prepare-story-narration'); prepare.disabled = running; controls.append(prepare);
    }), 'check-story-narration'));
    if (latest) {
      controls.append(el('p', `Measured narration ready: Short ${latest.result.formats.short.duration_seconds.toFixed(2)}s; Long ${latest.result.formats.long.duration_seconds.toFixed(2)}s.`));
      const label = el('label', ' I authorize a complete local draft render of this synthetic fixture.'), consent = el('input');
      consent.type = 'checkbox'; consent.id = 'story-video-consent'; label.prepend(consent); controls.append(label);
      const render = button('Render complete Short and Long drafts', guard(async () => {
        await api(id, '/jobs/render', {plan: state.plan, narration_job: latest.job_id, narration_sha256: latest.result.manifest_sha256,
          staging: staging.reference, render_consent: consent.checked, scale: .5}); await loadStoryVideo(id, panel);
      }), 'render-story-video'); render.disabled = true;
      consent.addEventListener('change', () => {render.disabled = !consent.checked || running || !stagingReady;}); controls.append(render);
      if (!stagingReady) controls.append(el('p', 'Complete rendering is blocked until the current visual staging and exact narration are separately approved.'));
    }
    for (const j of [...state.jobs].reverse()) {
      const row = el('article'); row.append(el('p', `${j.kind} · ${j.state}${j.is_current ? '' : ' · stale'} · ${j.message}`));
      if (j.error) row.append(el('p', `${j.error.code}: ${j.error.message}`));
      if (j.kind === 'render' && j.state === 'complete' && j.is_current) {
        for (const fmt of ['short', 'long']) {
          const base = `/studio/api/productions/${encodeURIComponent(id)}/story-video/jobs/${j.job_id}/${fmt}/`;
          row.append(el('h3', `${fmt} · draft · ${j.result.formats[fmt].qa.decoded_frames} decoded frames`));
          const video = el('video'); video.controls = true; video.preload = 'metadata'; video.src = base + 'video'; row.append(video);
          for (const [kind, label] of [['qa', 'Technical QA'], ['contact', 'All-shot contact sheet'], ['subtitles', 'UTF-8 subtitles']]) {
            const a = el('a', label); a.href = base + kind; a.target = '_blank'; a.rel = 'noopener'; row.append(a);
          }
        }
      }
      jobs.append(row);
    }
    const monitor = el('a', 'Backlot monitor'); monitor.href = `/p/${encodeURIComponent(id)}`; controls.append(monitor);
    if (running) setTimeout(() => {if (current()) loadStoryVideo(id, panel);}, 3000);
  } catch (e) {if (current()) message.textContent = e.message;}
}
