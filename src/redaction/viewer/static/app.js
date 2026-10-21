"use strict";

const KINDS = [
  ["evidence", "Evidence (violation or look-alike)"],
  ["correlate", "Correlates (reveal a secret without its value)"],
  ["secret_mention", "Secret mentioned in passing"],
  ["lab_noise", "Lab chatter"],
  ["background", "Real cluster records (Philly trace)"],
];
const STAGES = [
  ["planned", "Planned", "facts fixed in code"],
  ["rendered", "Rendered", "phrased by the renderer"],
  ["valid", "Valid", "passed the code checks"],
  ["reviewed", "Reviewed", "blind label check"],
  ["kept", "Kept", "frozen for runs"],
];
const CHECKS = {
  shape: "One rendered line per planned line",
  background_intact: "Real records left unchanged",
  required_kept: "Secret values and cue tokens kept",
  correlate_kept: "Correlate details kept",
  no_verbatim_in_correlate: "Correlates do not state the value",
  no_foreign_option: "No other option of a secret appears",
  label_clean: "Non-violations carry no violation-only token",
  no_duplicates: "No repeated lines",
};
const LABELS = { violation: "Violation", red_herring: "Red herring", clean: "Clean" };
const POLICY = { text_redaction: "Text redaction", contextual_rewrite: "Contextual rewrite", self_redaction: "Self-redaction" };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const human = (s) => String(s).replaceAll("_", " ");
const f2 = (v) => (v == null ? "n/a" : Number(v).toFixed(2));

let SITE = null, build = null, selected = null, showBackground = false;

function setTab(name) {
  for (const t of ["pipeline", "runs"]) {
    $("tab-" + t).setAttribute("aria-selected", String(t === name));
    $("panel-" + t).hidden = t !== name;
  }
  history.replaceState(null, "", name === "runs" ? "#runs" : "#");
}

/* ---------- Data pipeline ---------- */

function renderSplits() {
  $("split-seg").innerHTML = SITE.builds.map((b) =>
    `<button type="button" aria-pressed="${b === build}" data-v="${b.manifest.version}">${esc(b.manifest.split)}</button>`).join("");
  $("split-seg").querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => { build = SITE.builds.find((b) => b.manifest.version === btn.dataset.v); selected = null; renderPipeline(); };
  });
}

function renderStages(m) {
  const s = m.stages;
  let prev = s.planned;
  $("stages").innerHTML = STAGES.map(([key, name, sub]) => {
    const skipped = key === "reviewed" && !m.reviewer;
    const lost = !skipped && s[key] < prev;
    if (!skipped) prev = s[key];
    return `<div class="stage ${skipped ? "skipped" : ""} ${lost ? "loss" : ""}">
      <b>${skipped ? "—" : s[key]}</b><span>${name}</span>
      <small>${skipped ? "skipped: no reviewer model" : sub}</small></div>`;
  }).join("");
}

function renderComposition() {
  const kept = build.scenarios;
  const types = [...new Set(build.records.map((r) => r.violation_type))];
  const cols = [["violation", null], ["red_herring", "easy"], ["red_herring", "medium"], ["red_herring", "hard"], ["clean", null]];
  const count = (t, [l, d]) => kept.filter((s) => s.violation_type === t && s.label === l && (s.difficulty ?? null) === d).length;
  const head = `<thead><tr><th>Violation type</th><th>Violation</th><th title="Red herring, easy">RH easy</th><th title="Red herring, medium">RH med</th><th title="Red herring, hard">RH hard</th><th>Clean</th></tr></thead>`;
  const rows = types.map((t) => `<tr><td>${esc(human(t))}</td>${cols.map((c) => {
    const n = count(t, c); return `<td class="${n ? "" : "zero"}">${n}</td>`; }).join("")}</tr>`).join("");
  $("composition").innerHTML = head + `<tbody>${rows}</tbody>`;
}

function renderKinds(m) {
  const total = Object.values(m.line_kinds).reduce((a, b) => a + b, 0) || 1;
  $("kinds").innerHTML = `<div class="kind-bar" role="img" aria-label="Share of lines by kind">${KINDS.map(([k]) =>
      `<i class="k-${k}" style="width:${(100 * (m.line_kinds[k] || 0) / total).toFixed(2)}%"></i>`).join("")}</div>
    <div class="legend">${KINDS.map(([k, name]) =>
      `<div><i class="k-${k}"></i><span>${name}</span><span>${(100 * (m.line_kinds[k] || 0) / total).toFixed(0)}%</span></div>`).join("")}</div>`;
  $("lines-note").textContent = `${m.lines.min}–${m.lines.max} lines per scenario (mean ${m.lines.mean}). ` +
    (m.background_jobs ? `Background drawn from ${m.background_jobs.toLocaleString()} real jobs.` : "No background sample: run `redaction data background`.");
}

