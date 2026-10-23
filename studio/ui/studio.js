import {loadVisualBible} from './visual-bible.js';

const $ = (id) => document.getElementById(id);
const form = $("production-form");
const content = $("content");
let canonicalPackages = [];
let uploadedText = null;
let sourceFilename = null;
let saving = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function api(path, options) {
  const response = await fetch(`/studio/api/${path}`, options);
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail;
    const error = new Error(Array.isArray(detail)
      ? detail.map((e) => `${e.loc?.join(".") || "Input"}: ${e.msg}`).join("\n")
      : detail?.message || detail || "Could not reach Studio. Please try again.");
    error.code = detail?.code;
    throw error;
  }
  return result;
}

function mode() { return new FormData(form).get("input_mode"); }
function showError(message) {
  $("form-error").textContent = message;
  $("form-error").hidden = false;
  $("form-error").focus();
}
function clearError() { $("form-error").hidden = true; }
function countCharacters() {
  $("character-count").textContent = `${Array.from(content.value).length.toLocaleString("en-US")} / 200,000`;
}
function switchMode() {
  const selected = mode();
  $("text-input-group").hidden = selected === "canonical";
  $("canonical-input-group").hidden = selected !== "canonical";
  $("content-label").textContent = selected === "topic" ? "Topic to research" : "Your story";
  content.placeholder = selected === "topic" ? "Enter a topic or question to research…" : "Paste your story here (Vietnamese supported)…";
  $("input-help").textContent = {
    topic: "A topic is input awaiting research. No Master Story or verified facts exist yet.",
    story: "The full story is saved for review; it is not treated as a researched Master Story.",
    canonical: "Only the selected package reference and hash are saved. Its content is not changed, and facts or publication rights are not approved.",
  }[selected];
  clearError();
}

async function loadPackages() {
  try {
    const data = await api("packages");
    canonicalPackages = data.packages;
    $("canonical-package").replaceChildren(element("option", "Select a canonical package"));
    $("canonical-package").firstChild.value = "";
    for (const p of canonicalPackages) {
      const option = element("option", `${p.title} · ${p.reference.package_id}@${p.reference.package_version}`);
      option.value = p.id;
      $("canonical-package").append(option);
    }
    $("canonical-package").disabled = !canonicalPackages.length;
    $("canonical-state").textContent = data.warnings.length
      ? data.warnings.join(" ")
      : canonicalPackages.length ? `${canonicalPackages.length} package(s) available. Human review is still required.`
        : "No approved canonical packages yet. You can still use Topic or Full story.";
  } catch {
    canonicalPackages = [];
    $("canonical-package").replaceChildren(element("option", "Could not load catalog"));
    $("canonical-package").disabled = true;
    $("canonical-state").textContent = "Could not load canonical packages. Reload the page to retry.";
  }
}

form.addEventListener("change", (event) => {
  if (event.target.name === "input_mode") switchMode();
});
content.addEventListener("input", () => {
  uploadedText = null;
  sourceFilename = null;
  $("upload-name").textContent = "The original text is saved unchanged.";
  countCharacters();
});
$("select-both").addEventListener("click", () => {
  $("format-short").checked = true;
  $("format-long").checked = true;
});
$("markdown-file").addEventListener("change", async () => {
  const file = $("markdown-file").files[0];
  if (!file) return;
  clearError();
  try {
    if (!/\.(md|markdown)$/i.test(file.name)) throw new Error("Choose a .md or .markdown file.");
    if (file.size > 1000000) throw new Error("The Markdown file exceeds the 1 MB limit.");
    const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
    if (Array.from(text).length > 200000) throw new Error("The file exceeds the 200,000 character limit.");
    // Textarea normalizes CRLF for display; retain upload bytes as text until the user edits it.
    content.value = text;
    uploadedText = text;
    sourceFilename = file.name;
    $("upload-name").textContent = file.name;
    countCharacters();
  } catch (error) {
    showError(error instanceof TypeError ? "The file must be valid UTF-8 text." : error.message);
  } finally {
    $("markdown-file").value = "";
  }
});

