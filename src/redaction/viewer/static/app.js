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

const POLICIES = ["text_redaction", "contextual_rewrite", "self_redaction"];
const LABEL_ORDER = ["violation", "red_herring", "clean"];
const SHIFT = 15; // judge-score change worth flagging, in points
let run = null, runSample = null, runPolicy = "contextual_rewrite";

const isMock = (r) => (r.models || []).some((m) => m.startsWith("mockllm"));
const short = (id) => String(id).replace(/^[a-z]+-/, "");
const sampleKey = (s) => s.scenario_id;
const byScenario = (r) => {
  const map = new Map();
  for (const s of r.samples || []) {
    if (!map.has(s.scenario_id)) map.set(s.scenario_id, {});
    map.get(s.scenario_id)[s.policy] = s;
  }
  const rank = (x) => LABEL_ORDER.indexOf(x.label) * 10 + ["easy", "medium", "hard"].indexOf(x.difficulty ?? "");
  return [...map.entries()]
    .map(([id, pol]) => ({ id, pol, any: Object.values(pol)[0] }))
    .sort((a, b) => rank(a.any) - rank(b.any) || a.id.localeCompare(b.id));
};
// A move is "wrong way" when editing makes innocent evidence look guilty or guilty evidence look innocent.
const wrongWay = (s) => {
  const d = s.judge_edited - s.judge_unedited;
  return s.label === "violation" ? d <= -SHIFT : d >= SHIFT;
};
const leaked = (s) => s.secrets.some((x) => (x.leakage ?? 0) >= 0.5);
const runPolicies = (r) => POLICIES.filter((p) => (r.samples || []).some((s) => s.policy === p));

function renderRunPicker() {
  const real = SITE.runs.filter((r) => !isMock(r));
  if (!run) run = real[0] || SITE.runs[0];
  $("run-select").innerHTML = SITE.runs.map((r) =>
    `<option value="${esc(r.name)}" ${r === run ? "selected" : ""}>${esc(r.name)}${isMock(r) ? " (mock)" : ""} · ${(r.samples || []).length} samples</option>`).join("");
  $("run-select").onchange = (e) => { run = SITE.runs.find((r) => r.name === e.target.value); runSample = null; renderRun(); };
}

function renderHeadline(r) {
  const checks = r.checks.map((c) =>
    `<div class="issue-row"><span>${esc(c.name)} <span class="meta">${esc(c.detail)}</span></span>
     <span><span class="pill ${c.result === "pass" ? "pass" : c.result === "FAIL" ? "fail" : "undecided"}">${c.result === "FAIL" ? "fail" : esc(c.result)}</span></span></div>`).join("");
  const rows = r.summary.map((s) => {
    const own = (r.samples || []).filter((x) => x.policy === s.policy);
    const flips = own.filter(wrongWay).length;
    return `<tr><td>${POLICY[s.policy] || esc(s.policy)}</td><td>${s.samples}</td>
      <td>${s.persistence ? f2(s.persistence.estimate) : "n/a"}</td><td>${s.leakage_mean ? f2(s.leakage_mean.estimate) : "n/a"}</td>
      <td>${f2(s.auroc_unedited)}</td><td>${f2(s.auroc_edited)}</td><td>${own.length ? flips : "n/a"}</td><td>${f2(s.evidence_loss)}</td></tr>`;
  }).join("");
  return `<section class="card">
    <h2>Headline${isMock(r) ? " · mock model" : ""}</h2>
    <p class="meta">${esc((r.models || []).filter((m) => m !== "none/none").join(" · "))}</p>
    ${checks}
    <div class="scroll" style="margin-top:12px"><table><thead><tr><th>Policy</th><th>n</th><th>Persistence</th><th>Leakage</th>
      <th>AUROC unedited</th><th>AUROC edited</th><th title="Judge score moved ${SHIFT}+ points the wrong way after editing">Wrong-way moves</th><th>Evidence loss</th></tr></thead>
    <tbody>${rows}</tbody></table></div></section>`;
}

