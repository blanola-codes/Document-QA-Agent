"use strict";

const $ = (id) => document.getElementById(id);
const MAX_TRIPLES_SHOWN = 300;
let allTriples = [];

// ---------- helpers ----------
async function api(url, options) {
  const response = await fetch(url, options);
  let data = {};
  try { data = await response.json(); } catch (e) { /* non-JSON error page */ }
  if (!response.ok) throw new Error(data.error || "Something went wrong (" + response.status + ").");
  return data;
}

function setMessage(text, kind) {
  const el = $("upload-msg");
  el.textContent = text;
  el.className = "msg " + (kind || "");
}

// ---------- upload ----------
const dropzone = $("dropzone");
const fileInput = $("file-input");

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
["dragenter", "dragover"].forEach((name) =>
  dropzone.addEventListener(name, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach((name) =>
  dropzone.addEventListener(name, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
  fileInput.value = "";
});
$("sample-btn").addEventListener("click", async () => {
  setMessage("Loading sample…");
  try { onLoaded(await api("/api/sample", { method: "POST" })); }
  catch (error) { setMessage(error.message, "error"); }
});

async function uploadFile(file) {
  setMessage("Building knowledge base…");
  const form = new FormData();
  form.append("file", file);
  try { onLoaded(await api("/api/upload", { method: "POST", body: form })); }
  catch (error) { setMessage(error.message, "error"); }
}

// ---------- after a document is loaded ----------
async function onLoaded(info) {
  setMessage("Loaded " + info.filename, "ok");
  $("status").classList.add("online");
  $("status-text").textContent = "Knowledge base ready";
  $("stat-records").textContent = info.records;
  $("stat-triples").textContent = info.triples;
  $("stat-columns").textContent = info.columns.length;
  $("stat-order").textContent = info.order_column || "none";
  ["stats", "qa-card", "kb-card", "graph-card"].forEach((id) => { $(id).hidden = false; });
  $("answer-box").hidden = true;
  $("history").textContent = "";
  $("history-wrap").hidden = true;

  try {
    const [knowledge, graph] = await Promise.all([api("/api/knowledge"), api("/api/graph")]);
    allTriples = knowledge.triple_list;
    renderTriples();
    renderGraph(graph);
    renderExamples(info, knowledge.triple_list);
  } catch (error) {
    setMessage(error.message, "error");
  }
}

// ---------- triples table ----------
$("triple-filter").addEventListener("input", renderTriples);

function renderTriples() {
  const needle = $("triple-filter").value.trim().toLowerCase();
  const matches = allTriples.filter((t) =>
    !needle || (t.subject + " " + t.relation + " " + t.object).toLowerCase().includes(needle));
  const body = $("triple-body");
  body.textContent = "";
  matches.slice(0, MAX_TRIPLES_SHOWN).forEach((t) => {
    const row = document.createElement("tr");
    [t.subject, t.relation, t.object].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
  $("triple-note").textContent = matches.length > MAX_TRIPLES_SHOWN
    ? "Showing the first " + MAX_TRIPLES_SHOWN + " of " + matches.length + " triples. Use the filter to narrow down."
    : matches.length + " triple" + (matches.length === 1 ? "" : "s") + " shown.";
}

// ---------- ordering graph (SVG, built without innerHTML) ----------
function svgEl(name, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
  return el;
}

function renderGraph(graph) {
  const box = $("graph");
  box.textContent = "";
  if (!graph.order_column || graph.nodes.length === 0) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "This document has no ordering column (such as order, position, sequence or rank), so no graph was built.";
    box.appendChild(p);
    return;
  }
  // Order nodes by following the edges from the first node.
  const next = new Map(graph.edges.map((e) => [e.from, e.to]));
  const targets = new Set(graph.edges.map((e) => e.to));
  const start = graph.nodes.find((n) => !targets.has(n)) || graph.nodes[0];
  const ordered = [];
  for (let n = start; n !== undefined && !ordered.includes(n); n = next.get(n)) ordered.push(n);

  const W = 120, H = 42, GX = 50, GY = 64, PAD = 20;
  const cols = Math.min(ordered.length, 5);
  const rows = Math.ceil(ordered.length / cols);
  const width = PAD * 2 + cols * W + (cols - 1) * GX;
  const height = PAD * 2 + rows * H + (rows - 1) * GY;

  const position = ordered.map((_, i) => {
    const row = Math.floor(i / cols);
    let col = i % cols;
    if (row % 2 === 1) col = cols - 1 - col;      // snake layout keeps arrows short
    return { x: PAD + col * (W + GX), y: PAD + row * (H + GY) };
  });

  const svg = svgEl("svg", { viewBox: "0 0 " + width + " " + height, width: width, height: height, role: "img" });
  svg.appendChild(svgEl("title")).textContent = "Ordering graph of " + ordered.length + " records";
  const defs = svgEl("defs");
  const marker = svgEl("marker", { id: "arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
  marker.appendChild(svgEl("path", { d: "M0,0 L10,5 L0,10 z", fill: "currentColor", style: "color: var(--muted)" }));
  defs.appendChild(marker);
  svg.appendChild(defs);

  for (let i = 0; i < ordered.length - 1; i++) {
    const a = position[i], b = position[i + 1];
    const ax = a.x + W / 2, ay = a.y + H / 2, bx = b.x + W / 2, by = b.y + H / 2;
    let x1 = ax, y1 = ay, x2 = bx, y2 = by;
    if (ay === by) { const dir = bx > ax ? 1 : -1; x1 = ax + dir * W / 2; x2 = bx - dir * W / 2; }
    else { y1 = ay + H / 2; y2 = by - H / 2; }
    svg.appendChild(svgEl("line", { class: "edge", x1: x1, y1: y1, x2: x2, y2: y2, "marker-end": "url(#arrow)" }));
  }
  ordered.forEach((name, i) => {
    const p = position[i];
    svg.appendChild(svgEl("rect", { class: "node", x: p.x, y: p.y, width: W, height: H, rx: 10 }));
    const label = svgEl("text", { x: p.x + W / 2, y: p.y + H / 2 + 5, "text-anchor": "middle" });
    label.textContent = name.length > 14 ? name.slice(0, 13) + "…" : name;
    svg.appendChild(label);
  });
  box.appendChild(svg);
}

// ---------- example questions ----------
function renderExamples(info, triples) {
  const box = $("examples");
  box.textContent = "";
  const subject = triples.length ? triples[0].subject : null;
  if (!subject) return;
  const fields = info.columns.filter((c) => c !== info.entity_column).slice(0, 2);
  const examples = fields.map((c) =>
    "What is the " + c.replace(/_(km|au|m|kg)$/i, "").replace(/_/g, " ") + " of " + subject + "?");
  examples.push("What is the temperature of " + subject + "?");
  examples.forEach((text) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = text;
    chip.addEventListener("click", () => { $("question").value = text; $("ask-form").requestSubmit(); });
    box.appendChild(chip);
  });
}

// ---------- asking questions ----------
$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = $("question").value.trim();
  if (!question) return;
  try {
    const result = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question }),
    });
    showAnswer(result);
  } catch (error) {
    showAnswer({ answer: error.message, type: "error", trace: [], time_ms: null, question: question });
  }
});

