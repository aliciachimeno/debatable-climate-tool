"use strict";

const $ = (id) => document.getElementById(id);
const TYPE_LABEL = {
  descriptive_factual: "Descriptive / factual", causal_attribution: "Causal attribution",
  predictive: "Predictive", policy_value: "Policy / value",
};
const ABOUT_LABEL = { claim: "THE CLAIM", implied_argument: "IMPLIED ARGUMENT", ambiguity: "AMBIGUITY", assumption: "ASSUMPTION" };
const STANCE_LABEL = { supports: "Supports this", refutes: "Contradicts this", context: "Context" };
// Evidence is shown one group at a time: the claim first, the rest behind a button.
const EVIDENCE_GROUPS = [["claim", "The claim"], ["implied_argument", "Implied argument"],
  ["ambiguity", "Ambiguities"], ["assumption", "Assumptions"]];
let evidenceGroup = "claim";

let run = 0;            // increments with every new claim, so stale responses are ignored
let pollTimer = null;

/* ---------- tiny DOM helper (all text goes through textContent: model output is untrusted) ---------- */
function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (typeof v === "function") node[k] = v;          // onclick etc.
    else if (v !== false && v != null) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) node.append(kid);
  return node;
}
function clear(node) { node.replaceChildren(); return node; }

/* ---------- api ---------- */
async function api(path, body) {
  const res = await fetch(path, body ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

/* ---------- tabs ---------- */
function showTab(name) {
  for (const t of ["debate", "evidence"]) {
    const on = t === name;
    $("tab-" + t).setAttribute("aria-selected", on);
    $("tab-" + t).tabIndex = on ? 0 : -1;
    $("panel-" + t).hidden = !on;
  }
}
$("tab-debate").onclick = () => showTab("debate");
$("tab-evidence").onclick = () => showTab("evidence");
document.querySelector(".tabs").addEventListener("keydown", (e) => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const next = $("tab-debate").getAttribute("aria-selected") === "true" ? "evidence" : "debate";
  showTab(next); $("tab-" + next).focus();
});

/* ---------- claim with the ambiguous terms marked ---------- */
function claimNodes(claim, ambiguities) {
  const spans = [];
  ambiguities.forEach((a, i) => {
    const at = claim.toLowerCase().indexOf((a.term_or_relation || "").toLowerCase());
    if (at >= 0 && a.term_or_relation) spans.push({ s: at, e: at + a.term_or_relation.length, n: i + 1 });
  });
  spans.sort((a, b) => a.s - b.s);
  const out = []; let pos = 0;
  for (const sp of spans) {
    if (sp.s < pos) continue;                       // overlapping term: skip
    out.push(claim.slice(pos, sp.s), el("mark", { text: claim.slice(sp.s, sp.e) }), el("sup", { class: "n", text: sp.n }));
    pos = sp.e;
  }
  out.push(claim.slice(pos));
  return out;
}

/* ---------- debate (analysis) ---------- */
function row(label, content) {
  return el("div", { class: "row" }, el("h2", { text: label }), content);
}
function renderDebate(a) {
  const panel = clear($("panel-debate"));
  const rows = [
    row("LITERAL MEANING", el("p", { text: a.literal_meaning })),
    row("IMPLIED ARGUMENT", el("p", { text: a.implied_argument })),
    row("AMBIGUITIES", a.ambiguities.length
      ? el("ul", {}, a.ambiguities.map((x, i) => el("li", {},
          el("span", { class: "num", text: i + 1 }), el("b", { text: `“${x.term_or_relation}”` }),
          el("span", { class: "sub", text: " — " + x.possible_meanings.join("; ") }))))
      : el("p", { class: "sub", text: "None found." })),
    row("HIDDEN ASSUMPTIONS", el("ul", {}, a.hidden_assumptions.map((h) => el("li", { text: h })))),
  ];
  const m = a.type_mismatch;
  if (m && m.detected) {
    rows.push(row("TYPE CHECK", el("p", {},
      el("b", { text: `${m.premise_type} → ${m.conclusion_type}. ` }), m.explanation)));
  }
  panel.append(
    el("div", { class: "sheet-head mono" }, el("span", { text: "CLAIM UNDER ANALYSIS" }),
      el("span", { text: "TYPE · " + (TYPE_LABEL[a.claim_type] || a.claim_type).toUpperCase(), title: a.type_reason })),
    el("h1", { class: "claim-text" }, claimNodes(a.claim, a.ambiguities)),
    el("div", { class: "rows" }, rows),
    el("div", { class: "foot" }, el("span", { text: "Next: what the official sources say." }),
      el("button", { class: "btn", type: "button", text: "Scientific evidence →", onclick: () => showTab("evidence") })),
  );
}
function renderDebateLoading(claim) {
  clear($("panel-debate")).append(
    el("div", { class: "sheet-head mono" }, el("span", { text: "CLAIM UNDER ANALYSIS" })),
    el("h1", { class: "claim-text", text: claim }),
    el("p", { class: "loading", role: "status", text: "Reading the claim…", style: "margin-top:32px" }));
}
function renderError(panel, message, retry) {
  panel.append(el("p", { class: "errline", role: "alert", text: message }),
    retry ? el("button", { class: "btn quiet", type: "button", text: "Try again", onclick: retry, style: "margin-top:16px" }) : null);
}

/* ---------- evidence ---------- */
function prettyDoc(name) {
  return name.replace(/\.pdf$/i, "").replace(/_/g, " ").replace(/Chapter(\d+)/i, (_, n) => "Chapter " + parseInt(n, 10));
}
function pageText(p) { return p.length === 1 ? `p. ${p[0]}` : `pp. ${p[0]}–${p[p.length - 1]}`; }

function findingNode(f) {
  const strength = [f.likelihood, f.confidence && `${f.confidence} confidence`, f.stated_as_fact && "stated as fact"].filter(Boolean);
  const also = f.also_in || [];
  return el("div", { class: "finding" },
    el("p", { class: "stmt", text: f.statement }),
    el("blockquote", { text: `“${f.quote}”` }),
    el("div", { class: "meta" },
      STANCE_LABEL[f.stance] ? el("span", { class: "stance " + f.stance, text: STANCE_LABEL[f.stance] }) : null,
      el("span", { text: `${prettyDoc(f.document)} · ${pageText(f.pages)}` }),
      strength.length ? el("span", { class: "strength", text: strength.join(" · ") }) : null),
    also.length ? el("details", { class: "also" },
      el("summary", { text: `Also stated in ${also.length} other ${also.length === 1 ? "document" : "documents"}` }),
      el("ul", {}, also.map((o) => el("li", { text: `${prettyDoc(o.document)} · ${pageText(o.pages)}` })))) : null);
}
function entryNode(e) {
  return el("section", { class: "q" },
    el("h2", {}, el("span", { class: "tag", text: ABOUT_LABEL[e.about] || e.about.toUpperCase() }), e.query),
    e.supporting || e.refuting ? el("details", { class: "also looks-for" },
      el("summary", { text: "What we looked for" }),
      el("ul", {},
        e.supporting ? el("li", { text: "Supporting evidence would say: " + e.supporting }) : null,
        e.refuting ? el("li", { text: "Refuting evidence would say: " + e.refuting }) : null)) : null,
    e.findings.map(findingNode),
    e.error ? el("p", { class: "errline", text: "The model could not answer this question (" + e.error + ")." })
      : !e.findings.length ? el("p", { class: "empty", text: "No verified evidence in the indexed documents." }) : null);
}
function renderEvidence(claim, entries, state) {
  const panel = clear($("panel-evidence"));
  panel.append(
    el("div", { class: "sheet-head mono" }, el("span", { text: "EVIDENCE FROM OFFICIAL DOCUMENTS" }),
      el("span", { text: "EVERY QUOTE VERIFIED AGAINST THE SOURCE" })),
    el("p", { class: "claim-text small", text: claim }));
  if (state.running) {
    const pct = state.total ? Math.round((100 * state.done) / state.total) : 5;
    panel.append(el("div", { class: "progress", role: "status" },
      el("span", { class: "mono muted", text: state.total ? `SEARCHING OFFICIAL DOCUMENTS · ${state.done} OF ${state.total}` : "SEARCHING OFFICIAL DOCUMENTS…" }),
      el("div", { class: "bar" }, el("i", { style: `width:${pct}%` }))));
  }
  // one button per group; while the search runs all show, afterwards only groups that exist
  const groups = EVIDENCE_GROUPS.filter(([key]) => state.running || entries.some((e) => e.about === key));
  if (!groups.some(([key]) => key === evidenceGroup)) evidenceGroup = groups.length ? groups[0][0] : "claim";
  if (groups.length) {
    panel.append(el("div", { class: "chips", role: "tablist", "aria-label": "Evidence by question" },
      groups.map(([key, label]) => {
        const items = entries.filter((e) => e.about === key);
        const n = items.reduce((sum, e) => sum + e.findings.length, 0);
        return el("button", {
          class: "chip", type: "button", role: "tab", "aria-selected": key === evidenceGroup ? "true" : "false",
          onclick: () => { evidenceGroup = key; renderEvidence(claim, entries, state); },
        }, label, el("span", { class: "count mono", text: items.length ? String(n) : "…" }));
      })));
  }
  if (state.notice) panel.append(el("p", { class: "empty", role: "status", text: state.notice }));
  const shown = entries.filter((e) => e.about === evidenceGroup);
  const body = el("div", { class: "rows" }, shown.length || !state.running ? shown.map(entryNode)
    : el("p", { class: "loading", role: "status", text: "Searching this part…", style: "margin-top:24px" }));
  panel.append(body);
  if (state.error) renderError(panel, "Could not complete the evidence search: " + state.error, state.retry);
  const total = entries.reduce((n, e) => n + e.findings.length, 0);
  const badge = $("evidence-badge");
  badge.hidden = state.running || state.error ? true : !total;
  badge.textContent = total;
}

function pollEvidence(jobId, claim, myRun, retry) {
  clearTimeout(pollTimer);
  const tick = async () => {
    if (myRun !== run) return;
    try {
      const j = await api("/api/evidence/" + jobId);
      if (myRun !== run) return;
      const running = j.status === "running";
      const entries = j.status === "done" ? j.result.evidence : j.entries;
      renderEvidence(claim, entries, { running, done: j.done, total: j.total, error: j.status === "error" ? j.error : null, retry,
        notice: j.status === "done" ? j.result.plan_error : null });
      if (running) pollTimer = setTimeout(tick, 1500);
    } catch (err) {
      if (myRun === run) renderEvidence(claim, [], { running: false, error: err.message, retry });
    }
  };
  tick();
}

/* ---------- flow ---------- */
async function startEvidence(analysis, myRun) {
  const claim = analysis.claim;
  const retry = () => startEvidence(analysis, myRun);
  renderEvidence(claim, [], { running: true, done: 0, total: 0 });
  try {
    const { job } = await api("/api/evidence", { analysis });
    pollEvidence(job, claim, myRun, retry);
  } catch (err) {
    if (myRun === run) renderEvidence(claim, [], { running: false, error: err.message, retry });
  }
}

async function analyseClaim(claim) {
  const myRun = ++run;
  clearTimeout(pollTimer);
  $("home").hidden = true; $("result").hidden = false; $("new-claim").hidden = false; $("tagline").hidden = true;
  $("evidence-badge").hidden = true;
  evidenceGroup = "claim";
  clear($("panel-evidence"));
  showTab("debate");
  renderDebateLoading(claim);
  try {
    const analysis = await api("/api/analyze", { claim });
    if (myRun !== run) return;
    renderDebate(analysis);
    startEvidence(analysis, myRun);           // evidence loads in the background
  } catch (err) {
    if (myRun !== run) return;
    clear($("panel-debate")).append(el("h1", { class: "claim-text", text: claim }));
    renderError($("panel-debate"), err.message, () => analyseClaim(claim));
  }
}

function reset() {
  run++; clearTimeout(pollTimer);
  $("result").hidden = true; $("home").hidden = false; $("new-claim").hidden = true; $("tagline").hidden = false;
  $("claim").focus();
}

$("claim-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const claim = $("claim").value.trim();
  if (claim.length >= 3) analyseClaim(claim);
});
$("claim").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("claim-form").requestSubmit(); }
});
$("new-claim").onclick = reset;
document.querySelector(".brand").addEventListener("click", (e) => { e.preventDefault(); reset(); });

api("/api/health").then((h) => {
  if (!h.index_ready) {
    const n = $("index-notice");
    n.textContent = "The document index is not ready: " + (h.message || "run `claims index`") + " You can still analyse claims, but the evidence tab will be empty.";
    n.hidden = false;
  }
}).catch(() => {});