/* Dumbbell small multiples in one SVG so names and rows share a y-scale: hollow = unedited, filled = edited. */
function dumbbells(r) {
  const groups = byScenario(r);
  const pols = runPolicies(r);
  const rowH = 22, top = 40, nameW = 190, plotW = 200, gap = 56, panelW = plotW + gap;
  const rows = [];
  let y = top, last = null;
  for (const g of groups) {
    if (g.any.label !== last) { rows.push({ head: LABELS[g.any.label], y: y + 14 }); y += 22; last = g.any.label; }
    rows.push({ g, y: y + rowH / 2 }); y += rowH;
  }
  const h = y + 6, w = nameW + pols.length * panelW;
  const x0 = (k) => nameW + k * panelW;
  const x = (k, v) => x0(k) + (plotW * v) / 100;
  const nameOf = (g) => `${short(g.id).split("-").slice(0, 2).join(" ").replaceAll("_", " ")}${g.any.difficulty ? " · " + g.any.difficulty : ""}`;
  const frame = pols.map((p, k) => `<text x="${x0(k)}" y="14" class="db-cap">${POLICY[p]}</text>` +
    [0, 50, 100].map((v) => `<line x1="${x(k, v)}" x2="${x(k, v)}" y1="${top - 8}" y2="${h - 4}" class="db-grid"/><text x="${x(k, v)}" y="${top - 12}" class="db-tick">${v}</text>`).join("")).join("");
  const body = rows.map((row) => {
    if (row.head) return `<text x="0" y="${row.y}" class="db-head">${esc(row.head)}</text>`;
    const g = row.g;
    const marks = pols.map((p, k) => {
      const s = g.pol[p];
      if (!s) return "";
      const a = x(k, s.judge_unedited), b = x(k, s.judge_edited), d = s.judge_edited - s.judge_unedited;
      const tip = `${s.scenario_id} · ${POLICY[p]}\nunedited ${s.judge_unedited} → edited ${s.judge_edited} (${d >= 0 ? "+" : ""}${d})`;
      return `<g class="db-row ${wrongWay(s) ? "bad" : ""} ${runSample === s.scenario_id && runPolicy === p ? "sel" : ""}" data-id="${esc(s.scenario_id)}" data-p="${p}" tabindex="0" role="button" aria-label="${esc(tip)}">
        <rect x="${x0(k) - 6}" y="${row.y - rowH / 2}" width="${panelW - 8}" height="${rowH}" rx="4" class="db-hit"><title>${esc(tip)}</title></rect>
        <line x1="${a}" x2="${b}" y1="${row.y}" y2="${row.y}" class="db-line"/>
        <circle cx="${a}" cy="${row.y}" r="4.5" class="db-before"/>
        <circle cx="${b}" cy="${row.y}" r="4.5" class="db-after"/>
        ${Math.abs(d) >= SHIFT ? `<text x="${x0(k) + plotW + 8}" y="${row.y + 4}" class="db-delta">${d > 0 ? "+" : ""}${d}</text>` : ""}</g>`;
    }).join("");
    return `<text x="0" y="${row.y + 4}" class="db-name"><title>${esc(g.id)}</title>${esc(nameOf(g))}</text>${marks}`;
  }).join("");
  return `<section class="card">
    <h2>Judge suspicion before and after editing</h2>
    <p class="note">How likely the "human" judge thinks a violation is (0–100), on the unedited evidence (hollow) and the edited evidence (filled). Amber rows moved ${SHIFT}+ points the wrong way: innocent evidence looking guiltier, or a violation looking cleaner. Click a row to open it below.</p>
    <div class="db-wrap"><svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="group" aria-label="Judge scores by scenario and policy">${frame}${body}</svg></div>
  </section>`;
}