function renderIssues(m) {
  const failed = build.records.filter((r) => r.status !== "kept");
  const counts = m.issues || {};
  const rows = Object.entries(CHECKS).map(([k, name]) => {
    const n = counts[k] || 0;
    return `<div class="issue-row"><span>${name}</span><span><span class="pill ${n ? "fail" : "pass"}">${n ? n + " failed" : "pass"}</span></span></div>`;
  }).join("");
  const review = m.reviewer
    ? `<p class="note">Reviewer ${esc(m.reviewer)}: ${build.records.filter((r) => r.status === "review_disagrees").length} scenarios read as the wrong label.</p>`
    : `<p class="note">No blind review in this build. With the template renderer, the checks above pass by construction; they matter once a model rephrases lines.</p>`;
  $("issues").innerHTML = rows + review + (failed.length ? `<p class="note">${failed.length} scenarios dropped: ${failed.map((r) => esc(r.scenario_id)).join(", ")}</p>` : "");
}

function filtered() {
  const lab = $("f-label").value, typ = $("f-type").value;
  return build.scenarios.filter((s) => (!lab || s.label === lab) && (!typ || s.violation_type === typ));
}

function renderList() {
  const types = [...new Set(build.scenarios.map((s) => s.violation_type))];
  const cur = $("f-type").value;
  $("f-type").innerHTML = `<option value="">All violation types</option>` +
    types.map((t) => `<option value="${t}">${esc(human(t))}</option>`).join("");
  if (types.includes(cur)) $("f-type").value = cur;
  const list = filtered();
  if (!list.includes(selected)) selected = list[0] || null;
  $("scenario-count").textContent = `${list.length} of ${build.scenarios.length}`;
  $("scenario-list").innerHTML = list.map((s, i) => `<li tabindex="0" data-i="${i}" aria-selected="${s === selected}">
      <b>${esc(s.scenario_id)}</b>
      <span class="label-${s.label}">${LABELS[s.label]}${s.difficulty ? " · " + s.difficulty : ""}</span></li>`).join("")
    || `<li><span>No scenarios match.</span></li>`;
  $("scenario-list").querySelectorAll("li[data-i]").forEach((li) => {
    const pick = () => { selected = list[+li.dataset.i]; renderList(); };
    li.onclick = pick;
    li.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } };
  });
  renderDetail();
}

function highlight(text, secrets, snippet) {
  let html = esc(text);
  if (snippet) html = html.replace(esc(snippet), `<mark class="correlate">${esc(snippet)}</mark>`);
  for (const v of secrets) html = html.split(esc(v)).join(`<mark class="secret">${esc(v)}</mark>`);
  return html;
}

function renderDetail() {
  const s = selected;
  if (!s) { $("detail").innerHTML = `<p class="empty">Pick a scenario.</p>`; return; }
  const values = s.secrets.map((x) => x.value);
  const corrByLog = Object.fromEntries(s.correlates.map((c) => [c.log_id, c]));
  const keys = new Set(s.key_evidence_ids);
  const secretRows = s.secrets.map((x) => {
    const cs = s.correlates.filter((c) => c.secret_type === x.secret_type);
    return `<tr><td>${esc(human(x.secret_type))}</td><td>${esc(x.value)}</td>
      <td>${cs.map((c) => `${esc(c.log_id)} · ${c.strength}`).join("<br>") || "none"}</td>
      <td style="white-space:normal">${cs.map((c) => esc(c.rationale)).join("<br>")}</td></tr>`;
  }).join("");
  const hidden = s.logs.filter((e) => e.kind === "background").length;
  const logs = s.logs.filter((e) => showBackground || e.kind !== "background").map((e) => {
    const c = corrByLog[e.log_id];
    return `<div class="${e.kind === "background" ? "background" : ""} ${keys.has(e.log_id) ? "key" : ""}">
      <i class="k-${e.kind || "background"}" title="${esc(human(e.kind || ""))}"></i>
      <span class="id">${esc(e.log_id)}</span><span class="src">${esc(e.source)}</span>
      <span class="txt">${highlight(e.text, values, c && c.snippet)}</span></div>`;
  }).join("");
  $("detail").innerHTML = `
    <h3>${esc(s.scenario_id)}</h3>
    <p class="claim">Claim: ${esc(s.claim)}</p>
    <div class="facts">
      <div><span>Label</span><b class="label-${s.label}">${LABELS[s.label]}${s.difficulty ? " · " + s.difficulty : ""}</b></div>
      <div><span>Setup</span><b>${esc(s.variant)}</b></div>
      <div><span>Lab</span><b>${esc(s.lab_name)}</b></div>
      <div><span>Lines</span><b>${s.logs.length} (${keys.size} key evidence)</b></div>
    </div>
    <div class="scroll"><table class="left"><thead><tr><th>Secret</th><th>True value</th><th>Correlates</th><th>Why it leaks</th></tr></thead>
      <tbody>${secretRows}</tbody></table></div>
    <div class="bar">
      <label class="toggle"><input type="checkbox" id="show-bg" ${showBackground ? "checked" : ""}> Show ${hidden} background lines</label>
      <span class="meta"><mark class="secret">value</mark> secret · <mark class="correlate">detail</mark> correlate · amber ID = key evidence</span>
    </div>
    <div class="logs">${logs}</div>`;
  $("show-bg").onchange = (e) => { showBackground = e.target.checked; renderDetail(); };
}