function showSuccess(saved) {
  const req = saved.request;
  const panel = $("save-success");
  panel.replaceChildren(element("h2", "Production request saved."));
  panel.append(element("p", "Production not started · Human review required · Publishing disabled"));
  panel.append(element("p", `Project ID: ${req.project_id}`));
  panel.append(element("p", `Formats: ${req.formats.map(formatLabel).join(" + ")}`));
  panel.append(element("p", "Saved files:"));
  const files = element("ul");
  for (const name of saved.saved_files) files.append(element("li", `projects/${req.project_id}/${name}`));
  panel.append(files);
  const hash = element("p", "Content SHA-256: ");
  hash.append(element("code", req.content_sha256));
  panel.append(hash);
  const link = element("a", "Open Backlot ↗");
  link.href = saved.backlot_url;
  link.target = "_blank";
  link.rel = "noopener";
  panel.append(link);
  panel.hidden = false;
  panel.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (saving) return;
  clearError();
  $("save-success").hidden = true;
  const formats = [...form.querySelectorAll('[name="formats"]:checked')].map((input) => input.value);
  const selectedMode = mode();
  const text = uploadedText ?? content.value;
  if (!formats.length) return showError("Choose at least one output format: Short or Long.");
  if (selectedMode !== "canonical" && !text.trim()) return showError(selectedMode === "topic"
    ? "Enter a topic to research." : "Enter the story text before saving.");
  if (selectedMode === "canonical" && !$("canonical-package").value) return showError("Select an approved canonical package.");
  const id = $("project-id").value;
  if (id && !/^[a-z0-9][a-z0-9-]{0,63}$/.test(id)) return showError("Project ID may only use lowercase letters, digits and hyphens (max 64 characters).");
  saving = true;
  $("save-button").disabled = true;
  $("save-button").textContent = "Saving request…";
  try {
    const saved = await api("productions", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: id || null, title: $("title").value || null, input_mode: selectedMode,
        content: selectedMode === "canonical" ? null : text,
        canonical_package_id: selectedMode === "canonical" ? $("canonical-package").value : null,
        source_filename: selectedMode === "canonical" ? null : sourceFilename,
        formats, style: "stickman_horror_2d", review_mode: "human_required", publishing_enabled: false,
      }),
    });
    showSuccess(saved);
    // Repeated clicks with the same request cannot accidentally create duplicate projects.
    $("project-id").value = saved.request.project_id;
    await loadProductions();
  } catch (error) {
    showError(error.message || "Could not save the request. Check the local connection and try again.");
  } finally {
    saving = false;
    $("save-button").disabled = false;
    $("save-button").textContent = "Save / Create Project ↗";
  }
});

function formatLabel(format) { return format === "short" ? "Short 9:16" : "Long 16:9"; }
function activate(view) {
  $("new-view").hidden = view !== "new";
  $("list-view").hidden = view !== "list";
  $("new-tab").classList.toggle("active", view === "new");
  $("list-tab").classList.toggle("active", view === "list");
  $("new-tab").setAttribute("aria-current", view === "new" ? "page" : "false");
  $("list-tab").setAttribute("aria-current", view === "list" ? "page" : "false");
  $("page-name").textContent = view === "new" ? "New Production" : "My Productions";
}
$("new-tab").addEventListener("click", () => {
  activate("new");
  if (!$("save-success").hidden) {
    form.reset();
    uploadedText = sourceFilename = null;
    $("project-id").value = "";
    $("save-success").hidden = true;
    $("upload-name").textContent = "The original text is saved unchanged.";
    switchMode();
    countCharacters();
  }
});
$("list-tab").addEventListener("click", () => { activate("list"); loadProductions(); });
$("refresh-list").addEventListener("click", () => loadProductions());

async function showDetail(id) {
  $("intake-panel").replaceChildren();
  $("review-panel").replaceChildren();
  $("visual-bible-panel").replaceChildren();
  $("visual-bible-panel").dataset.projectId = id;
  try {
    const { request } = await api(`productions/${encodeURIComponent(id)}`);
    $("detail-content").textContent = request.content ?? JSON.stringify(request.canonical_package, null, 2);
    $("production-detail").hidden = false;
    $("production-detail").scrollIntoView({ behavior: "smooth", block: "center" });
    if (request.input_mode !== "story") return intakeMessage("Story Intake supports Full story requests only at this stage.");
    try {
      renderIntake(await api(`productions/${encodeURIComponent(id)}/intake`), id);
    } catch (error) {
      intakeMessage(error.code === "not_prepared"
        ? "Story draft not prepared yet. Prepare Story Draft runs intake only: no research, narration or rendering."
        : error.message, error.code !== "not_prepared");
    }
    await loadReview(id);
  } catch (error) {
    $("production-detail").hidden = false;
    $("detail-content").textContent = error.message;
  }
}

