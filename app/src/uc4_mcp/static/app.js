"use strict";
// Breeder screen. Every node is built with el(): text goes in as text nodes, never as markup,
// so nothing the API returns can inject HTML.

const byId = (id) => document.getElementById(id);
const SHAPE = { PASS: "●", HOLD: "▲", FAIL: "■" };
const state = { trial: null, decisions: [], trials: new Map(), chat: [], openSeq: 0, lineSeq: 0 };

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(typeof c === "string" || typeof c === "number" ? document.createTextNode(c) : c);
  }
  return node;
}

const show = (target, ...children) => target.replaceChildren(...children.flat().filter(Boolean));
const ref = (row) => `${row.source_file}#${row.row_id}`;
const fmt = (v, uom) => (v == null ? "n/a" : `${v}${uom ? " " + uom : ""}`);

async function api(path, options) {
  try {
    const res = await fetch(path, options);
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
    return { status: res.status, data };
  } catch (_) {
    return { status: 0, data: { message: "Cannot reach the server.", text: "Cannot reach the server." } };
  }
}

const post = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

function errorMessage(res) {
  const d = res.data || {};
  return d.message || d.text || (d.detail && d.detail[0] && d.detail[0].msg) || `Error ${res.status}`;
}

// Provenance: a tooltip plus a "source" toggle that reveals file#row.
function withSource(content, refs) {
  const detail = el("span", { class: "src-detail", hidden: true, text: refs.join(", ") });
  const toggle = el("button", {
    type: "button", class: "link src", text: "source", "aria-expanded": "false",
    onclick: (e) => {
      e.stopPropagation(); // don't trigger a clickable parent row
      detail.hidden = !detail.hidden;
      toggle.setAttribute("aria-expanded", String(!detail.hidden));
    },
  });
  return el("td", { title: refs.join("\n") }, content, " ", refs.length ? toggle : null,
    " ", detail);
}

const th = (...names) => el("thead", {}, el("tr", {}, names.map((n) => el("th", { text: n }))));
const refsAttr = (refs) => refs.join("|");

function renderCandidates(target, message, candidates, onPick) {
  show(target, message ? el("span", { text: message }) : null,
    (candidates || []).map((c) => el("button", {
      type: "button", text: c.label || c.id, onclick: () => onPick(c),
    })));
}

function renderBanner(rec) {
  const shape = SHAPE[rec.verdict] || "";
  const banner = byId("banner");
  banner.className = `banner ${rec.colour}`;
  show(banner,
    el("p", { class: "verdict", text: `${shape} ${rec.verdict}` }),
    el("p", {}, el("strong", { text: rec.trial_id }), ` · ${rec.reason}`),
    el("p", { class: "src", text: `Rule set: ${rec.rule_version}. Thresholds are inferred, not approved.` }),
    !rec.matches_supplied
      ? el("p", { text: `The supplied verdict was ${rec.supplied_verdict}.` }) : null,
    el("p", {}, el("strong", { text: "The breeder decides." }),
      " This is a proposal with its evidence, not a decision."));
}

function criterionStatus(c) {
  if (c.value == null) return el("span", { class: "bad", text: "missing: not met" });
  if (c.kind === "knockout") {
    return c.triggered ? el("span", { class: "bad", text: "knockout triggered" })
      : el("span", { class: "ok", text: "not triggered" });
  }
  return c.passed ? el("span", { class: "ok", text: "met" })
    : el("span", { class: "bad", text: "not met" });
}

function renderCriteria(t) {
  const byField = new Map(t.values.map((v) => [v.field, v]));
  const rows = t.recommendation.criteria.map((c) => {
    const row = byField.get(c.field);
    const refs = row ? [ref(row)] : t.recommendation.evidence_row_ids;
    const [lo, hi] = c.bracket;
    return el("tr", { "data-refs": refsAttr(refs) },
      el("td", { text: c.label }),
      withSource(fmt(c.value, row && row.uom), refs),
      el("td", { text: `${c.test} ${c.threshold}${row && row.uom ? " " + row.uom : ""}` }),
      el("td", { text: `${lo} to ${hi} (inferred)` }),
      el("td", {}, criterionStatus(c)));
  });
  show(byId("criteria"), th("Criterion", "Value", "Test", "Bracket (inferred)", "Result"),
    el("tbody", {}, rows));
}

function renderRationale(t) {
  const rec = t.recommendation;
  const label = new Map(rec.criteria.map((c) => [c.field, c.label]));
  show(byId("rationale"),
    el("p", { text: rec.supplied_rationale || "No rationale supplied." }),
    rec.rationale_omits.length ? el("p", { class: "warn" },
      `The supplied text does not mention: ${rec.rationale_omits.map((f) => label.get(f) || f).join(", ")}`)
      : null);
}

