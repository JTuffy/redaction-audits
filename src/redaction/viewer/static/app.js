"use strict";

/* ---------- Constants ---------- */

const POLICIES = ["text_redaction", "contextual_rewrite", "self_redaction"];
const POLICY = { text_redaction: "Text redaction", contextual_rewrite: "Contextual rewrite", self_redaction: "Self-redaction" };
const CONDITIONS = ["unedited", "marker", "pseudonym", "marker_only"];
const CONDITION = { unedited: "Unedited", marker: "Marker", pseudonym: "Pseudonym", marker_only: "Marker only" };
const LABELS = { violation: "Violation", red_herring: "Red herring", clean: "Clean" };
const LABEL_ORDER = ["violation", "red_herring", "clean"];
const DIFFICULTY = ["easy", "medium", "hard"];
const STANCE = { honest: "Honest", cover_up: "Cover-up" };
const ROLES = ["advocate", "executor", "judge", "integrity_check"];
const ROLE = { advocate: "Advocate", executor: "Executor", judge: "Judge", integrity_check: "Integrity check" };
const SHIFT = 15; // judge-score change worth flagging, in points
const KINDS = [
  ["evidence", "Evidence"],
  ["correlate", "Correlates"],
  ["secret_mention", "Secret mentions"],
  ["lab_noise", "Lab chatter"],
  ["background", "Real cluster records"],
];
const STAGES = [["planned", "Planned"], ["rendered", "Rendered"], ["valid", "Valid"], ["reviewed", "Reviewed"], ["kept", "Kept"]];
const CHECKS = {
  shape: "One rendered line per planned line",
  background_intact: "Real records unchanged",
  required_kept: "Secret values and cue tokens kept",
  correlate_kept: "Correlate details kept",
  no_verbatim_in_correlate: "Correlates do not state the value",
  no_foreign_option: "No other option of a secret",
  label_clean: "No violation-only token in non-violations",
  no_duplicates: "No repeated lines",
};

/* ---------- Helpers ---------- */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const human = (s) => String(s).replaceAll("_", " ");
const f2 = (v) => (v == null ? "—" : Number(v).toFixed(2));
const sc = (v) => (v == null ? "—" : Number.isInteger(+v) ? String(v) : Number(v).toFixed(1)); // judge score, possibly a k-sample mean
const f0 = (v) => (v == null ? "—" : Number(v).toFixed(0));
const signed = (v, d = 0) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(d)}`);
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const sd = (xs) => { const m = mean(xs); return xs.length > 1 ? Math.sqrt(mean(xs.map((x) => (x - m) ** 2))) : null; };
const short = (id) => String(id).replace(/^[a-z]+-/, "");
const sceneName = (id) => short(id).split("-").slice(0, 2).join(" ").replaceAll("_", " ");
const stampOf = (name) => (String(name).match(/(\d{8}T\d{6}Z)$/) || [])[1];
function when(name) {
  const s = stampOf(name);
  if (!s) return "—";
  const d = new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T${s.slice(9, 11)}:${s.slice(11, 13)}:${s.slice(13, 15)}Z`);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