function intakeMessage(text, isError = false) {
  const note = element("p", text, isError ? "error-panel" : "field-help");
  if (isError) note.setAttribute("role", "alert");
  $("intake-panel").replaceChildren(note);
}

function visibleBreaks(text) { return text.replace(/\r\n/g, "↵\n").replace(/\r/g, "↵\n"); }

function renderIntake(data, id) {
  const report = data.report;
  const panel = $("intake-panel");
  panel.replaceChildren(element("h2", "Story Draft"));
  panel.append(element("p", data.status === "already_prepared"
    ? "Already prepared. The verified existing draft is shown; nothing was rewritten." : "", "field-help"));
  const chips = element("div", undefined, "chip-row");
  chips.append(element("span", "Review status: Pending human review", "status-chip"),
    element("span", "Production not started", "status-chip"));
  panel.append(chips);
  panel.append(element("p", "Automatic analysis is incomplete: deterministic rules only. Plot, twists, "
    + "contradictions, who-is-who and speakers were not analyzed. Nothing below is approved.", "coverage-warning"));
  const counts = element("dl", undefined, "intake-counts");
  for (const [key, label] of [["segments", "Segments"], ["characters", "Character candidates"],
    ["locations", "Location candidates"], ["objects", "Object candidates"], ["dialogue_lines", "Dialogue lines"],
    ["time_expressions", "Time expressions"], ["proposed_changes", "Proposed changes"],
    ["human_interpretation_items", "Questions for you"]]) {
    counts.append(element("dt", label), element("dd", String(report.counts[key])));
  }
  panel.append(counts);

  panel.append(element("h3", "Proposed editorial changes (not approved)"));
  if (!data.changes.length) panel.append(element("p", "None proposed.", "field-help"));
  for (const change of data.changes) {
    const box = element("article", undefined, "change-card");
    box.append(element("strong", `${change.id} · ${change.rule.replaceAll("_", " ")} · line ${change.source_span.line}`
      + ` · confidence ${change.confidence}`));
    box.append(element("p", change.rationale, "field-help"));
    box.append(element("small", "Before"), element("pre", visibleBreaks(change.before_excerpt)));
    box.append(element("small", "After (proposal only)"), element("pre", visibleBreaks(change.after_excerpt)));
    panel.append(box);
  }

  panel.append(element("h3", "Needs your interpretation"));
  const questions = element("ol", undefined, "question-list");
  for (const item of data.human_interpretation) {
    const where = item.segment_ids.length ? ` (${item.segment_ids.length} segments)` : "";
    questions.append(element("li", `${item.question}${where}`));
  }
  panel.append(questions);

  panel.append(element("h3", "Extracted candidates (unverified)"));
  for (const [key, label] of [["characters", "Characters"], ["locations", "Locations"], ["objects", "Objects"]]) {
    const items = data.candidates[key].map((c) => `${c.label} (${c.mention_count})`).join(", ");
    panel.append(element("p", `${label}: ${items || "none"}`, "candidate-line"));
  }
  panel.append(element("h3", "Saved files"));
  const files = element("ul", undefined, "file-list");
  for (const name of data.saved_files) files.append(element("li", `projects/${id}/${name}`));
  panel.append(files);
}