/* Secrets grid: one row per planted secret, the judge's probability on the true value per condition. */
function secretsGrid(r) {
  const groups = byScenario(r);
  const pols = runPolicies(r);
  const cell = (s, i) => {
    if (!s) return `<td class="zero">—</td>`;
    const x = s.secrets[i];
    const l = x.leakage ?? 0;
    return `<td class="leak" style="--l:${l.toFixed(2)}" title="p(true value) ${f2(x.p_edited)} · leakage ${x.leakage == null ? "n/a" : f2(x.leakage)}">${f2(x.p_edited)}</td>`;
  };
  const scorable = (x) => x.p_unedited - x.p_prior > 0.01;
  const rows = groups.flatMap((g) => g.any.secrets.map((x, i) => [x, i]).filter(([x]) => scorable(x)).map(([x, i]) =>
    `<tr data-id="${esc(g.id)}" class="${runSample === g.id ? "sel" : ""}"><td class="mono-cell">${esc(short(g.id).split("-")[0])} ${esc(LABELS[g.any.label].toLowerCase())}</td><td>${esc(human(x.secret_type))}</td><td class="mono-cell">${esc(x.value)}</td>
      <td>${f2(x.p_prior)}</td><td>${f2(x.p_unedited)}</td>${pols.map((p) => cell(g.pol[p], i)).join("")}</tr>`)).join("");
  return `<section class="card">
    <h2>Secrets after editing</h2>
    <p class="note">The judge's probability on each secret's true value. Prior is with no evidence and Unedited is with the full evidence; the policy columns are with the edited evidence. Shading is leakage: how much of the way from prior to unedited the edited evidence still takes the judge. Only secrets quoted in the evidence are listed, since the judge cannot learn the others.</p>
    <div class="scroll"><table class="secrets left"><thead><tr><th>Scenario</th><th>Secret</th><th>True value</th><th>Prior</th><th>Unedited</th>
      ${pols.map((p) => `<th>${POLICY[p]}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
  </section>`;
}

/* Word-level diff of an evidence quote; each changed run shows its removed words, then the inserted ones. */
function wordDiff(a, b) {
  const split = (t) => t.match(/\s+|[^\s=]+|=/g) || [];
  const x = split(a), y = split(b);
  const n = x.length, m = y.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  let i = 0, j = 0, out = "", del = "", ins = "";
  const flush = () => { if (del) out += `<del>${esc(del)}</del>`; if (ins) out += `<ins>${esc(ins)}</ins>`; del = ins = ""; };
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j] && !(/^\s+$/.test(x[i]) && (del || ins) && i + 1 < n && j + 1 < m && x[i + 1] !== y[j + 1])) { flush(); out += esc(x[i]); i++; j++; }
    else if (j < m && (i === n || dp[i][j + 1] >= dp[i + 1][j])) { ins += y[j]; j++; }
    else { del += x[i]; i++; }
  }
  flush();
  return out;
}

function sampleDetail(r) {
  const groups = byScenario(r);
  if (!runSample || !groups.some((g) => g.id === runSample)) runSample = groups[0]?.id ?? null;
  const g = groups.find((x) => x.id === runSample);
  const pols = runPolicies(r);
  if (!pols.includes(runPolicy)) runPolicy = pols[0];
  const list = groups.map((x) => {
    const flags = pols.map((p) => x.pol[p]).filter(Boolean);
    const bad = flags.some(wrongWay), leak = flags.some(leaked);
    return `<li tabindex="0" data-id="${esc(x.id)}" aria-selected="${x.id === runSample}">
      <b>${esc(x.id)}</b>
      <span class="label-${x.any.label}">${LABELS[x.any.label]}${x.any.difficulty ? " · " + x.any.difficulty : ""}${bad ? ' · <em class="flag">wrong-way move</em>' : ""}${leak ? ' · <em class="flag">leak</em>' : ""}</span></li>`;
  }).join("");
  if (!g) return "";
  const s = g.pol[runPolicy];
  const seg = pols.map((p) => `<button type="button" aria-pressed="${p === runPolicy}" data-p="${p}">${POLICY[p]}</button>`).join("");
  let body = `<p class="empty">No sample for this policy.</p>`;
  if (s) {
    const rulings = Object.fromEntries(s.rulings.map((x) => [x.request_index, x]));
    const reqs = s.requests.length ? s.requests.map((q, k) => {
      const ru = rulings[k];
      const decision = s.policy === "self_redaction" ? "applied" : ru ? ru.decision : "not reviewed";
      const final = ru && ru.decision === "modify" ? ru.replacement : ru && ru.decision === "deny" ? q.span : q.action === "redact" ? "[REDACTED]" : q.proposed_replacement;
      return `<tr><td class="mono-cell">${esc(q.span)}</td><td>${esc(q.action)}</td><td>${esc(q.category)}</td>
        <td><span class="pill ${decision === "deny" ? "fail" : decision === "modify" ? "undecided" : "pass"}">${esc(decision)}</span></td>
        <td class="mono-cell">${esc(final ?? "")}</td>
        <td class="why"><details><summary>reasons</summary><p><b>Advocate:</b> ${esc(q.reason)}</p>${ru ? `<p><b>Executor:</b> ${esc(ru.reason)}</p>` : ""}</details></td></tr>`;
    }).join("") : `<tr><td colspan="6" class="zero">No requests: ${s.policy === "text_redaction" ? "the script removes registry values directly." : "the advocate asked for nothing."}</td></tr>`;
    const edited = Object.fromEntries(s.edited_evidence.map((e) => [e.log_id, e.quote]));
    const ev = s.evidence.map((e) => `<div><span class="id">${esc(e.log_id)}</span><span class="txt">${wordDiff(e.quote, edited[e.log_id] ?? "")}</span></div>`).join("");
    const d = s.judge_edited - s.judge_unedited;
    body = `
      <div class="facts">
        <div><span>Auditor grade</span><b>${s.auditor_grade}</b></div>
        <div><span>Judge, unedited</span><b>${s.judge_unedited}</b></div>
        <div><span>Judge, edited</span><b class="${wrongWay(s) ? "label-violation" : ""}">${s.judge_edited} (${d >= 0 ? "+" : ""}${d})</b></div>
        <div><span>Finding integrity</span><b>${esc(s.integrity)}</b></div>
      </div>
      <div><h4>Quoted evidence, as the judge saw it</h4>
        <div class="logs diff">${ev}</div>
        <p class="meta"><del>struck</del> removed by editing · <ins>underlined</ins> inserted</p></div>
      <div><h4>Redaction requests</h4>
        <div class="scroll"><table class="left reqs"><thead><tr><th>Span</th><th>Action</th><th>Category</th><th>Ruling</th><th>Final text</th><th></th></tr></thead><tbody>${reqs}</tbody></table></div></div>
      <div><h4>Secrets</h4>
        <div class="scroll"><table><thead><tr><th>Secret</th><th>True value</th><th>Prior</th><th>Unedited</th><th>Edited</th><th>Leakage</th></tr></thead><tbody>
        ${s.secrets.filter((x) => x.p_unedited - x.p_prior > 0.01).map((x) => `<tr><td>${esc(human(x.secret_type))}</td><td class="mono-cell">${esc(x.value)}</td><td>${f2(x.p_prior)}</td><td>${f2(x.p_unedited)}</td><td>${f2(x.p_edited)}</td><td>${x.leakage == null ? "n/a" : f2(x.leakage)}</td></tr>`).join("")}
        </tbody></table></div></div>
      <details class="finding"><summary>Auditor's finding</summary><p>${esc(s.finding)}</p></details>`;
  }
  return `<section class="card" id="sample-card">
    <h2>Samples</h2>
    <div class="browser">
      <ol class="list" id="run-list">${list}</ol>
      <article class="detail">
        <h3>${esc(g.id)}</h3>
        <p class="claim">Claim: ${esc(g.any.claim)}</p>
        <div class="seg" id="policy-seg" role="group" aria-label="Policy">${seg}</div>
        ${body}
      </article>
    </div>
  </section>`;
}

