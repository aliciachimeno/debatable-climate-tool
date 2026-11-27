import { detectServer, createServerBackend } from "./js/server-backend.js";
import { createBrowserBackend } from "./js/browser-backend.js";
import { initSettings } from "./js/settings.js";

const $ = (id) => document.getElementById(id);
const TYPE_LABEL = {
  descriptive_factual: "Descriptive / factual", causal_attribution: "Causal attribution",
  predictive: "Predictive", policy_value: "Policy / value",
};
const ABOUT_LABEL = { claim: "THE CLAIM", implied_argument: "IMPLIED ARGUMENT", ambiguity: "AMBIGUITY", assumption: "ASSUMPTION" };
const STANCE_LABEL = { supports: "Supports this", refutes: "Contradicts this", context: "Context" };
// Evidence is shown one group at a time: the claim first, the rest behind a button.
const EVIDENCE_GROUPS = [["claim", "The claim"], ["ambiguity", "Ambiguities"],
  ["assumption", "Assumptions"], ["implied_argument", "Implied argument"]];
let evidenceGroup = "claim";

let run = 0;            // increments with every new claim, so stale responses are ignored
let abort = null;       // cancels the requests of the claim being replaced
let backend = null;     // server (claims serve) or browser (GitHub Pages)
let settings = null;    // the Language model box; only in browser mode

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
  rows.push(row("IMPLIED ARGUMENT", el("p", { text: a.implied_argument })));   // always last
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

function referenceNode(f) {
  const text = `${f.label || prettyDoc(f.document)} · ${pageText(f.pages)}`;
  return /^https:\/\//.test(f.url || "")
    ? el("a", { href: f.url, target: "_blank", rel: "noopener noreferrer", text })
    : el("span", { text });
}

/* ---------- evidence chain: what the quote itself cites (papers, chapter sections, figures) ---------- */
const matchNote = (c) => (c >= 1 ? "Exact match in the reference list" : "Likely match in the reference list");
const UNLINKED_NOTE = { not_indexed: "not in the indexed documents", not_found: "not found", no_reference_list: "no reference list" };
const isLinked = (x) => x.status === "resolved" || x.status === "ambiguous";

function safeLink(url, text) {
  return /^https:\/\//.test(url || "") ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text }) : null;
}
function chainCard(kind, tag, label, sub, note, body) {
  return el("details", { class: "cnode " + kind },
    el("summary", {},
      el("span", { class: "ctag", text: tag }),
      el("span", { class: "clabel", text: label }),
      sub ? el("span", { class: "csub", text: sub }) : null,
      note ? el("span", { class: "cnote", text: note }) : null),
    el("div", { class: "cbody" }, body.filter(Boolean)));
}
function referenceBody(r) {
  return [el("p", { text: r.text }),
    el("p", { class: "clinks" }, safeLink(r.doi_url, "DOI ↗"), safeLink(r.url, `Reference list · ${pageText([r.page])} ↗`))];
}
function paperCard(p) {
  const tag = p.type === "assessment" ? "IPCC REPORT" : "STUDY";
  if (p.status === "ambiguous") {
    return chainCard("paper", tag, p.label, "Several possible matches", "Not sure which one",
      (p.candidates || []).map((c) => el("div", { class: "cand" }, referenceBody(c))));
  }
  const r = p.reference;
  return chainCard("paper", tag, p.label, r.title.length > 110 ? r.title.slice(0, 110).trimEnd() + "…" : r.title,
    matchNote(p.confidence), referenceBody(r));
}
function sectionCard(s) {
  return chainCard("sec", "SECTION", s.label, s.title || "", "",
    [el("p", { class: "clinks" }, safeLink(s.url, `Open in the report · ${pageText([s.page])} ↗`))]);
}
function figureCard(f) {
  const tag = (f.kind || "figure").toUpperCase();
  return chainCard("fig", tag, f.label, f.title || "", "",
    [el("p", { class: "clinks" }, safeLink(f.url, `Open the page · ${pageText([f.page])} ↗`),
       safeLink(f.figure_url, "Figure ↗"), safeLink(f.data_url, "Data ↗"), safeLink(f.code_url, "Code ↗"),
       safeLink(f.index_url, "All AR6 WGI figures ↗"))]);
}
function chainColumn(title, kind, cards) {
  return cards.length ? el("div", { class: "ccol " + kind }, el("h3", { text: title }), cards) : null;
}
function provenanceNode(p) {
  if (!p) return null;
  const papers = p.papers.filter(isLinked), sections = p.sections.filter(isLinked), figures = p.figures.filter(isLinked);
  const unlinked = [...p.sections, ...p.figures, ...p.papers].filter((x) => !isLinked(x));
  if (!papers.length && !sections.length && !figures.length && !unlinked.length) return null;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const count = [papers.length && plural(papers.length, "reference", "references"),
    sections.length && plural(sections.length, "section", "sections"),
    figures.length && plural(figures.length, "figure or table", "figures and tables")].filter(Boolean).join(" · ");
  return el("details", { class: "chain" },
    el("summary", {}, el("span", { class: "mono", text: "EVIDENCE CHAIN" }), el("span", { class: "ccount", text: count || "nothing linked" })),
    el("div", { class: "cgrid" },
      chainColumn("Chapter text", "sec", sections.map(sectionCard)),
      chainColumn("Studies cited", "paper", papers.map(paperCard)),
      chainColumn("Figures & data", "fig", figures.map(figureCard))),
    unlinked.length ? el("p", { class: "cunlinked", text: "Also cited, not linked here: " +
      unlinked.map((x) => `${x.label} (${UNLINKED_NOTE[x.status] || x.status})`).join("; ") + "." }) : null);
}