async function prepareDraft(id, button) {
  button.disabled = true;
  button.textContent = "Preparing story draft…";
  try {
    const data = await api(`productions/${encodeURIComponent(id)}/intake`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
    await showDetail(id);
    renderIntake(data, id);
    await loadProductions();
  } catch (error) {
    await showDetail(id);
    intakeMessage(error.message || "Could not prepare the story draft. The original story is unchanged.", true);
  } finally {
    button.disabled = false;
    button.textContent = "Prepare Story Draft";
  }
}

function draftStatus(row) {
  if (row.input_mode !== "story") return "Story draft: not available for this input mode yet";
  if (row.intake_status === "prepared") return "Story draft: prepared · pending human review";
  return "Story draft: not prepared";
}

let listRequest = 0;

async function loadProductions() {
  const request = ++listRequest;  // Overlapping loads (page load + tab click) must not render twice.
  $("list-status").hidden = false;
  $("list-status").textContent = "Loading productions…";
  $("production-list").replaceChildren();
  try {
    const rows = await api("productions");
    if (request !== listRequest) return;
    $("production-list").replaceChildren();
    $("production-count").textContent = rows.length;
    $("list-status").textContent = "No productions yet. Choose New Production to save your first idea.";
    $("list-status").hidden = rows.length > 0;
    for (const row of rows) {
      const card = element("article", undefined, "production-card");
      const body = element("div");
      body.append(element("h2", row.title), element("code", row.project_id));
      body.append(element("p", row.kind === "studio"
        ? `${row.input_mode} · ${row.formats.map(formatLabel).join(" + ")} · Human review required`
        : "Existing workspace · Review status: see Backlot"));
      body.append(element("span", row.kind === "studio" ? "Production not started" : "Existing workspace", "status-chip"));
      const actions = element("div", undefined, "card-actions");
      if (row.kind === "studio") {
        const button = element("button", "View input", "secondary-button");
        button.type = "button";
        button.addEventListener("click", () => showDetail(row.project_id));
        const prepare = element("button", "Prepare Story Draft", "secondary-button prepare-draft");
        prepare.type = "button";
        prepare.dataset.projectId = row.project_id;
        if (row.input_mode !== "story") {
          prepare.disabled = true;
          prepare.title = "Story Intake supports Full story requests only at this stage.";
        }
        prepare.addEventListener("click", () => prepareDraft(row.project_id, prepare));
        const reviewButton = element("button", "Story Review", "secondary-button open-review");
        reviewButton.type = "button";
        reviewButton.dataset.projectId = row.project_id;
        reviewButton.disabled = row.input_mode !== "story";
        reviewButton.addEventListener("click", async () => {
          await showDetail(row.project_id);
          $("review-panel").scrollIntoView({ block: "start" });
        });
        actions.append(button, prepare, reviewButton);
        const visual = element("button", "Visual Bible", "secondary-button open-visual-bible");
        visual.type = "button";
        visual.dataset.projectId = row.project_id;
        visual.disabled = row.input_mode !== "story";
        visual.addEventListener("click", async () => {
          await showDetail(row.project_id);
          $("visual-bible-panel").scrollIntoView({block: "start"});
        });
        actions.append(visual);
        body.append(element("p", draftStatus(row), "intake-status"));
      }
      const board = element("a", "Open Backlot ↗");
      board.href = row.backlot_url;
      board.target = "_blank";
      board.rel = "noopener";
      actions.append(board);
      card.append(body, actions);
      $("production-list").append(card);
    }
  } catch {
    $("list-status").textContent = "Could not load productions. Choose Refresh to retry.";
  }
}

switchMode();
loadPackages();
loadProductions();

// ---------------------------------------------------------------------------
// P2.2 editorial review: decisions are recorded only; they never start production.
// ---------------------------------------------------------------------------

const STATUS_LABEL = {
  accepted: "Accepted", rejected: "Rejected", deferred: "Deferred", answered: "Answered",
  open: "Open (unresolved)", undecided: "Undecided", stale: "Stale (inputs changed)",
  intentionally_unresolved: "Intentionally unresolved",
};
const COLLECTION_LABEL = {
  characters: "Characters", locations: "Locations", objects: "Objects", facts: "Facts and claims",
  events: "Events (relative order)", dialogue: "Dialogue and messages", sound_cues: "Sound cues",
  motifs: "Motifs", continuity_rules: "Continuity rules",
};
const META_FIELDS = ["kind", "identity_status", "on_screen_policy", "story_phase", "certainty", "channel",
  "speaker_label", "attribution_status", "reported_by", "revealed_at", "conflicts_with", "narrative_order"];

function section(title, open = false) {
  const box = element("details", undefined, "review-section");
  box.open = open;
  box.append(element("summary", title));
  return box;
}

function statusChip(review) {
  return element("span", STATUS_LABEL[review.status] || review.status, `decision-chip decision-${review.status}`);
}

function reviewMessage(text, isError = false) {
  const note = element("p", text, isError ? "error-panel" : "field-help");
  if (isError) note.setAttribute("role", "alert");
  $("review-panel").prepend(note);
  note.scrollIntoView({ block: "center" });
}

async function decide(id, targetId, review, decision, answer) {
  try {
    await api(`productions/${encodeURIComponent(id)}/review/decisions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_id: targetId, decision, answer: answer ?? null, supersedes: review.decision_id }),
    });
  } catch (error) {
    await loadReview(id, targetId);
    reviewMessage(error.message, true);
    return;
  }
  await loadReview(id, targetId);
}

function decisionButton(id, targetId, review, choice, label, read) {
  const button = element("button", label, "secondary-button decision-button");
  button.type = "button";
  button.dataset.target = targetId;
  button.dataset.decision = choice;
  button.addEventListener("click", () => {
    const answer = read ? read() : undefined;
    if (read && !answer) return reviewMessage("An empty answer is not recorded; the question stays open.", true);
    return decide(id, targetId, review, choice, answer);
  });
  return button;
}

function decisionRow(id, targetId, review, choices) {
  const row = element("div", undefined, "decision-row");
  row.append(statusChip(review));
  for (const [choice, label] of choices) row.append(decisionButton(id, targetId, review, choice, label));
  if (review.history.length > 1) row.append(element("small", `${review.history.length} decisions recorded`));
  return row;
}

const ACCEPT_REJECT_DEFER = [["accept", "Accept"], ["reject", "Reject"], ["defer", "Defer"]];

function evidenceList(evidence) {
  const list = element("ul", undefined, "evidence-list");
  for (const e of evidence.slice(0, 4)) list.append(element("li", `${e.segment_id}: ${visibleBreaks(e.quote)}`));
  if (evidence.length > 4) list.append(element("li", `+${evidence.length - 4} more source spans`));
  return list;
}

function itemTitle(item) {
  return item.name || item.label || item.text || item.rule || item.statement;
}

function itemCard(id, item) {
  const card = element("article", undefined, "review-card");
  card.dataset.target = item.id;
  card.append(element("strong", `${item.id} · ${itemTitle(item)}`));
  const meta = META_FIELDS.filter((k) => item[k] !== undefined && item[k] !== null && `${item[k]}` !== "")
    .map((k) => `${k.replaceAll("_", " ")}: ${Array.isArray(item[k]) ? item[k].join(", ") || "none" : item[k]}`);
  if (meta.length) card.append(element("small", meta.join(" · "), "item-meta"));
  const texts = [item.description, item.proposed_treatment, item.production_guidance,
    item.review_note ? `Review note: ${item.review_note}` : null];
  if (item.statement && itemTitle(item) !== item.statement) texts.unshift(item.statement);
  for (const text of texts) if (text) card.append(element("p", text, "item-text"));
  card.append(evidenceList(item.evidence));
  card.append(decisionRow(id, item.id, item.review, ACCEPT_REJECT_DEFER));
  return card;
}

function questionCard(id, q) {
  const card = element("article", undefined, "review-card question-card");
  card.dataset.target = q.id;
  card.append(element("strong", `${q.id} · ${q.origin === "intake" ? "Story Intake" : "Story Bible"}`));
  card.append(element("p", q.question, "item-text"));
  if (q.evidence) card.append(evidenceList(q.evidence));
  if (q.review.answer) card.append(element("p", `Recorded answer: ${q.review.answer}`, "recorded-answer"));
  const input = element("textarea", undefined, "answer-input");
  input.rows = 2;
  input.maxLength = 4000;
  input.placeholder = "Your interpretation (leave empty to keep the question open)";
  input.setAttribute("aria-label", `Answer for ${q.id}`);
  const row = element("div", undefined, "decision-row");
  row.append(statusChip(q.review),
    decisionButton(id, q.id, q.review, "answer", "Record answer", () => input.value.trim() ? input.value : ""),
    decisionButton(id, q.id, q.review, "preserve_ambiguity", "Preserve Ambiguity"),
    decisionButton(id, q.id, q.review, "defer", "Defer"));
  card.append(input, row);
  return card;
}

function durationLine(plan) {
  const d = plan.duration;
  const target = plan.target_seconds
    ? ` Target ${plan.target_seconds.min}-${plan.target_seconds.max} s.` : " Duration unknown until TTS.";
  return `Estimated ${d.estimated_seconds} s (${d.syllables} syllables + ${d.planned_silence_seconds} s planned `
    + `silence). Estimate only, pending TTS measurement.${target}`;
}

function beatBlock(beat) {
  const b = element("div", undefined, "beat");
  const verbatim = beat.narration.mode === "verbatim";
  b.append(element("span", verbatim ? "Verbatim source text" : "Authored proposal, not source text",
    `mode-badge mode-${beat.narration.mode}`));
  const sources = [...new Set(beat.narration.sources.map((s) => s.segment_id))].join(", ");
  b.append(element("small", `${beat.id} · sources ${sources}`));
  b.append(element("pre", visibleBreaks(beat.narration.text)));
  const parts = [`Action: ${beat.staging.action}`, `Camera: ${beat.staging.camera}`,
    `Environment: ${beat.staging.environment}`];
  if (beat.staging.uncertainty) parts.push(`Uncertainty: ${beat.staging.uncertainty}`);
  if (beat.sound_cue_ids.length) parts.push(`Sound: ${beat.sound_cue_ids.join(", ")}`);
  if (beat.silence_after_seconds) parts.push(`Silence ${beat.silence_after_seconds} s`);
  b.append(element("small", parts.join(" · "), "item-meta"));
  return b;
}

function formatCard(id, plan) {
  const card = element("article", undefined, "review-card format-card-review");
  card.dataset.target = plan.id;
  card.append(element("strong", `${plan.id} · ${plan.format === "short" ? "Short" : "Long"} ${plan.aspect_ratio}`));
  card.append(element("small", durationLine(plan), "item-meta"));
  if (plan.intent) card.append(element("p", plan.intent, "item-text"));
  if (plan.depends_on_changes.length) {
    card.append(element("p", `Depends on proposed edits: ${plan.depends_on_changes.join(", ")}`, "item-text"));
  }
  for (const chapter of plan.chapters) {
    const box = element("details", undefined, "chapter");
    box.append(element("summary", `${chapter.id} · ${chapter.title} (${chapter.beats.length} beats)`));
    for (const beat of chapter.beats) box.append(beatBlock(beat));
    card.append(box);
  }
  card.append(decisionRow(id, plan.id, plan.review, ACCEPT_REJECT_DEFER));
  return card;
}

async function importDraft(id, file) {
  let draft;
  try {
    draft = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()));
  } catch {
    return reviewMessage("The file must be valid UTF-8 JSON.", true);
  }
  const response = await fetch(`/studio/api/productions/${encodeURIComponent(id)}/fiction-package`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const problems = result.detail?.problems || [];
    return reviewMessage(`${result.detail?.message || "Import failed."}${problems.length
      ? `\n${problems.slice(0, 12).join("\n")}` : ""}`, true);
  }
  await loadReview(id);
}

function importDraftControl(id) {
  const wrap = element("div", undefined, "import-draft");
  wrap.append(element("p", "No Story Bible package yet. Import a Story Bible draft (.json). It is validated "
    + "against the original story; importing approves nothing.", "field-help"));
  const label = element("label", "Import Story Bible draft (.json)", "secondary-button");
  const input = element("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.id = "bible-draft-file";
  input.className = "sr-only";
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (file) importDraft(id, file).finally(() => { input.value = ""; });
  });
  label.append(input);
  wrap.append(label);
  return wrap;
}

async function loadReview(id, focusTarget) {
  let view;
  try {
    view = await api(`productions/${encodeURIComponent(id)}/review`);
  } catch (error) {
    $("review-panel").replaceChildren(element("p", error.message, "error-panel"));
    return;
  }
  renderReview(view, id);
  if (focusTarget) {
    document.querySelector(`#review-panel [data-target="${focusTarget}"]`)?.scrollIntoView({ block: "center" });
  }
}

function reviewHeader(view) {
  const chips = element("div", undefined, "chip-row");
  const status = view.review_status === "decisions_recorded" ? "Decisions recorded" : "Pending human review";
  chips.append(element("span", `Review status: ${status}`, "status-chip review-status-chip"),
    element("span", "Production not started", "status-chip"));
  const c = view.counts;
  const counts = `Accepted ${c.accepted} · Rejected ${c.rejected} · Deferred ${c.deferred} · Answered ${c.answered}`
    + ` · Intentionally unresolved ${c.intentionally_unresolved}`
    + ` · Open questions ${c.open} · Undecided ${c.undecided}${c.stale ? ` · Stale ${c.stale}` : ""}`;
  const missing = element("div", undefined, "coverage-warning missing-coverage");
  missing.append(element("strong", "Missing or incomplete"));
  const list = element("ul");
  for (const m of view.missing_coverage) list.append(element("li", m));
  missing.append(list);
  return [chips, element("p", view.approval_scope, "field-help"), element("p", counts, "review-counts"), missing];
}

function changeCard(id, change) {
  const card = element("article", undefined, "review-card");
  card.dataset.target = change.id;
  card.append(element("strong", `${change.id} · ${change.rule.replaceAll("_", " ")} · line ${change.source_span.line}`));
  card.append(element("p", change.rationale, "item-text"));
  card.append(element("small", "Before"), element("pre", visibleBreaks(change.before_excerpt)));
  card.append(element("small", "After"), element("pre", visibleBreaks(change.after_excerpt)));
  card.append(decisionRow(id, change.id, change.review, ACCEPT_REJECT_DEFER));
  return card;
}

function renderPackage(panel, id, pkg) {
  panel.append(element("h3", `Story Bible · ${pkg.title} · ${pkg.package_id}`));
  panel.append(element("p", `Authored by ${pkg.provenance.draft.authored_by}. ${pkg.coverage.semantic_basis}`,
    "field-help"));
  for (const [key, label] of Object.entries(COLLECTION_LABEL)) {
    const box = section(`${label} (${pkg.collections[key].length})`);
    box.dataset.collection = key;
    for (const item of pkg.collections[key]) box.append(itemCard(id, item));
    panel.append(box);
  }
  const formats = section("Short and Long drafts", true);
  for (const key of ["short", "long"]) formats.append(formatCard(id, pkg.formats[key]));
  panel.append(formats);
  const sp = pkg.stickman_production;
  const stick = section("Stickman Horror preparation (preliminary, not rendered)");
  stick.append(element("p", sp.uncertainty_policy, "item-text"));
  for (const ch of sp.characters) {
    stick.append(element("p", `${ch.character_id}: ${ch.silhouette} (${ch.basis.replaceAll("_", " ")})`, "item-text"));
  }
  stick.append(element("small", `Not primary output: ${sp.forbidden_primary_treatments.join(", ").replaceAll("_", " ")}`,
    "item-meta"));
  panel.append(stick);
}

function renderReview(view, id) {
  const panel = $("review-panel");
  panel.replaceChildren(element("h2", "Story Review"));
  if (view.state === "intake_missing") {
    panel.append(element("p", `Story review starts after Prepare Story Draft. ${view.message}`, "field-help"));
    return;
  }
  panel.append(...reviewHeader(view));
  if (!view.package) panel.append(importDraftControl(id));
  const original = section("Original story (read-only)");
  original.append(element("pre", view.original_story, "story-text"));
  const working = section("Proposed working text (all proposed edits applied; preview only)");
  working.append(element("pre", view.working_text_proposal, "story-text"));
  panel.append(original, working);
  const edits = section(`Proposed edits (${view.changes.length})`, true);
  for (const change of view.changes) edits.append(changeCard(id, change));
  panel.append(edits);
  const unresolved = view.questions.filter((q) => !["answered", "intentionally_unresolved"].includes(q.review.status)).length;
  const questions = section(`Interpretation questions (${unresolved} unresolved of ${view.questions.length})`, true);
  for (const q of view.questions) questions.append(questionCard(id, q));
  panel.append(questions);
  if (view.package) {
    renderPackage(panel, id, view.package);
    const reviewed = element("section", undefined, "reviewed-story");
    reviewed.id = "reviewed-story-panel";
    panel.append(reviewed);
    loadReviewed(id, reviewed);
  }
}

async function loadReviewed(id, panel, version) {
  panel.replaceChildren(element("p", "Checking reviewed story versions…", "field-help"));
  try {
    const data = await api(`productions/${encodeURIComponent(id)}/reviewed-story${version ? `/${version}` : ""}`);
    if (panel.isConnected) renderReviewed(id, panel, data);
  } catch (error) {
    if (panel.isConnected) panel.replaceChildren(element("p", error.message, "error-panel"));
  }
}

function renderReviewed(id, panel, data) {
  if ($("visual-bible-panel").dataset.projectId === id) loadVisualBible(id, $("visual-bible-panel"));
  panel.replaceChildren(element("h3", "Reviewed story · pre-production content only"));
  panel.append(element("p", "Materialization saves an immutable candidate. Approve Reviewed Story is a separate "
    + "human action for the exact displayed version and hashes. No action here starts production or permits publishing.", "field-help"));
  const materialize = element("button", "Materialize Reviewed Story", "secondary-button");
  materialize.type = "button";
  materialize.id = "materialize-reviewed-story";
  materialize.addEventListener("click", async () => {
    materialize.disabled = true;
    try {
      const result = await api(`productions/${encodeURIComponent(id)}/reviewed-story`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
      });
      if (panel.isConnected) renderReviewed(id, panel, result);
    } catch (error) {
      reviewMessage(error.message, true);
    } finally {
      materialize.disabled = false;
    }
  });
  panel.append(materialize);
  if (data.state === "missing") {
    panel.append(element("p", "No reviewed version yet. Decisions alone approve nothing.", "field-help"));
    return;
  }
  const selector = element("select");
  selector.id = "reviewed-version";
  selector.setAttribute("aria-label", "Reviewed story version");
  for (const version of data.versions) {
    const option = element("option", version);
    option.value = version;
    option.selected = version === data.version;
    selector.append(option);
  }
  selector.addEventListener("change", () => loadReviewed(id, panel, selector.value));
  panel.append(selector);
  panel.append(element("p", `${data.version} · ${data.approval ? "Approved for pre-production story content; frozen" : "Awaiting explicit approval"}`
    + `${data.is_current ? "" : " · Decisions changed: materialize a new version and approve again"}`, "reviewed-status"));
  panel.append(element("pre", `Package SHA-256: ${data.package_sha256}\nManifest SHA-256: ${data.manifest_sha256}`,
    "story-text reviewed-hashes"));
  const pkg = data.package;
  const blockers = element("div", undefined, "coverage-warning reviewed-blockers");
  blockers.append(element("strong", `Remaining blockers: ${pkg.blockers.length}`));
  const list = element("ul");
  for (const issue of pkg.blockers) list.append(element("li", issue));
  blockers.append(list);
  panel.append(blockers);
  const decisions = section("Applied editorial changes and semantic decisions", true);
  for (const choice of ["accept", "reject", "defer", "answer", "preserve_ambiguity", "undecided", "stale"]) {
    const rows = pkg.dispositions.filter(d => d.decision === choice);
    if (!rows.length) continue;
    const box = section(`${choice === "preserve_ambiguity" ? "Intentionally unresolved questions" : choice} (${rows.length})`);
    const items = element("ul", undefined, "evidence-list");
    for (const d of rows) items.append(element("li", `${d.target_id} · ${d.kind} · ${d.question || ""}`
      + `${d.answer ? ` · Human interpretation: ${d.answer}` : ""} · ${d.decision_id || "No decision"}`));
    box.append(items);
    decisions.append(box);
  }
  panel.append(decisions);
  const working = section("Reviewed working text and source mapping");
  working.append(element("pre", pkg.working_text, "story-text"));
  working.append(element("pre", JSON.stringify(pkg.source_mapping, null, 2), "story-text"));
  panel.append(working);
  const canon = section("Accepted canonical Story Bible and source evidence");
  canon.append(element("pre", JSON.stringify(pkg.canonical_story, null, 2), "story-text"));
  panel.append(canon);
  const formats = section("Reviewed Short and Long contents", true);
  for (const [name, plan] of Object.entries(pkg.canonical_story.formats)) {
    const format = section(`${name === "short" ? "Short" : "Long"} ${plan.aspect_ratio}`, true);
    format.append(element("p", durationLine(plan), "field-help"));
    for (const chapter of plan.chapters) for (const beat of chapter.beats) format.append(beatBlock(beat));
    formats.append(format);
  }
  panel.append(formats);
  const approval = element("button", "Approve Reviewed Story", "primary-button");
  approval.id = "approve-reviewed-story";
  approval.type = "button";
  const consent = element("input");
  consent.type = "checkbox";
  consent.id = "reviewed-story-consent";
  const label = element("label", ` I reviewed ${data.version}, its changes, accepted/rejected items, intentional `
    + "ambiguities and both plans above. I approve these exact hashes for pre-production story content only.", "field-help");
  label.prepend(consent);
  const unavailable = Boolean(pkg.blockers.length || !data.is_current || data.approval);
  approval.disabled = true;
  consent.disabled = unavailable;
  consent.addEventListener("change", () => { approval.disabled = unavailable || !consent.checked; });
  approval.addEventListener("click", async () => {
    approval.disabled = true;
    try {
      const result = await api(`productions/${encodeURIComponent(id)}/reviewed-story/${data.version}/approve`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({package_sha256: data.package_sha256, manifest_sha256: data.manifest_sha256}),
      });
      if (panel.isConnected) renderReviewed(id, panel, result);
    } catch (error) {
      reviewMessage(error.message, true);
      await loadReviewed(id, panel);
    }
  });
  panel.append(label, approval);
}