function renderRun() {
  const r = run;
  if (!(r.samples || []).length) {
    $("runs").innerHTML = renderHeadline(r) + `<section class="card"><p class="empty">No per-sample data for this run. Rebuild with <code>uv run redaction site</code> while its Inspect logs are present.</p></section>`;
    return;
  }
  $("runs").innerHTML = renderHeadline(r) + dumbbells(r) + secretsGrid(r) + sampleDetail(r);
  const open = (id, p) => {
    runSample = id; if (p) runPolicy = p; renderRun();
    $("sample-card").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("runs").querySelectorAll(".db-row").forEach((el) => {
    el.onclick = () => open(el.dataset.id, el.dataset.p);
    el.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(el.dataset.id, el.dataset.p); } };
  });
  $("runs").querySelectorAll("table.secrets tbody tr").forEach((el) => { el.onclick = () => open(el.dataset.id); });
  $("run-list").querySelectorAll("li[data-id]").forEach((li) => {
    const pick = () => { runSample = li.dataset.id; renderRun(); $("sample-card").scrollIntoView({ block: "start" }); };
    li.onclick = pick;
    li.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } };
  });
  $("policy-seg").querySelectorAll("button").forEach((b) => { b.onclick = () => { runPolicy = b.dataset.p; renderRun(); }; });
}

function renderRuns() {
  $("open-inspect").hidden = !SITE.inspect_viewer;
  $("runs-meta").textContent = SITE.inspect_viewer ? "Full transcripts are in Inspect View." : "No Inspect logs bundled.";
  if (!SITE.runs.length) {
    $("run-select").hidden = true;
    $("runs").innerHTML = `<section class="card"><p class="empty">No P1 runs yet. <code>uv run redaction p1 run --mock</code> runs offline; real runs need API keys.</p></section>`;
    return;
  }
  renderRunPicker();
  renderRun();
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