function findingNode(f) {
  const strength = [f.likelihood, f.confidence && `${f.confidence} confidence`, f.stated_as_fact && "stated as fact"].filter(Boolean);
  const also = f.also_in || [];
  return el("div", { class: "finding" },
    el("p", { class: "stmt", text: f.statement }),
    el("blockquote", { text: `“${f.quote}”` }),
    el("div", { class: "meta" },
      STANCE_LABEL[f.stance] ? el("span", { class: "stance " + f.stance, text: STANCE_LABEL[f.stance] }) : null,
      referenceNode(f),
      strength.length ? el("span", { class: "strength", text: strength.join(" · ") }) : null),
    provenanceNode(f.provenance),
    also.length ? el("details", { class: "also" },
      el("summary", { text: `Also stated in ${also.length} other ${also.length === 1 ? "document" : "documents"}` }),
      el("ul", {}, also.map((o) => el("li", { text: `${prettyDoc(o.document)} · ${pageText(o.pages)}` })))) : null);
}
function entryNode(e) {
  return el("section", { class: "q" },
    el("h2", {}, el("span", { class: "tag", text: ABOUT_LABEL[e.about] || e.about.toUpperCase() }), e.query),
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
      el("span", { class: "mono muted", text: state.total ? `SEARCHING OFFICIAL DOCUMENTS · ${state.done} OF ${state.total}` : (state.status || "SEARCHING OFFICIAL DOCUMENTS…").toUpperCase() }),
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

/* ---------- flow ---------- */
const aborted = (err) => err && err.name === "AbortError";

async function startEvidence(analysis, myRun, signal) {
  const claim = analysis.claim;
  let entries = [];
  const retry = () => startEvidence(analysis, myRun, signal);
  renderEvidence(claim, entries, { running: true, done: 0, total: 0 });
  try {
    await backend.evidence(analysis, {
      signal,
      onUpdate: (u) => {
        if (myRun !== run) return;
        entries = u.entries;
        renderEvidence(claim, entries, { ...u, retry });
      },
    });
  } catch (err) {
    if (myRun !== run || aborted(err)) return;
    renderEvidence(claim, entries, { running: false, error: err.message, retry });
  }
}

async function analyseClaim(claim) {
  await backendReady;
  const myRun = ++run;
  if (abort) abort.abort();
  abort = new AbortController();
  const { signal } = abort;
  $("home").hidden = true; $("result").hidden = false; $("new-claim").hidden = false; $("tagline").hidden = true;
  $("evidence-badge").hidden = true;
  evidenceGroup = "claim";
  clear($("panel-evidence"));
  showTab("debate");

  if (backend.needsSettings && !settings.ready()) {
    clear($("panel-debate")).append(el("h1", { class: "claim-text", text: claim }));
    renderError($("panel-debate"), "Connect a language model first: open the “Language model” box at the top right, add your API key and the model name, then try again.", () => analyseClaim(claim));
    settings.open();
    return;
  }
  renderDebateLoading(claim);
  try {
    backend.prepare();               // browser mode: start loading the index while the model reads the claim
    const analysis = await backend.analyze(claim, { signal });
    if (myRun !== run) return;
    renderDebate(analysis);
    startEvidence(analysis, myRun, signal);          // evidence loads in the background
  } catch (err) {
    if (myRun !== run || aborted(err)) return;
    clear($("panel-debate")).append(el("h1", { class: "claim-text", text: claim }));
    renderError($("panel-debate"), err.message, () => analyseClaim(claim));
  }
}

function reset() {
  run++;
  if (abort) abort.abort();
  $("result").hidden = true; $("home").hidden = false; $("new-claim").hidden = true; $("tagline").hidden = false;
  $("claim").focus();
}

function showNotice(text) {
  const n = $("index-notice");
  n.textContent = text;
  n.hidden = !text;
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

/* ---------- which backend? ---------- */
const NEEDS_MODEL = "This page has no server. Connect your own language model with the “Language model” box at the top right; your key stays in your browser.";

const backendReady = (async () => {
  const health = await detectServer();
  if (health) {                                       // `claims serve`: the server owns the model settings
    backend = createServerBackend(health);
    $("llm").hidden = true;
    showNotice(backend.notice);
    return;
  }
  settings = initSettings();
  backend = createBrowserBackend({ getConfig: settings.get });
  const refresh = () => showNotice(settings.ready() ? "" : NEEDS_MODEL);
  $("llm-form").addEventListener("input", refresh);
  refresh();
})();