function renderAggregates(t) {
  const explain = t.flags.concat(t.recommendation.flags)
    .find((f) => f.code === "AGGREGATE_LINKS_UNVERIFIED");
  const row = (name, a, b) => el("tr", {}, el("td", { text: name }),
    el("td", { text: fmt(a) }), el("td", { text: fmt(b) }));
  show(byId("aggregates"),
    el("div", { class: "scroll" }, el("table", {},
      th("Measure", "Supplied", "From linked observations"),
      el("tbody", {},
        row("GBV mean", t.supplied_gbv_mean, t.linked_gbv_mean),
        row("Resistant lines %", t.supplied_resistant_pct, t.linked_resistant_pct)))),
    explain ? el("p", { class: "info", text: explain.message }) : null);
}

function allFlags(t) {
  const seen = new Set();
  const flags = t.recommendation.flags.concat(t.flags).filter((f) => {
    const key = f.code + f.message;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return flags.sort((a, b) => (a.severity === "warning" ? 0 : 1) - (b.severity === "warning" ? 0 : 1));
}

function renderFlags(t) {
  const flags = allFlags(t);
  show(byId("flags"), flags.length ? flags.map((f) => el("div", {
    class: f.severity === "warning" ? "warn" : "info",
    "data-refs": refsAttr(f.evidence_row_ids),
  },
  el("strong", { text: f.code }), `: ${f.message}`,
  f.evidence_row_ids.length ? el("details", {},
    el("summary", { text: `${f.evidence_row_ids.length} evidence rows` }),
    el("ul", {}, f.evidence_row_ids.map((id) => el("li", { text: id })))) : null))
    : el("p", { class: "muted", text: "No flags." }));
}

const field = (rows, name) => (rows.find((r) => r.field === name) || {}).value;

function renderLines(t) {
  ++state.lineSeq;
  const rows = t.lines.map((l) => {
    const open = () => openLine(l.material_guid);
    const gbv = l.genomics.find((r) => r.field === "GENOMIC_BREEDING_VALUE");
    const resistance = l.genomics.find((r) => r.field === "MARKER_DISEASE_RESISTANCE");
    const refs = [ref(l.link), ...l.genomics.map(ref)];
    return el("tr", {
      class: "clickable", tabindex: "0", "data-refs": refsAttr(refs),
      onclick: open,
      onkeydown: (e) => {
        if (e.target !== e.currentTarget) return; // keys on the nested "source" button are its own
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      },
    },
    el("td", { text: l.material_id }),
    withSource(fmt(gbv && gbv.value), gbv ? [ref(gbv)] : []),
    withSource(fmt(resistance && resistance.value), resistance ? [ref(resistance)] : []));
  });
  show(byId("lines"), th("Material ID", "GBV", "Resistance marker"), el("tbody", {}, rows));
  const select = byId("decision-form").elements.material_guid;
  select.replaceChildren(el("option", { value: "", text: "No specific line" }),
    ...t.lines.map((l) => el("option", { value: l.material_guid, text: l.material_id })));
  show(byId("line-panel"));
}

// The reason text already starts with the verdict word; don't show it twice.
const stripVerdict = (reason, verdict) =>
  (reason || "").startsWith(`${verdict}: `) ? reason.slice(verdict.length + 2) : reason;

function renderLinePanel(view) {
  const panel = byId("line-panel");
  panel.replaceChildren();
  const flags = view.flags.map((f) => el("li", {}, el("strong", { text: f.code }), `: ${f.message}`));
  show(panel,
    el("h3", { text: `Line ${view.material_id}` }),
    el("p", { class: "muted", text: view.note }),
    el("h4", { text: "Genomics" }),
    el("ul", {}, view.genomics.map((g) => el("li", { text: `${g.field}: ${fmt(g.value, g.uom)}` }))),
    el("h4", { text: "Lab observations" }),
    view.lab.length ? el("ul", {}, view.lab.map((r) => el("li", { text: `${r.field}: ${fmt(r.value)}` })),
      el("li", { class: "muted", text: "lab rows have no trial key: not linked to this trial" }))
      : el("p", { class: "muted", text: "No lab rows." }),
    el("h4", { text: "Trial verdicts (per trial, not per line)" }),
    el("ul", {}, view.trials.map((x) => el("li", {},
      el("strong", { text: x.trial_id }),
      ` ${SHAPE[x.verdict] || ""} ${x.verdict}: ${stripVerdict(x.reason, x.verdict)}`))),
    view.operations.length ? el("h4", { text: "Operations" }) : null,
    view.operations.length ? el("ul", {}, view.operations.map((o) =>
      el("li", { text: `${o.date || "no date"} · ${o.operation_type} · ${o.status}` }))) : null,
    view.flags.length ? el("h4", { text: "Flags" }) : null,
    view.flags.length ? el("ul", {}, flags) : null);
  panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function openLine(guid) {
  const seq = ++state.lineSeq;
  const trial = state.trial;
  const res = await api(`/lines/${encodeURIComponent(guid)}`);
  if (seq !== state.lineSeq || state.trial !== trial) return;
  if (res.data && res.data.status === "ok") renderLinePanel(res.data.result);
  else show(byId("line-panel"), el("p", { class: "error", text: errorMessage(res) }));
}

function renderOperations(t) {
  const rows = t.operations.map((o) => {
    const codes = [...new Set(o.evidence.flatMap((e) => e.flags))];
    return el("tr", { "data-refs": refsAttr(o.evidence.map(ref)) },
      el("td", { text: o.date || "no date" }), el("td", { text: o.operation_type }),
      el("td", { text: o.status }), el("td", { text: codes.join(", ") || "none" }));
  });
  show(byId("operations"), th("Date", "Type", "Status", "Flags"), el("tbody", {}, rows));
}

function renderHistory() {
  const items = [...state.decisions].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  show(byId("history"), items.length ? items.map((d) => el("div", { class: "hist-item" },
    el("strong", { text: `${SHAPE[d.decision]} ${d.decision}` }),
    d.overrides ? el("span", { class: "badge override", text: "override" }) : null,
    ` by ${d.user} at ${d.timestamp}`,
    el("div", { text: d.reason }),
    el("div", { class: "src", text: `Made against recommendation: ${d.recommendation.verdict}` })))
    : el("p", { class: "muted", text: "No decisions recorded yet." }));
}

function optionText(entry) {
  const last = entry.latest_decision ? ` · decided ${entry.latest_decision.decision}` : "";
  return `${entry.trial_id} · ${entry.verdict}${last}`;
}

function renderTrialList() {
  byId("trial-list").replaceChildren(
    ...[...state.trials.values()].map((e) => el("option", { value: optionText(e) })));
}

function highlight(refs) {
  for (const n of document.querySelectorAll(".cited")) n.classList.remove("cited");
  const wanted = new Set(refs);
  for (const n of document.querySelectorAll("[data-refs]")) {
    if (n.dataset.refs.split("|").some((r) => wanted.has(r))) n.classList.add("cited");
  }
}

function resetDecisionForm() {
  const form = byId("decision-form");
  form.elements.reason.value = "";
  for (const r of form.querySelectorAll("input[type=radio]")) r.checked = false;
}

function clearTrial() {
  ++state.lineSeq;
  state.trial = null;
  state.decisions = [];
  for (const id of ["banner", "criteria", "rationale", "aggregates", "flags", "lines",
    "line-panel", "operations", "history", "decision-error"]) show(byId(id));
  byId("banner").className = "banner";
  byId("decision-form").elements.material_guid.replaceChildren(
    el("option", { value: "", text: "No specific line" }));
  resetDecisionForm();
  byId("decision-form").querySelector("button[type=submit]").disabled = true;
}

function renderTrial(t, decisions) {
  const changed = !state.trial || state.trial.trial_guid !== t.trial_guid;
  state.trial = t;
  state.decisions = decisions;
  byId("decision-form").querySelector("button[type=submit]").disabled = false;
  renderBanner(t.recommendation);
  renderCriteria(t);
  renderRationale(t);
  renderAggregates(t);
  renderFlags(t);
  renderLines(t);
  renderOperations(t);
  renderHistory();
  show(byId("decision-error"));
  if (changed) resetDecisionForm(); // never carry a draft from one trial to another
}

async function openTrial(query) {
  const seq = ++state.openSeq;
  const res = await api(`/trials/${encodeURIComponent(query)}`);
  if (seq !== state.openSeq) return;
  const d = res.data || {};
  const box = byId("candidates");
  if (d.status === "ok") {
    show(box);
    renderTrial(d.result, d.decisions || []);
    byId("trial-search").value = d.result.trial_id;
    if (location.hash !== `#${d.result.trial_id}`) history.replaceState(null, "", `#${d.result.trial_id}`);
  } else {
    // Nothing is open any more: a decision must not be recorded against the previous trial.
    clearTrial();
    if (d.status === "many") renderCandidates(box, d.message, d.candidates, (c) => openTrial(c.id));
    else show(box, el("span", { class: "error", text: errorMessage(res) }));
  }
}

async function loadTrials() {
  const res = await api("/trials");
  if (res.status !== 200 || !Array.isArray(res.data)) {
    show(byId("candidates"), el("span", { class: "error", text: "Could not load the trial list." }));
    return;
  }
  state.trials = new Map(res.data.map((e) => [e.trial_id, e]));
  renderTrialList();
  const wanted = decodeURIComponent(location.hash.slice(1));
  if (wanted || res.data.length) await openTrial(wanted || res.data[0].trial_id);
}

async function submitDecision(event) {
  event.preventDefault();
  const form = byId("decision-form");
  const err = byId("decision-error");
  const button = form.querySelector("button[type=submit]");
  const alias = byId("user-alias").value.trim();
  if (!state.trial) return show(err, "Open a trial first.");
  if (!form.elements.decision.value) return show(err, "Choose PASS, HOLD or FAIL.");
  if (!alias) return show(err, "Enter your alias first.");
  if (form.elements.reason.value.trim().length < 5) {
    return show(err, "A reason of 5 to 1000 characters is required.");
  }
  show(err);
  const t = state.trial; // the breeder may switch trials while the request is in flight
  button.disabled = true;
  try {
    const res = await post("/decisions", {
      trial: t.trial_guid, decision: form.elements.decision.value,
      reason: form.elements.reason.value, user: alias,
      material_guid: form.elements.material_guid.value || null,
    });
    if (res.status === 201) {
      const entry = state.trials.get(t.trial_id);
      if (entry) { entry.latest_decision = res.data; renderTrialList(); }
      if (state.trial === t) {
        state.decisions = [res.data, ...state.decisions];
        resetDecisionForm();
        renderHistory();
      }
    } else if (state.trial === t) {
      show(err, errorMessage(res));
    }
  } finally {
    button.disabled = !state.trial;
  }
}

function renderAnswer(res, question) {
  const box = byId("answer");
  const a = res.data || {};
  answerState.set(box, "error", false);
  if (res.status === 503) return show(box, el("p", { class: "warn", text: `Ask unavailable: ${a.text}` }));
  if (res.status !== 200) return show(box, el("p", { class: "error", text: errorMessage(res) }));
  const responseState = answerState.classify(a);
  if (responseState === "error") return show(box, el("p", { class: "error", text: "No usable answer returned. Please try again." }));
  const cites = a.citations || [];
  show(box,
    a.status === "unverified" ? el("p", { class: "warn" },
      "Unverified: some claims could not be checked against the data. Treat with care.") : null,
    el("p", { class: "answer-text", text: a.text }),
    a.status === "clarify" ? el("div", { id: "clarify" }) : null,
    cites.length ? el("ol", { class: "cites" }, cites.map((c) =>
      el("li", { text: c.found ? c.ref : `${c.ref} (not found)` }))) : null,
    a.disclaimer ? el("p", { class: "muted", text: a.disclaimer }) : null);
  answerState.set(box, responseState);
  answerState.question(box, question);
  if (a.status === "clarify") {
    renderCandidates(box.querySelector("#clarify"), "", a.candidates, (c) => {
      openTrial(c.id);
      ask(c.id);
    });
  }
  highlight(cites.filter((c) => c.found).map((c) => c.ref));
}

let askSequence = 0;
async function ask(question) {
  const sequence = ++askSequence;
  const button = byId("ask-form").querySelector("button");
  button.disabled = true;
  byId("ask-form").setAttribute("aria-busy", "true");
  answerState.set(byId("answer"), "pending", false);
  show(byId("answer"), el("p", { class: "muted", text: "Checking evidence…" }));
  try {
    const res = await post("/ask", { question, history: state.chat.slice(-10) });
    if (sequence !== askSequence) return;
    renderAnswer(res, question);
    if (res.status === 200 && res.data && res.data.text) {
      state.chat.push({ role: "user", content: question }, { role: "assistant", content: res.data.text });
      state.chat = state.chat.slice(-10);
    }
  } finally {
    if (sequence === askSequence) {
      button.disabled = false;
      byId("ask-form").setAttribute("aria-busy", "false");
    }
  }
}

function init() {
  try { byId("user-alias").value = localStorage.getItem("uc4-alias") || ""; } catch (_) { /* storage blocked */ }
  byId("user-alias").addEventListener("input", (e) => {
    try { localStorage.setItem("uc4-alias", e.target.value); } catch (_) { /* storage blocked */ }
  });
  byId("trial-search").addEventListener("change", (e) => {
    const q = e.target.value.split("·")[0].trim();
    if (q) openTrial(q);
  });
  byId("decision-form").addEventListener("submit", submitDecision);
  byId("ask-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const box = byId("ask-question");
    const q = box.value.trim();
    if (q) { box.value = ""; ask(q); }
  });
  window.addEventListener("hashchange", () => {
    const q = decodeURIComponent(location.hash.slice(1));
    if (q && (!state.trial || q !== state.trial.trial_id)) openTrial(q);
  });
  loadTrials();
}

init();
