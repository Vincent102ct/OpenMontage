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

async function loadProductions() {
  $("list-status").hidden = false;
  $("list-status").textContent = "Loading productions…";
  $("production-list").replaceChildren();
  try {
    const rows = await api("productions");
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
        actions.append(button, prepare);
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