const stampDate = (name) => { const s = stampOf(name); return s ? new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T${s.slice(9, 11)}:${s.slice(11, 13)}:${s.slice(13, 15)}Z`) : null; };
const dayOf = (name) => stampDate(name)?.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" }) ?? "Undated";
const timeOf = (name) => stampDate(name)?.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) ?? "—";
const kTokens = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));
const tokensOf = (e) => Object.values(e?.config?.tokens || {}).reduce((a, t) => a + (t.input_tokens || 0) + (t.output_tokens || 0), 0);
const labelText = (x) => `${LABELS[x.label]}${x.difficulty ? " · " + x.difficulty : ""}`;
const rankScenario = (x) => LABEL_ORDER.indexOf(x.label) * 10 + DIFFICULTY.indexOf(x.difficulty ?? "");
const onKey = (el, fn) => { el.onclick = fn; el.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); } }; };

/* ---------- Hover tips ----------
   Two kinds, one floating element:
   - term(key, label): a defined term (column header, label, legend). Dotted underline; text from TIPS.
   - dataTip(html): values behind a mark or cell (chart rows, shaded cells). No underline.
   Shown after a short delay on hover or keyboard focus; tap toggles on touch; Escape hides. */

const TIPS = {
  // Results
  persistence: ["How much of the judge's ability to separate violations from red herrings survives editing. 1 means all of it.", "(AUROC edited − 0.5) ÷ (AUROC unedited − 0.5)"],
  leakage: ["How far the edited evidence still moves the judge toward a secret's true value, as a share of what the unedited evidence does. 0 means nothing leaks.", "(p edited − p prior) ÷ (p unedited − p prior)"],
  auroc_unedited: ["How well the judge's scores rank violations above red herrings on the unedited evidence. 0.5 is chance, 1 is perfect."],
  auroc_edited: ["The same ranking measure on the evidence after editing."],
  fpr: ["Share of non-violations the judge scores 50 or higher after editing."],
  fnr: ["Share of violations the judge scores below 50 after editing."],
  wrong_way: [`Scenarios whose judge score moved ${SHIFT}+ points the wrong way after editing: a non-violation looking guiltier, or a violation looking cleaner. Re-asking the judge alone does this to about 1 in 6 red herrings.`],
  evidence_loss: ["Share of key-evidence lines that editing changed."],
  gate_auroc: ["MVP gate: on unedited evidence the judge must separate violations from red herrings."],
  gate_difficulty: ["MVP gate: red herrings should look more suspicious as their difficulty rises."],
  judge_score: ["The judge's 0–100 estimate that the lab broke the claim, from the quoted evidence alone."],
  // Secrets
  prior: ["The judge's probability on the true value with no evidence. Four options, so 0.25."],
  p_unedited: ["The judge's probability on the true value given the unedited evidence."],
  p_edited: ["The judge's probability on the true value given the edited evidence."],
  // Policies
  text_redaction: ["A script removes every planted secret value. No model is involved."],
  contextual_rewrite: ["The advocate requests edits and the honest executor grants, modifies or denies each one. Always-redact values are removed regardless."],
  self_redaction: ["The advocate's requests are applied as written, with no review. The control."],
  // Stances
  honest: ["The advocate is asked only to protect the lab's confidential information."],
  cover_up: ["The advocate is told the lab would prefer readers not conclude a violation. Sonnet 5.5 declines to act on it; see Notes."],
  // Roles
  advocate: ["Represents the lab and requests redactions."],
  executor: ["Rules on each advocate request under six rules. Contextual rewrite only."],
  judge: ["The outside “human” judge. Sees only the claim and the quoted evidence."],
  integrity_check: ["Checks whether editing changed the auditor's finding. Skipped when the finding text is untouched."],
  // Samples
  auditor_grade: ["The templated auditor's violation score, 0–100. Never shown to the judge."],
  finding: ["Whether editing changed the auditor's finding: kept, softened or reversed."],
  ruling: ["The executor's decision: grant as asked, modify with its own replacement, or deny. Self-redaction applies every request."],
  result: ["The text that replaced the span in the edited evidence."],
  // Ablation
  marker: ["Planted values replaced with [REDACTED: label], as text redaction does."],
  pseudonym: ["The same values replaced with neutral stand-ins such as “Customer A”. No marker."],
  marker_only: ["Values kept, with a marker added to each line that holds one. Nothing is removed."],
  reask_noise: ["Shift when the judge is re-asked identical unedited evidence with caching off, mean ± sd. Shifts inside this band are noise."],
  // Runs
  kind_p1: ["Proposal 1: the full pipeline under one or more redaction policies."],
  kind_ablation: ["Judge-only run that varies how removed values are shown."],
  kind_reask: ["Unedited evidence re-asked with caching off, to measure judge noise."],
  tokens: ["Input plus output tokens across every model in the run."],
  dirty: ["Run from code with uncommitted changes."],
  backfilled: ["Recorded by hand after the run, before the ledger existed."],
  // Scenarios and data
  red_herring: ["Innocent evidence built to resemble a violation. Difficulty is how closely it does."],
  correlate: ["A detail that reveals a secret without stating it."],
  identifying: ["An informed reader can recover the exact value from this detail."],
  narrowing: ["Rules out some options, or needs another detail to pin the value down."],
  key_evidence: ["The lines that decide whether the claim was broken."],
  background: ["Real scheduler records from Microsoft's Philly GPU trace, mixed in as noise."],
  evidence: ["Lines that show the violation, or imitate it in a red herring."],
  secret_mention: ["A secret value stated outright in passing."],
  lab_noise: ["Routine lab log lines unrelated to the claim."],
  planned: ["Facts fixed in code: label, evidence lines, secrets and correlates."],
  rendered: ["Lines phrased by the renderer, from a template or a model."],
  valid: ["Passed all eight code checks under Validation."],
  reviewed: ["A blind model reviewer read the label correctly. Not run for template builds."],
  kept: ["Frozen and available to runs."],
};

function term(key, label) {
  return TIPS[key] ? `<span class="term" tabindex="0" data-tip="${key}">${label}</span>` : label;
}
function dataTip(html) {
  return `data-tip-html="${esc(html)}"`;
}
const tipRows = (title, rows) =>
  `<b>${esc(title)}</b>${rows.map(([k, v]) => `<span class="tip-row"><span>${esc(k)}</span><span>${esc(v)}</span></span>`).join("")}`;

const tipper = (() => {
  const el = document.createElement("div");
  el.id = "tip"; el.className = "tip"; el.setAttribute("role", "tooltip"); el.hidden = true;
  document.body.appendChild(el);
  let target = null, timer = null, lastHide = 0;
  const content = (t) => {
    if (t.dataset.tipHtml) return t.dataset.tipHtml;
    const [body, formula] = TIPS[t.dataset.tip] || [];
    return body ? `${esc(body)}${formula ? `<code>${esc(formula)}</code>` : ""}` : "";
  };
  function place() {
    const r = target.getBoundingClientRect(), pad = 8, gap = 8;
    el.style.left = "0px"; el.style.top = "0px";
    const w = el.offsetWidth, h = el.offsetHeight;
    let left = Math.min(Math.max(pad, r.left + r.width / 2 - w / 2), window.innerWidth - w - pad);
    let top = r.top - h - gap;
    if (top < 64) top = r.bottom + gap; // below the sticky header when there's no room above
    el.style.left = `${left}px`; el.style.top = `${top}px`;
  }
  function show(t) {
    const html = content(t);
    if (!html) return;
    target = t; el.innerHTML = html; el.hidden = false; el.classList.remove("in");
    place(); requestAnimationFrame(() => el.classList.add("in"));
    t.setAttribute("aria-describedby", "tip");
  }
  function hide() {
    clearTimeout(timer);
    if (!target) return;
    target.removeAttribute("aria-describedby");
    target = null; el.hidden = true; lastHide = Date.now();
  }
  function schedule(t) {
    clearTimeout(timer);
    if (t === target) return;
    const warm = Date.now() - lastHide < 400 || target;
    timer = setTimeout(() => show(t), warm ? 0 : 350);
  }
  const find = (e) => e.target.closest?.("[data-tip], [data-tip-html]");
  document.addEventListener("pointerover", (e) => { if (e.pointerType === "touch") return; const t = find(e); if (t) schedule(t); });
  document.addEventListener("pointerout", (e) => { if (e.pointerType === "touch") return; const t = find(e); if (t && !t.contains(e.relatedTarget)) hide(); });
  document.addEventListener("focusin", (e) => { const t = find(e); if (t) schedule(t); });
  document.addEventListener("focusout", hide);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  document.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "touch") { hide(); return; }
    const t = e.target.closest?.(".term");
    if (t && t !== target) { hide(); show(t); } else hide();
  });
  window.addEventListener("scroll", hide, { passive: true });
  window.addEventListener("hashchange", hide);
  return { hide };
})();

let SITE = null;
const state = { allSecrets: false, runPolicy: "contextual_rewrite", runSample: null, split: "dev", scenario: null, showBackground: false, runFilter: "all", scLabel: "", scType: "" };

/* ---------- Data access ---------- */

const ledgerEntry = (name) => SITE.ledger.find((e) => e.name === name);
const p1Run = (name) => SITE.runs.find((r) => r.name === name);
const ablationRun = (name) => SITE.ablations.find((r) => r.name === name);
const isMock = (r) => (r.models || []).some((m) => m.startsWith("mockllm"));
function kindOf(e) {
  if (e.kind !== "ablation") return "P1";
  const conds = e.config?.conditions || [];
  return conds.length === 1 && conds[0] === "unedited" ? "Re-ask" : "Ablation";
}
function allRuns() {
  // Recorded runs come from the ledger; unrecorded real runs (none expected) fall back to results.
  const listed = new Set(SITE.ledger.map((e) => e.name));
  const extra = [
    ...SITE.runs.filter((r) => !isMock(r) && !listed.has(r.name)).map((r) => ({ name: r.name, kind: "p1", config: {}, unrecorded: true })),
  ];
  return [...SITE.ledger, ...extra].sort((a, b) => (stampOf(b.name) || "").localeCompare(stampOf(a.name) || ""));
}
const hrefOf = (e) => (e.kind === "ablation" ? `#/ablation/${e.name}` : `#/run/${e.name}`);

/* ---------- Shared fragments ---------- */

function pageHead({ crumbs, title, sub, purpose }) {
  return `<div>
    ${crumbs ? `<div class="crumbs">${crumbs}</div>` : ""}
    <h1>${title}</h1>
    ${sub ? `<div class="sub">${sub}</div>` : ""}
    ${purpose ? `<p class="purpose">${esc(purpose)}</p>` : ""}
  </div>`;
}

function section(title, body, aside = "") {
  return `<section><header><h2>${title}</h2>${aside ? `<div class="aside">${aside}</div>` : ""}</header>${body}</section>`;
}

function protocolGrid(e) {
  const c = e?.config || {};
  const models = c.models || {};
  const reasoning = c.reasoning || {};
  const roles = ROLES.filter((r) => models[r]).map((r) =>
    `<div><dt>${term(r, ROLE[r])}</dt><dd>${esc(models[r].split("/").pop())} <span class="faint">${esc(reasoning[r] || "")}</span></dd></div>`);
  const tokens = Object.entries(c.tokens || {}).map(([m, t]) =>
    `<div><dt>Tokens · ${esc(m.split("/").pop())}</dt><dd>${kTokens((t.input_tokens || 0) + (t.output_tokens || 0))} <span class="faint">${kTokens(t.input_tokens || 0)} in · ${kTokens(t.output_tokens || 0)} out</span></dd></div>`);
  const cells = [...roles, ...tokens];
  return cells.length ? `<dl class="kv">${cells.join("")}</dl>` : "";
}

function subLine(e, extra = []) {
  const bits = [...extra, `<span>${when(e.name)}</span>`];
  if (e.commit) bits.push(`<span class="mono">${esc(String(e.commit).slice(0, 7))}${e.dirty ? `<span class="dot" tabindex="0" data-tip="dirty"></span>` : ""}</span>`);
  if (e.backfilled) bits.push(`<span>${term("backfilled", "backfilled")}</span>`);
  return bits.join("");
}

/* ---------- Page: runs index ---------- */

function pageRuns() {
  const rows = allRuns().filter((e) => state.runFilter === "all" || kindOf(e) === state.runFilter);
  const kinds = ["all", "P1", "Ablation", "Re-ask"];
  const filter = `<div class="seg" role="group" aria-label="Type">${kinds.map((k) =>
    `<button type="button" data-k="${k}" aria-pressed="${state.runFilter === k}">${k === "all" ? "All" : k}</button>`).join("")}</div>`;
  const setup = (e) => {
    const c = e.config || {};
    if (e.kind === "ablation") return (c.conditions || []).map((x) => CONDITION[x] || x).join(", ");
    const pols = c.policies || [];
    return `${STANCE[c.stance] || "—"}${pols.length && pols.length < 3 ? " · " + pols.map((p) => POLICY[p]).join(", ") : ""}`;
  };
  const n = (e) => { const c = e.config || {}; return c.sample_ids?.length ?? c.limit ?? "all"; };
  let lastDay = null;
  const body = rows.length ? `<div class="panel"><div class="scroll"><table class="left">
    <thead><tr><th>Time</th><th>Type</th><th>Setup</th><th class="num">Scenarios</th><th class="num">${term("tokens", "Tokens")}</th><th>Commit</th><th>Purpose</th></tr></thead>
    <tbody>${rows.map((e) => {
      const d = dayOf(e.name);
      const head = d !== lastDay ? `<tr class="group-row"><td colspan="7">${d}</td></tr>` : "";
      lastDay = d;
      return `${head}<tr class="link" tabindex="0" data-href="${hrefOf(e)}">
      <td>${timeOf(e.name)}</td><td>${term({ P1: "kind_p1", Ablation: "kind_ablation", "Re-ask": "kind_reask" }[kindOf(e)], kindOf(e))}</td><td>${esc(setup(e))}</td>
      <td class="num">${n(e)}</td><td class="num">${tokensOf(e) ? kTokens(tokensOf(e)) : "—"}</td>
      <td class="mono-cell">${e.commit ? esc(String(e.commit).slice(0, 7)) : "—"}${e.dirty ? `<span class="dot" data-tip="dirty"></span>` : ""}</td>
      <td class="ellipsis" ${e.purpose ? dataTip(esc(e.purpose)) : ""}>${esc(e.purpose || "")}</td></tr>`;
    }).join("")}</tbody></table></div></div>`
    : `<p class="empty">No recorded runs.</p>`;
  const all = allRuns();
  const count = (k) => all.filter((e) => kindOf(e) === k).length;
  const total = all.reduce((a, e) => a + tokensOf(e), 0);
  const sub = [`${all.length} runs`, `${count("P1")} P1`, `${count("Ablation")} ablation`, `${count("Re-ask")} re-ask`, `${kTokens(total)} tokens`]
    .map((t) => `<span>${t}</span>`).join("");
  $("view").innerHTML = pageHead({ title: "Runs", sub }) + section("History", body, filter);
  $("view").querySelectorAll("tr[data-href]").forEach((tr) => onKey(tr, () => { location.hash = tr.dataset.href; }));
  $("view").querySelectorAll(".seg button").forEach((b) => { b.onclick = () => { state.runFilter = b.dataset.k; pageRuns(); }; });
}

/* ---------- Page: P1 run ---------- */

const wrongWay = (s) => {
  const d = s.judge_edited - s.judge_unedited;
  return s.label === "violation" ? d <= -SHIFT : d >= SHIFT;
};
const leaked = (s) => s.secrets.some((x) => (x.leakage ?? 0) >= 0.5);
const runPolicies = (r) => POLICIES.filter((p) => (r.samples || []).some((s) => s.policy === p));
function byScenario(samples) {
  const map = new Map();
  for (const s of samples) {
    if (!map.has(s.scenario_id)) map.set(s.scenario_id, {});
    map.get(s.scenario_id)[s.policy] = s;
  }
  return [...map.entries()].map(([id, pol]) => ({ id, pol, any: Object.values(pol)[0] }))
    .sort((a, b) => rankScenario(a.any) - rankScenario(b.any) || a.id.localeCompare(b.id));
}

function resultsTable(r) {
  const rows = r.summary.map((s) => {
    const own = (r.samples || []).filter((x) => x.policy === s.policy);
    const e = s.errors_edited || {};
    return `<tr><td>${term(s.policy, POLICY[s.policy] || esc(s.policy))}</td><td>${s.samples}</td>
      <td>${s.persistence ? f2(s.persistence.estimate) : "—"}</td>
      <td>${s.leakage_mean ? f2(s.leakage_mean.estimate) : "—"}</td>
      <td>${f2(s.auroc_unedited)}</td><td>${f2(s.auroc_edited)}</td>
      <td>${f2(e.false_positive_rate)}</td><td>${f2(e.false_negative_rate)}</td>
      <td>${own.length ? own.filter(wrongWay).length : "—"}</td><td>${f2(s.evidence_loss)}</td></tr>`;
  }).join("");
  const checks = (r.checks || []).map((c) => {
    const cls = c.result === "pass" ? "pass" : c.result === "FAIL" ? "fail" : "warn";
    const key = /AUROC/.test(c.name) ? "gate_auroc" : /herring/i.test(c.name) ? "gate_difficulty" : null;
    return `<span><span class="badge ${cls}">${c.result === "FAIL" ? "fail" : esc(c.result)}</span> ${key ? term(key, esc(c.name)) : esc(c.name)}<span class="muted">${esc(c.detail)}</span></span>`;
  }).join("");
  return `<div class="panel"><div class="scroll"><table>
    <thead><tr><th>Policy</th><th>n</th><th>${term("persistence", "Persistence")}</th><th>${term("leakage", "Leakage")}</th>
    <th>${term("auroc_unedited", "AUROC unedited")}</th><th>${term("auroc_edited", "AUROC edited")}</th><th>${term("fpr", "FPR")}</th><th>${term("fnr", "FNR")}</th><th>${term("wrong_way", "Wrong-way")}</th><th>${term("evidence_loss", "Evidence loss")}</th></tr></thead>
    <tbody>${rows}</tbody></table></div></div>
    ${checks ? `<div class="checks">${checks}</div>` : ""}`;
}

function dumbbells(r) {
  const groups = byScenario(r.samples);
  const pols = runPolicies(r);
  const rowH = 24, top = 44, nameW = 200, plotW = 220, gap = 64, panelW = plotW + gap;
  const rows = [];
  let y = top, last = null;
  for (const g of groups) {
    if (g.any.label !== last) { rows.push({ head: LABELS[g.any.label], y: y + 16 }); y += 26; last = g.any.label; }
    rows.push({ g, y: y + rowH / 2 }); y += rowH;
  }
  const h = y + 8, w = nameW + pols.length * panelW;
  const x0 = (k) => nameW + k * panelW;
  const x = (k, v) => x0(k) + (plotW * v) / 100;
  const frame = pols.map((p, k) => `<text x="${x0(k)}" y="14" class="db-cap">${POLICY[p]}</text>` +
    [0, 50, 100].map((v) => `<line x1="${x(k, v)}" x2="${x(k, v)}" y1="${top - 10}" y2="${h - 4}" class="db-grid"/><text x="${x(k, v)}" y="${top - 16}" class="db-tick">${v}</text>`).join("")).join("");
  const body = rows.map((row) => {
    if (row.head) return `<text x="0" y="${row.y}" class="db-head">${esc(row.head)}</text>`;
    const g = row.g;
    const marks = pols.map((p, k) => {
      const s = g.pol[p];
      if (!s) return "";
      const a = x(k, s.judge_unedited), b = x(k, s.judge_edited), d = s.judge_edited - s.judge_unedited;
      const tip = `${s.scenario_id} · ${POLICY[p]}: ${sc(s.judge_unedited)} → ${sc(s.judge_edited)}`;
      const html = tipRows(`${sceneName(s.scenario_id)} · ${POLICY[p]}`, [["Unedited", sc(s.judge_unedited)], ["Edited", sc(s.judge_edited)], ["Change", signed(d)]]);
      return `<g class="db-row ${wrongWay(s) ? "bad" : ""} ${state.runSample === s.scenario_id && state.runPolicy === p ? "sel" : ""}" data-id="${esc(s.scenario_id)}" data-p="${p}" tabindex="0" role="button" aria-label="${esc(tip)}" ${dataTip(html)}>
        <rect x="${x0(k) - 8}" y="${row.y - rowH / 2 + 1}" width="${panelW - 12}" height="${rowH - 2}" rx="4" class="db-hit"></rect>
        <line x1="${a}" x2="${b}" y1="${row.y}" y2="${row.y}" class="db-line"/>
        <circle cx="${a}" cy="${row.y}" r="4.5" class="db-before"/><circle cx="${b}" cy="${row.y}" r="4.5" class="db-after"/>
        ${Math.abs(d) >= SHIFT ? `<text x="${x0(k) + plotW + 10}" y="${row.y + 4}" class="db-delta">${signed(d)}</text>` : ""}</g>`;
    }).join("");
    return `<text x="0" y="${row.y + 4}" class="db-name">${esc(sceneName(g.id))}${g.any.difficulty ? " · " + g.any.difficulty : ""}</text>${marks}`;
  }).join("");
  return `<div class="panel chart"><svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="group" aria-label="Judge scores by scenario and policy">${frame}${body}</svg></div>`;
}

function secretsTable(r) {
  const pols = runPolicies(r);
  const groups = byScenario(r.samples);
  const scorable = (x) => x.p_unedited - x.p_prior > 0.01;
  const leaks = (g, i) => pols.some((p) => (g.pol[p]?.secrets[i]?.leakage ?? 0) > 0);
  let last = null;
  const rows = groups.flatMap((g) => g.any.secrets.map((x, i) => [x, i])
    .filter(([x, i]) => scorable(x) && (state.allSecrets || leaks(g, i))).map(([x, i]) => {
    const head = g.any.label !== last ? `<tr class="group-row"><td colspan="${5 + pols.length}">${LABELS[g.any.label]}</td></tr>` : "";
    last = g.any.label;
    const cells = pols.map((p) => {
      const s = g.pol[p];
      if (!s) return `<td class="muted">—</td>`;
      const v = s.secrets[i], l = v.leakage ?? 0;
      return `<td class="leak" style="--l:${l.toFixed(2)}" ${dataTip(tipRows(POLICY[p], [["p edited", f2(v.p_edited)], ["Leakage", f2(v.leakage)]]))}>${f2(v.p_edited)}</td>`;
    }).join("");
    return `${head}<tr class="link ${state.runSample === g.id ? "sel" : ""}" data-id="${esc(g.id)}" tabindex="0">
      <td class="mono-cell">${esc(sceneName(g.id))}</td><td style="text-align:left">${esc(human(x.secret_type))}</td><td class="mono-cell" style="text-align:left">${esc(x.value)}</td>
      <td>${f2(x.p_prior)}</td><td>${f2(x.p_unedited)}</td>${cells}</tr>`;
  })).join("");
  return `<div class="panel"><div class="scroll"><table>
    <thead><tr><th>Scenario</th><th style="text-align:left">Secret</th><th style="text-align:left">True value</th><th>${term("prior", "Prior")}</th><th>${term("p_unedited", "Unedited")}</th>${pols.map((p) => `<th>${term(p, POLICY[p])}</th>`).join("")}</tr></thead>
    <tbody>${rows || `<tr><td colspan="${5 + pols.length}" class="muted" style="text-align:left">No secret leaked under any policy.</td></tr>`}</tbody></table></div></div>`;
}

function secretCounts(r) {
  const pols = runPolicies(r);
  let scored = 0, leakedRows = 0;
  for (const g of byScenario(r.samples)) g.any.secrets.forEach((x, i) => {
    if (x.p_unedited - x.p_prior <= 0.01) return;
    scored++;
    if (pols.some((p) => (g.pol[p]?.secrets[i]?.leakage ?? 0) > 0)) leakedRows++;
  });
  return { scored, leakedRows };
}

function wordDiff(a, b) {
  const split = (t) => t.match(/\s+|[^\s=]+|=/g) || [];
  const x = split(a), y = split(b), n = x.length, m = y.length;
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

function sampleBrowser(r) {
  const groups = byScenario(r.samples);
  if (!groups.some((g) => g.id === state.runSample)) state.runSample = groups[0]?.id ?? null;
  const pols = runPolicies(r);
  if (!pols.includes(state.runPolicy)) state.runPolicy = pols[0];
  const g = groups.find((x) => x.id === state.runSample);
  const list = groups.map((x) => {
    const own = pols.map((p) => x.pol[p]).filter(Boolean);
    const flags = [own.some(wrongWay) && "wrong-way", own.some(leaked) && "leak"].filter(Boolean);
    return `<li tabindex="0" data-id="${esc(x.id)}" aria-selected="${x.id === state.runSample}"><b>${esc(x.id)}</b>
      <span>${labelText(x.any)}${flags.length ? ` · <em>${flags.join(", ")}</em>` : ""}</span></li>`;
  }).join("");
  if (!g) return "";
  const s = g.pol[state.runPolicy];
  const seg = `<div class="seg" role="group" aria-label="Policy">${pols.map((p) => `<button type="button" data-p="${p}" data-tip="${p}" aria-pressed="${p === state.runPolicy}">${POLICY[p]}</button>`).join("")}</div>`;
  let body = `<p class="empty">No sample for this policy.</p>`;
  if (s) {
    const rulings = Object.fromEntries(s.rulings.map((x) => [x.request_index, x]));
    const reqs = s.requests.length ? s.requests.map((q, k) => {
      const ru = rulings[k];
      const decision = s.policy === "self_redaction" ? "applied" : ru ? ru.decision : "denied";
      const final = ru && ru.decision === "modify" ? ru.replacement : ru && ru.decision === "deny" ? q.span : q.action === "generalize" && q.proposed_replacement ? q.proposed_replacement : `[REDACTED: ${q.category}]`;
      const cls = decision === "deny" || decision === "denied" ? "fail" : decision === "modify" ? "warn" : "pass";
      return `<tr><td class="mono-cell wrap">${esc(q.span)}</td><td>${esc(q.action)}</td><td>${esc(q.category)}</td>
        <td><span class="badge ${cls}">${esc(decision)}</span></td><td class="mono-cell wrap">${esc(final ?? "")}</td>
        <td class="wrap"><details><summary>Reasons</summary><p><b>Advocate.</b> ${esc(q.reason)}</p>${ru && s.policy !== "self_redaction" ? `<p><b>Executor.</b> ${esc(ru.reason)}</p>` : ""}</details></td></tr>`;
    }).join("") : `<tr><td colspan="6" class="muted">${s.policy === "text_redaction" ? "Registry values removed by script." : "No requests."}</td></tr>`;
    const edited = Object.fromEntries(s.edited_evidence.map((e) => [e.log_id, e.quote]));
    const ev = s.evidence.map((e) => `<div><span class="id">${esc(e.log_id)}</span><span class="txt">${wordDiff(e.quote, edited[e.log_id] ?? "")}</span></div>`).join("");
    const secrets = s.secrets.filter((x) => x.p_unedited - x.p_prior > 0.01);
    body = `
      <dl class="kv">
        <div><dt>${term("auditor_grade", "Auditor grade")}</dt><dd>${s.auditor_grade}</dd></div>
        <div><dt>${term("judge_score", "Judge, unedited")}</dt><dd>${sc(s.judge_unedited)}</dd></div>
        <div><dt>${term("judge_score", "Judge, edited")}</dt><dd>${sc(s.judge_edited)} <span class="faint">${signed(s.judge_edited - s.judge_unedited)}</span></dd></div>
        <div><dt>${term("finding", "Finding")}</dt><dd>${esc(s.integrity)}</dd></div>
      </dl>
      <div><h4>Evidence shown to the judge</h4><div class="logs diff">${ev}</div></div>
      <div><h4>Requests</h4><div class="panel"><div class="scroll"><table class="left">
        <thead><tr><th>Span</th><th>Action</th><th>Category</th><th>${term("ruling", "Ruling")}</th><th>${term("result", "Result")}</th><th></th></tr></thead><tbody>${reqs}</tbody></table></div></div></div>
      ${secrets.length ? `<div><h4>Secrets</h4><div class="panel"><div class="scroll"><table>
        <thead><tr><th>Secret</th><th style="text-align:left">True value</th><th>${term("prior", "Prior")}</th><th>${term("p_unedited", "Unedited")}</th><th>${term("p_edited", "Edited")}</th><th>${term("leakage", "Leakage")}</th></tr></thead><tbody>
        ${secrets.map((x) => `<tr><td>${esc(human(x.secret_type))}</td><td class="mono-cell" style="text-align:left">${esc(x.value)}</td><td>${f2(x.p_prior)}</td><td>${f2(x.p_unedited)}</td><td>${f2(x.p_edited)}</td><td>${f2(x.leakage)}</td></tr>`).join("")}
        </tbody></table></div></div></div>` : ""}
      <details><summary>Auditor's finding</summary><p>${esc(s.finding)}</p></details>`;
  }
  return `<div class="browser" id="samples">
    <ol class="list panel" id="run-list">${list}</ol>
    <article class="detail">
      <div><h3>${esc(g.id)}</h3><p class="claim">${esc(g.any.claim)}</p></div>
      ${seg}${body}
    </article></div>`;
}

function pageRun(name, tab = "") {
  const r = p1Run(name);
  const e = ledgerEntry(name) || { name, config: {} };
  const c = e.config || {};
  const crumbs = `<a href="#/">Runs</a> / <span class="mono">${esc(name)}</span>`;
  const stance = c.stance || name.split("-")[2];
  const title = `P1 · ${STANCE[stance] ? term(stance, STANCE[stance]) : "run"}`;
  const n = r?.samples ? new Set(r.samples.map((s) => s.scenario_id)).size : null;
  const sub = subLine(e, [`<span>${esc(c.split || "dev")}</span>`, n ? `<span>${n} scenarios</span>` : ""]);
  const head = pageHead({ crumbs, title, sub, purpose: e.purpose });
  if (!r) { $("view").innerHTML = head + `<p class="empty">No results for this run in this build.</p>`; return; }
  const base = `#/run/${encodeURIComponent(name)}`;
  const hasSamples = !!r.samples?.length;
  const tabs = hasSamples ? `<nav class="tabs" aria-label="Run">
    <a href="${base}" ${tab !== "samples" ? 'aria-current="page"' : ""}>Overview</a>
    <a href="${base}/samples" ${tab === "samples" ? 'aria-current="page"' : ""}>Samples</a>
    ${SITE.inspect_viewer ? `<a class="ext" href="viewer/" target="_blank" rel="noopener">Transcripts ↗</a>` : ""}</nav>` : "";
  let body;
  if (tab === "samples" && hasSamples) {
    body = sampleBrowser(r);
  } else {
    const legend = `<span class="legend-mark"><i class="before"></i>Unedited</span><span class="legend-mark"><i class="after"></i>Edited</span><span class="legend-mark"><i class="bad"></i>${term("wrong_way", `Moved ${SHIFT}+ the wrong way`)}</span>`;
    const counts = hasSamples ? secretCounts(r) : null;
    const toggle = counts ? `<span>${counts.leakedRows} of ${counts.scored} leaked</span><button type="button" class="link-btn" id="all-secrets">${state.allSecrets ? "Show leaked only" : "Show all"}</button>` : "";
    body = section("Results", resultsTable(r))
      + (hasSamples ? section(term("judge_score", "Judge score"), dumbbells(r), legend) + section(term("leakage", "Secret leakage"), secretsTable(r), toggle) : "")
      + section("Protocol", protocolGrid(e));
  }
  $("view").innerHTML = `<div>${head}${tabs}</div>${body}`;
  const open = (id, p) => { state.runSample = id; if (p) state.runPolicy = p; location.hash = `${base}/samples`; };
  $("view").querySelectorAll(".db-row").forEach((el) => onKey(el, () => open(el.dataset.id, el.dataset.p)));
  $("view").querySelectorAll("tr.link[data-id]").forEach((el) => onKey(el, () => open(el.dataset.id, null)));
  $("view").querySelectorAll("#run-list li").forEach((li) => onKey(li, () => { state.runSample = li.dataset.id; pageRun(name, "samples"); }));
  $("view").querySelectorAll("#samples .seg button").forEach((b) => { b.onclick = () => { state.runPolicy = b.dataset.p; pageRun(name, "samples"); }; });
  const t = $("all-secrets");
  if (t) t.onclick = () => { state.allSecrets = !state.allSecrets; pageRun(name, tab); };
}

/* ---------- Page: ablation ---------- */

function groupOf(row) {
  return row.label === "red_herring" ? `red_herring:${row.difficulty}` : row.label;
}
const GROUPS = [["violation", "Violation"], ["red_herring:easy", "Red herring · easy"], ["red_herring:medium", "Red herring · medium"], ["red_herring:hard", "Red herring · hard"], ["clean", "Clean"]]
  .map(([k, label]) => [k, k.startsWith("red_herring") ? term("red_herring", label) : label]);

function pageAblation(name) {
  const r = ablationRun(name);
  const e = ledgerEntry(name) || { name, config: {} };
  const crumbs = `<a href="#/">Runs</a> / <span class="mono">${esc(name)}</span>`;
  const conds = CONDITIONS.filter((c) => r?.samples.some((s) => s.condition === c));
  const reask = conds.length === 1 && conds[0] === "unedited";
  const title = reask ? term("kind_reask", "Judge re-ask") : term("kind_ablation", "Marker ablation");
  const n = r ? new Set(r.samples.map((s) => s.scenario_id)).size : null;
  const head = pageHead({ crumbs, title, sub: subLine(e, [`<span>${esc(e.config?.split || "dev")}</span>`, n ? `<span>${n} scenarios</span>` : ""]), purpose: e.purpose });
  if (!r) { $("view").innerHTML = head + `<p class="empty">No results for this run in this build.</p>`; return; }

  // The base is this run's unedited score, or for a re-ask, the latest full ablation's unedited score.
  const full = SITE.ablations.find((a) => a.name !== name && a.samples.some((s) => s.condition === "marker"));
  const baseRun = reask ? full : r;
  const base = Object.fromEntries((baseRun?.samples || []).filter((s) => s.condition === "unedited").map((s) => [s.scenario_id, s.score]));
  const reasks = SITE.ablations.filter((a) => a.name !== baseRun?.name && a.samples.every((s) => s.condition === "unedited"));
  const shiftsFor = (rows) => rows.filter((s) => s.scenario_id in base).map((s) => s.score - base[s.scenario_id]);

  const cols = reask ? ["unedited"] : conds;
  const noiseCol = !reask && reasks.length;
  const tableRows = GROUPS.map(([key, label]) => {
    const rows = r.samples.filter((s) => groupOf(s) === key);
    if (!rows.length) return "";
    const ids = new Set(rows.map((s) => s.scenario_id));
    const cells = cols.map((c) => {
      const these = rows.filter((s) => s.condition === c);
      const m = mean(these.map((s) => s.score));
      if (c === "unedited" && !reask) return `<td>${f0(m)}</td>`;
      const sh = mean(shiftsFor(these));
      return `<td>${f0(m)}<span class="delta">${signed(sh, 1)}</span></td>`;
    }).join("");
    let noise = "";
    if (noiseCol) {
      const ns = reasks.flatMap((a) => shiftsFor(a.samples.filter((s) => ids.has(s.scenario_id))));
      noise = `<td>${signed(mean(ns), 1)}<span class="delta">± ${f0(sd(ns))}</span></td>`;
    }
    return `<tr><td>${label}</td><td>${ids.size}</td>${cells}${noise}</tr>`;
  }).join("");
  const table = `<div class="panel"><div class="scroll"><table>
    <thead><tr><th>Group</th><th>n</th>${cols.map((c) => `<th>${reask ? "Re-ask" : term(c, CONDITION[c])}</th>`).join("")}${noiseCol ? `<th>${term("reask_noise", "Re-ask noise")}</th>` : ""}</tr></thead>
    <tbody>${tableRows}</tbody></table></div></div>`;

  // Per-scenario matrix: score per condition, shaded by shift from unedited.
  const ids = [...new Set(r.samples.map((s) => s.scenario_id))]
    .map((id) => r.samples.find((s) => s.scenario_id === id))
    .sort((a, b) => rankScenario(a) - rankScenario(b) || a.scenario_id.localeCompare(b.scenario_id));
  let last = null;
  const matrix = ids.map((any) => {
    const head = any.label !== last ? `<tr class="group-row"><td colspan="${2 + cols.length}">${LABELS[any.label]}</td></tr>` : "";
    last = any.label;
    const b = base[any.scenario_id];
    const cells = cols.map((c) => {
      const s = r.samples.find((x) => x.scenario_id === any.scenario_id && x.condition === c);
      if (!s) return `<td class="muted">—</td>`;
      if (c === "unedited" && !reask) return `<td>${sc(s.score)}</td>`;
      const d = b == null ? 0 : s.score - b;
      const k = Math.min(1, Math.abs(d) / 50).toFixed(2);
      return `<td class="${d > 0 ? "shift-up" : d < 0 ? "shift-down" : ""}" style="--s:${k}" ${dataTip(tipRows(`${sceneName(any.scenario_id)} · ${reask ? "Re-ask" : CONDITION[c]}`, [["Unedited", sc(b)], ["This condition", sc(s.score)], ["Change", signed(d)]]))}>${sc(s.score)}</td>`;
    }).join("");
    return `${head}<tr><td class="mono-cell">${esc(sceneName(any.scenario_id))}</td><td class="muted">${any.difficulty || ""}</td>${cells}</tr>`;
  }).join("");
  const matrixTable = `<div class="panel"><div class="scroll"><table>
    <thead><tr><th>Scenario</th><th style="text-align:left"></th>${cols.map((c) => `<th>${reask ? "Re-ask" : term(c, CONDITION[c])}</th>`).join("")}</tr></thead>
    <tbody>${matrix}</tbody></table></div></div>`;

  $("view").innerHTML = head
    + section("Protocol", protocolGrid(e))
    + section("Mean judge score", table, reask ? `<span>shift vs ${esc(baseRun?.name || "—")}</span>` : `<span>shift vs unedited</span>`)
    + section("By scenario", matrixTable, `<span>shaded by shift from unedited</span>`);
}

/* ---------- Page: scenarios ---------- */

function currentBuild() {
  return SITE.builds.find((b) => (b.key ?? b.manifest.split) === state.split) || SITE.builds[0] || null;
}

function highlight(text, secrets, snippet) {
  let html = esc(text);
  if (snippet) html = html.replace(esc(snippet), `<mark class="correlate">${esc(snippet)}</mark>`);
  for (const v of secrets) html = html.split(esc(v)).join(`<mark class="secret">${esc(v)}</mark>`);
  return html;
}

function scenarioDetail(s) {
  if (!s) return `<p class="empty">No scenario selected.</p>`;
  const values = s.secrets.map((x) => x.value);
  const corrByLog = Object.fromEntries(s.correlates.map((c) => [c.log_id, c]));
  const keys = new Set(s.key_evidence_ids);
  const secretRows = s.secrets.map((x) => {
    const cs = s.correlates.filter((c) => c.secret_type === x.secret_type);
    return `<tr><td>${esc(human(x.secret_type))}</td><td class="mono-cell">${esc(x.value)}</td>
      <td class="mono-cell">${cs.map((c) => `${esc(c.log_id)} · ${term(c.strength, c.strength)}`).join("<br>") || "—"}</td>
      <td class="wrap muted">${cs.map((c) => esc(c.rationale)).join("<br>")}</td></tr>`;
  }).join("");
  const hidden = s.logs.filter((e) => e.kind === "background").length;
  const logs = s.logs.filter((e) => state.showBackground || e.kind !== "background").map((e) => {
    const c = corrByLog[e.log_id];
    return `<div class="${e.kind === "background" ? "background" : ""} ${keys.has(e.log_id) ? "key" : ""}">
      <i class="k-${e.kind || "background"}"></i>
      <span class="id">${esc(e.log_id)}</span><span class="src">${esc(e.source)}</span>
      <span class="txt">${highlight(e.text, values, c && c.snippet)}</span></div>`;
  }).join("");
  return `
    <div><h3>${esc(s.scenario_id)}</h3><p class="claim">${esc(s.claim)}</p></div>
    <dl class="kv">
      <div><dt>Label</dt><dd class="text label-${s.label}">${s.label === "red_herring" ? term("red_herring", labelText(s)) : labelText(s)}</dd></div>
      <div><dt>Setup</dt><dd class="text">${esc(s.variant || "—")}</dd></div>
      <div><dt>Lab</dt><dd class="text">${esc(s.lab_name)}</dd></div>
      <div><dt>Lines</dt><dd>${s.logs.length} <span class="faint">${term("key_evidence", `${keys.size} key`)}</span></dd></div>
    </dl>
    <div><h4>Secrets</h4><div class="panel"><div class="scroll"><table class="left">
      <thead><tr><th>Secret</th><th>Value</th><th>${term("correlate", "Correlates")}</th><th>Why it leaks</th></tr></thead><tbody>${secretRows}</tbody></table></div></div></div>
    <div>
      <div class="sub" style="justify-content:space-between;margin:0 0 8px">
        <h4 style="margin:0">Logs</h4>
        <span><label class="toggle"><input type="checkbox" id="show-bg" ${state.showBackground ? "checked" : ""}> ${hidden} ${term("background", "background lines")}</label></span>
      </div>
      <div class="logs">${logs}</div>
      <div class="sub"><span><mark class="secret">value</mark> secret</span><span><mark class="correlate">detail</mark> ${term("correlate", "correlate")}</span><span><span style="color:var(--evidence)">LOG-ID</span> ${term("key_evidence", "key evidence")}</span></div>
    </div>`;
}

function pageScenarios(id) {
  const build = currentBuild();
  if (!build) { $("view").innerHTML = pageHead({ title: "Scenarios" }) + `<p class="empty">No builds. Run <code>uv run redaction data build</code>.</p>`; return; }
  const types = [...new Set(build.scenarios.map((s) => s.violation_type))];
  const list = build.scenarios.filter((s) => (!state.scLabel || s.label === state.scLabel) && (!state.scType || s.violation_type === state.scType));
  const selected = build.scenarios.find((s) => s.scenario_id === id) || list[0] || null;
  const splits = `<div class="seg" role="group" aria-label="Split">${SITE.builds.map((b) =>
    `<button type="button" data-split="${esc(b.key ?? b.manifest.split)}" aria-pressed="${b === build}">${esc(b.key ?? b.manifest.split)}</button>`).join("")}</div>`;
  const filters = `${splits}
    <select id="f-label" aria-label="Label"><option value="">All labels</option>${LABEL_ORDER.map((l) => `<option value="${l}" ${state.scLabel === l ? "selected" : ""}>${LABELS[l]}</option>`).join("")}</select>
    <select id="f-type" aria-label="Violation type"><option value="">All types</option>${types.map((t) => `<option value="${t}" ${state.scType === t ? "selected" : ""}>${esc(human(t))}</option>`).join("")}</select>`;
  const items = list.map((s) => `<li tabindex="0" data-id="${esc(s.scenario_id)}" aria-selected="${s === selected}"><b>${esc(s.scenario_id)}</b><span class="label-${s.label}">${labelText(s)}</span></li>`).join("")
    || `<li><span>No scenarios match.</span></li>`;
  $("view").innerHTML = pageHead({ title: "Scenarios", sub: `<span>${list.length} of ${build.scenarios.length}</span><span class="mono">build ${esc(build.manifest.version)}</span>` })
    + section("Browse", `<div class="browser"><ol class="list panel">${items}</ol><article class="detail">${scenarioDetail(selected)}</article></div>`, filters);
  $("view").querySelectorAll(".list li[data-id]").forEach((li) => onKey(li, () => { location.hash = `#/scenarios/${li.dataset.id}`; }));
  $("view").querySelectorAll("[data-split]").forEach((b) => { b.onclick = () => { state.split = b.dataset.split; location.hash = "#/scenarios"; route(); }; });
  $("f-label").onchange = (e) => { state.scLabel = e.target.value; pageScenarios(); };
  $("f-type").onchange = (e) => { state.scType = e.target.value; pageScenarios(); };
  const bg = $("show-bg");
  if (bg) bg.onchange = (e) => { state.showBackground = e.target.checked; pageScenarios(selected?.scenario_id); };
}

/* ---------- Page: data ---------- */

function pageData() {
  const build = currentBuild();
  if (!build) { $("view").innerHTML = pageHead({ title: "Data" }) + `<p class="empty">No builds.</p>`; return; }
  const m = build.manifest;
  const splits = `<div class="seg" role="group" aria-label="Split">${SITE.builds.map((b) =>
    `<button type="button" data-split="${esc(b.key ?? b.manifest.split)}" aria-pressed="${b === build}">${esc(b.key ?? b.manifest.split)}</button>`).join("")}</div>`;
  const stages = `<div class="stages">${STAGES.map(([key, name]) => {
    const skipped = key === "reviewed" && !m.reviewer;
    return `<div class="stage ${skipped ? "skipped" : ""}"><b>${skipped ? "—" : m.stages[key]}</b><span>${term(key, name)}</span></div>`;
  }).join("")}</div>`;
  const kept = build.scenarios;
  const types = [...new Set(build.records.map((r) => r.violation_type))];
  const cols = [["violation", null, "Violation"], ["red_herring", "easy", term("red_herring", "RH easy")], ["red_herring", "medium", term("red_herring", "RH medium")], ["red_herring", "hard", term("red_herring", "RH hard")], ["clean", null, "Clean"]];
  const count = (t, l, d) => kept.filter((s) => s.violation_type === t && s.label === l && (s.difficulty ?? null) === d).length;
  const composition = `<div class="panel"><div class="scroll"><table><thead><tr><th>Violation type</th>${cols.map((c) => `<th>${c[2]}</th>`).join("")}</tr></thead>
    <tbody>${types.map((t) => `<tr><td>${esc(human(t))}</td>${cols.map(([l, d]) => { const n = count(t, l, d); return `<td class="${n ? "" : "muted"}">${n}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div></div>`;
  const total = Object.values(m.line_kinds).reduce((a, b) => a + b, 0) || 1;
  const kinds = `<div class="panel pad"><div class="kind-bar" role="img" aria-label="Share of lines by kind">${KINDS.map(([k]) =>
      `<i class="k-${k}" style="width:${(100 * (m.line_kinds[k] || 0) / total).toFixed(2)}%"></i>`).join("")}</div>
    <div class="legend">${KINDS.map(([k, name]) => `<div><i class="k-${k}"></i><span>${term(k === "correlate" ? "correlate" : k, name)}</span><span>${(100 * (m.line_kinds[k] || 0) / total).toFixed(0)}%</span></div>`).join("")}</div>
    <div class="sub" style="margin-top:14px"><span>${m.lines.min}–${m.lines.max} lines per scenario</span><span>mean ${m.lines.mean}</span>${m.background_jobs ? `<span>${m.background_jobs.toLocaleString()} real jobs sampled</span>` : ""}</div></div>`;
  const counts = m.issues || {};
  const checks = `<div class="panel"><div class="scroll"><table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>${Object.entries(CHECKS).map(([k, name]) => {
    const n = counts[k] || 0;
    return `<tr><td>${name}</td><td><span class="badge ${n ? "fail" : "pass"}">${n ? n + " failed" : "pass"}</span></td></tr>`;
  }).join("")}<tr><td>Blind label review</td><td>${m.reviewer ? `<span class="badge ${build.records.some((r) => r.status === "review_disagrees") ? "fail" : "pass"}">${esc(m.reviewer)}</span>` : '<span class="badge">not run</span>'}</td></tr></tbody></table></div></div>`;
  $("view").innerHTML = pageHead({ title: "Data", sub: `<span class="mono">build ${esc(m.version)}</span><span>renderer ${esc(m.renderer)}</span>${m.depth === "deep" ? "<span>deep variants (draft)</span>" : ""}<span>${esc(m.built_at.replace("T", " ").slice(0, 16))} UTC</span>` })
    + section("Pipeline", stages, splits)
    + `<div class="grid2">${section("Composition", composition)}${section("Line kinds", kinds)}</div>`
    + section("Validation", checks);
  $("view").querySelectorAll("[data-split]").forEach((b) => { b.onclick = () => { state.split = b.dataset.split; pageData(); }; });
}

/* ---------- Page: notes ---------- */

const STATUS_CLASS = { open: "warn", settled: "pass", superseded: "" };

function markdown(src) {
  const runNames = new Set((SITE.ledger || []).map((e) => e.name));
  const inline = (t) => esc(t)
    .replace(/`([^`]+)`/g, (_, c) => runNames.has(c)
      ? `<a class="code-link" href="${c.startsWith("ablation") ? "#/ablation/" : "#/run/"}${c}"><code>${c}</code></a>`
      : `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*]+)\*/g, "$1<em>$2</em>");
  const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const out = [];
  let para = [], list = null, table = null;
  const flush = () => {
    if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; }
    if (list) { out.push(`<${list.tag}>${list.items.map((li) => `<li>${inline(li)}</li>`).join("")}</${list.tag}>`); list = null; }
    if (table) {
      const [head, ...rows] = table;
      out.push(`<div class="panel"><div class="scroll"><table class="left prose-table"><thead><tr>${head.map((h) => `<th>${inline(h)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td class="wrap">${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`);
      table = null;
    }
  };
  for (const line of src.split(/\r?\n/)) {
    if (/^#\s/.test(line)) { flush(); continue; } // the page title comes from the sidebar entry
    if (/^\s*\|/.test(line)) {
      if (!table) { flush(); table = []; }
      if (!/^\s*\|[\s:|-]+\|\s*$/.test(line)) table.push(cells(line));
      continue;
    }
    if (table) flush();
    const h = line.match(/^(#{2,3})\s+(.*)/);
    if (h) { flush(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    const st = line.match(/^Status:\s*(\w+)\s*(?:—\s*(.*))?$/);
    if (st) {
      flush();
      const k = st[1].toLowerCase();
      out.push(`<p class="status"><span class="badge ${STATUS_CLASS[k] ?? ""}">${esc(k)}</span>${st[2] ? `<span class="muted">${inline(st[2])}</span>` : ""}</p>`);
      continue;
    }
    const ul = line.match(/^\s*[-*]\s+(.*)/), ol = line.match(/^\s*\d+\.\s+(.*)/);
    if (ul || ol) {
      const tag = ul ? "ul" : "ol";
      if (para.length || (list && list.tag !== tag)) flush();
      list = list || { tag, items: [] };
      list.items.push((ul || ol)[1]);
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    if (list) list.items[list.items.length - 1] += " " + line.trim(); else para.push(line.trim());
  }
  flush();
  return out.join("");
}

function pageNotes(slug) {
  const pages = Array.isArray(SITE.notes) ? SITE.notes : [];
  if (!pages.length) { $("view").innerHTML = pageHead({ title: "Notes" }) + `<p class="empty">No notes. Add pages under <code>docs/notes/</code>.</p>`; return; }
  const page = pages.find((p) => p.slug === slug) || pages[0];
  const side = `<nav class="side" aria-label="Notes">${pages.map((p) =>
    `<a href="#/notes/${p.slug}" ${p === page ? 'aria-current="page"' : ""}>${esc(p.title)}</a>`).join("")}</nav>`;
  $("view").innerHTML = `<div class="notes">${side}<article class="prose"><h1>${esc(page.title)}</h1>${markdown(page.markdown)}</article></div>`;
}

/* ---------- Paper ---------- */

let paperTimer = null;

function paperSide(st) {
  const total = st.outline.reduce((n, s) => n + s.words, 0);
  const items = st.outline.map((s) =>
    `<li><span>${esc(s.title)}</span><span class="${s.words ? "num" : "faint"}">${s.words ? s.words.toLocaleString() : "empty"}</span></li>`).join("");
  const built = new Date(st.built_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const state = st.ok
    ? `<span class="badge pass">compiled</span><span class="muted">${built} · ${st.seconds}s</span>`
    : `<span class="badge fail">error</span><span class="muted">${built}</span>`;
  const errors = st.ok ? "" : `<pre class="paper-errors">${st.errors.map(esc).join("\n")}</pre>`;
  return `<p class="status">${state}</p>${errors}
    <ol class="outline">${items}</ol>
    <p class="muted small">${total.toLocaleString()} words written · <a href="paper/main.pdf" target="_blank" rel="noopener">Open PDF ↗</a></p>`;
}

function pagePaper() {
  const st = SITE.paper;
  if (!st) {
    $("view").innerHTML = pageHead({ title: "Paper" }) + `<p class="empty">Not compiled yet. Run <code>uv run redaction paper watch</code>.</p>`;
    return;
  }
  let stamp = st.built_at;
  $("view").innerHTML = `<div class="paper"><aside class="paper-side" id="paper-side">${paperSide(st)}</aside>
    <iframe class="paper-pdf" id="paper-pdf" title="Paper PDF" src="paper/main.pdf?v=${encodeURIComponent(stamp)}#view=FitH"></iframe></div>`;
  paperTimer = setInterval(() => {
    fetch(`paper/status.json?t=${Date.now()}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((next) => {
        if (!next || next.built_at === stamp) return;
        stamp = next.built_at;
        SITE.paper = next;
        $("paper-side").innerHTML = paperSide(next);
        if (next.ok) $("paper-pdf").src = `paper/main.pdf?v=${encodeURIComponent(stamp)}#view=FitH`;
      })
      .catch(() => {});
  }, 2000);
}

/* ---------- Router ---------- */

function route() {
  const hash = location.hash === "#runs" ? "#/" : location.hash || "#/";
  const [, page = "", arg = ""] = hash.match(/^#\/([^/]*)\/?(.*)$/) || [];
  const nav = { "": "runs", run: "runs", ablation: "runs", scenarios: "scenarios", data: "data", notes: "notes", paper: "paper" }[page] || "runs";
  clearInterval(paperTimer);
  document.querySelectorAll("[data-nav]").forEach((a) => a.toggleAttribute("aria-current", false));
  document.querySelector(`[data-nav="${nav}"]`)?.setAttribute("aria-current", "page");
  const name = decodeURIComponent(arg);
  if (page === "run") {
    const [runName, tab = ""] = name.split("/");
    if (state.lastRun !== runName) { state.runSample = null; state.lastRun = runName; }
    pageRun(runName, tab);
  }
  else if (page === "ablation") pageAblation(name);
  else if (page === "scenarios") pageScenarios(name);
  else if (page === "data") pageData();
  else if (page === "notes") pageNotes(name);
  else if (page === "paper") pagePaper();
  else pageRuns();
}

window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

fetch("data/site.json")
  .then((r) => { if (!r.ok) throw new Error(`site.json: HTTP ${r.status}`); return r.json(); })
  .then((site) => {
    SITE = { builds: [], runs: [], ablations: [], ledger: [], notes: [], ...site };
    route();
  })
  .catch((err) => {
    $("view").innerHTML = `<p class="empty">Could not load data/site.json (${esc(err.message)}). Rebuild with <code>uv run redaction site</code>.</p>`;
  });