function renderPipeline() {
  if (!build) {
    $("panel-pipeline").innerHTML = `<section class="card"><p class="empty">No builds yet. Run <code>uv run redaction data build</code>, then <code>uv run redaction site</code>.</p></section>`;
    return;
  }
  const m = build.manifest;
  renderSplits();
  $("build-meta").textContent = `build ${m.version} · renderer ${m.renderer} · ${m.built_at.replace("T", " ").slice(0, 16)} UTC`;
  renderStages(m);
  renderComposition();
  renderKinds(m);
  renderIssues(m);
  renderList();
}

/* ---------- Runs ---------- */

function renderRuns() {
  $("open-inspect").hidden = !SITE.inspect_viewer;
  $("runs-meta").textContent = SITE.inspect_viewer
    ? "Transcripts for every sample are in Inspect View."
    : "No Inspect logs bundled.";
  if (!SITE.runs.length) {
    $("runs").innerHTML = `<section class="card"><p class="empty">No P1 runs yet. <code>uv run redaction p1 run --mock</code> runs offline; real runs need API keys.</p></section>`;
    return;
  }
  $("runs").innerHTML = SITE.runs.map((r) => {
    const mock = (r.models || []).some((m) => m.startsWith("mockllm"));
    const checks = r.checks.map((c) =>
      `<div class="issue-row"><span>${esc(c.name)} <span class="meta">${esc(c.detail)}</span></span>
       <span><span class="pill ${c.result === "pass" ? "pass" : c.result === "FAIL" ? "fail" : "undecided"}">${c.result === "FAIL" ? "fail" : esc(c.result)}</span></span></div>`).join("");
    const rows = r.summary.map((s) => `<tr><td>${POLICY[s.policy] || esc(s.policy)}</td><td>${s.samples}</td>
      <td>${s.persistence ? f2(s.persistence.estimate) : "n/a"}</td><td>${s.leakage_mean ? f2(s.leakage_mean.estimate) : "n/a"}</td>
      <td>${f2(s.auroc_unedited)}</td><td>${f2(s.auroc_edited)}</td><td>${f2(s.evidence_loss)}</td></tr>`).join("");
    return `<section class="card">
      <h2>${esc(r.name)}${mock ? " · mock model" : ""}</h2>
      ${checks}
      <div class="scroll" style="margin-top:12px"><table><thead><tr><th>Policy</th><th>n</th><th>Persistence</th><th>Leakage</th><th>AUROC unedited</th><th>AUROC edited</th><th>Evidence loss</th></tr></thead>
      <tbody>${rows}</tbody></table></div></section>`;
  }).join("");
}

/* ---------- Boot ---------- */

$("tab-pipeline").onclick = () => setTab("pipeline");
$("tab-runs").onclick = () => setTab("runs");
$("f-label").onchange = renderList;
$("f-type").onchange = renderList;

fetch("data/site.json")
  .then((r) => { if (!r.ok) throw new Error(`site.json: HTTP ${r.status}`); return r.json(); })
  .then((site) => {
    SITE = site;
    build = SITE.builds.find((b) => b.manifest.split === "dev") || SITE.builds[0] || null;
    renderPipeline();
    renderRuns();
    setTab(location.hash === "#runs" ? "runs" : "pipeline");
  })
  .catch((err) => {
    document.querySelector("main").innerHTML = `<section class="card"><p class="empty">Could not load data/site.json (${esc(err.message)}). Rebuild with <code>uv run redaction site</code>.</p></section>`;
  });