function showAnswer(result) {
  const box = $("answer-box");
  box.hidden = false;
  box.classList.toggle("notfound", result.type === "not found" || result.type === "error");
  $("answer-text").textContent = result.answer;
  $("answer-type").textContent = result.type;
  $("answer-time").textContent = result.time_ms === null ? "" : "Response time: " + result.time_ms + " ms";
  const trace = $("answer-trace");
  trace.textContent = "";
  result.trace.forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    trace.appendChild(li);
  });

  const history = $("history");
  const item = document.createElement("li");
  item.textContent = result.question + " → " + result.answer;
  history.prepend(item);
  while (history.children.length > 10) history.removeChild(history.lastChild);
  $("history-wrap").hidden = false;
}

// ---------- evaluation ----------
$("eval-btn").addEventListener("click", runEvaluation);

function addCell(row, text, className) {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  row.appendChild(cell);
}

async function runEvaluation() {
  const msg = $("eval-msg");
  msg.textContent = "Running…";
  msg.className = "msg";
  try {
    const data = await api("/api/evaluate?suite=" + encodeURIComponent($("suite-select").value));
    const m = data.metrics;
    const tiles = [
      [m.accuracy + "%", "Answer accuracy (" + m.correct + "/" + m.total + ")"],
      [m.coverage + "%", "Query coverage (" + m.supported_answered + "/" + m.supported_total + " supported)"],
      [m.unsupported_total ? m.unsupported_rejected + "/" + m.unsupported_total : "–", "Unsupported questions rejected"],
      [m.reasoning_accuracy + "%", "Trace supports answer (" + m.reasoning_correct + "/" + m.total + ")"],
      [m.avg_time_ms + " ms", "Average response time"],
      [m.max_time_ms + " ms", "Slowest response"],
    ];
    const stats = $("eval-stats");
    stats.textContent = "";
    tiles.forEach(([value, label]) => {
      const tile = document.createElement("div");
      tile.className = "stat";
      const num = document.createElement("span");
      num.className = "num";
      num.textContent = value;
      const lab = document.createElement("span");
      lab.className = "label";
      lab.textContent = label;
      tile.append(num, lab);
      stats.appendChild(tile);
    });

    const cats = $("eval-cats");
    cats.textContent = "";
    Object.entries(m.by_category).forEach(([name, entry]) => {
      const row = document.createElement("tr");
      addCell(row, name);
      addCell(row, entry.correct + " / " + entry.total);
      addCell(row, entry.accuracy + "%");
      cats.appendChild(row);
    });

    const body = $("eval-body");
    body.textContent = "";
    data.rows.forEach((r) => {
      const row = document.createElement("tr");
      addCell(row, r["No"]);
      addCell(row, r["Question"]);
      addCell(row, r["System answer"]);
      addCell(row, r["Correct"] ? "✓ Pass" : "✗ Fail", r["Correct"] ? "pass" : "fail");
      addCell(row, r["Trace supports answer"] ? "✓" : "✗", r["Trace supports answer"] ? "pass" : "fail");
      addCell(row, r["Response time (ms)"]);
      body.appendChild(row);
    });

    $("eval-note").textContent = "Test file: " + data.test_file +
      ". The trace check is an automatic rule-based check, not a proof of correctness.";
    $("eval-results").hidden = false;
    msg.textContent = "Done.";
    msg.className = "msg ok";
  } catch (error) {
    msg.textContent = error.message;
    msg.className = "msg error";
  }
}
