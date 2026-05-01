const sampleText = `A biotech company announced Series B financing to advance a PD-1 combination therapy through phase 2 and expand an autoimmune pipeline. Strategic and financial investors participated in the round. Analysts said the financing may improve the company's research runway, while clinical failure, regulatory approval, and market competition remain key risks.`;

const state = {
  lastResult: null,
  documentsOffset: 0,
  documentsLimit: 25,
  documentsHasMore: false,
  selectedDocumentId: "",
  selectedDocumentSource: "",
  runsOffset: 0,
  runsLimit: 20,
  runsHasMore: false,
  sources: [],
  sourceProfiles: [],
  selectedProfile: "core_intelligence",
  sourceState: [],
  sourceStateData: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function setLoading(button, loading) {
  if (!button) {
    return;
  }
  button.disabled = loading;
  button.dataset.originalText ||= button.textContent;
  button.textContent = loading ? "Processing" : button.dataset.originalText;
}

async function requestJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.message || data.error || "request failed");
  }
  return data;
}

async function getJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.message || data.error || "request failed");
  }
  return data;
}

function renderResult(result) {
  state.lastResult = result;
  $("#result-json").textContent = JSON.stringify(result, null, 2);
  $("#summary-output").textContent =
    result.summary || result.reason || result.error || "Waiting for analysis.";

  const sentiment = result.sentiment || {};
  const risk = result.risk || {};
  $("#sentiment-label").textContent = sentiment.label || "-";
  $("#risk-severity").textContent = risk.severity || "-";

  const terms = result.top_terms || [];
  const events = result.events || [];
  const routeSteps = result.recommended_steps || [];
  $("#term-count").textContent = String(terms.length || events.length || routeSteps.length || 0);

  const chips = $("#chips");
  chips.innerHTML = "";
  const chipValues = [
    ...terms.map(([term, count]) => `${term} × ${count}`),
    ...events.map((event) => event.title || event.event_type).filter(Boolean),
    ...routeSteps,
  ];
  for (const value of chipValues.slice(0, 18)) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = value;
    chips.appendChild(chip);
  }
}

function renderRecords(containerSelector, records, mode) {
  const container = $(containerSelector);
  container.innerHTML = "";
  if (!records.length) {
    const empty = document.createElement("p");
    empty.className = "record-summary";
    empty.textContent = "No records yet.";
    container.appendChild(empty);
    return;
  }

  for (const record of records.slice().reverse()) {
    const item = document.createElement("article");
    item.className = "record-item";

    const title = document.createElement("h3");
    const doc = record.document || {};
    const raw = doc.raw || {};
    const insight = record.insight || {};
    title.textContent =
      mode === "feedback"
        ? `${record.decision || "feedback"} · ${record.document_id || "-"}`
        : raw.title || insight.summary || raw.document_id || "Untitled document";

    const meta = document.createElement("p");
    meta.className = "record-meta";
    meta.textContent =
      mode === "feedback"
        ? `${record.reviewer || "-"} · ${record.created_at || ""}`
        : `${raw.source?.name || "-"} · ${record.provider || "-"} · ${record.created_at || ""}`;

    const summary = document.createElement("p");
    summary.className = "record-summary";
    summary.textContent =
      mode === "feedback"
        ? record.comment || "No comment"
        : insight.summary || doc.text || "No summary";

    item.append(title, meta, summary);
    item.addEventListener("click", () => {
      renderResult(record.insight || record);
      if (mode !== "feedback") {
        activatePanel("document");
      }
    });
    container.appendChild(item);
  }
}

function renderDocumentTable(data) {
  const rows = data.items || [];
  const filteredTotal = data.filtered_total ?? data.total ?? rows.length;
  $("#documents-count").textContent =
    `${rows.length} records / ${filteredTotal} filtered / ${data.total ?? rows.length} total`;
  state.documentsHasMore = Boolean(data.has_more);
  $("#documents-prev-button").disabled = (data.offset || 0) <= 0;
  $("#documents-next-button").disabled = !state.documentsHasMore;
  $("#documents-page-label").textContent =
    `Page ${Math.floor((data.offset || 0) / (data.limit || state.documentsLimit)) + 1}`;
  updateFacetSelect("#documents-source-filter", data.facets?.sources || []);
  updateFacetSelect("#documents-event-filter", data.facets?.event_types || []);
  updateFacetSelect("#documents-risk-filter", data.facets?.risks || []);

  const body = $("#documents-table-body");
  body.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.textContent = "No records yet.";
    tr.appendChild(td);
    body.appendChild(tr);
    renderDocumentDetail(null);
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(titleCell(row));
    tr.appendChild(textCell(row.source || "-"));
    tr.appendChild(textCell(row.event_title || row.event_type || "-"));
    tr.appendChild(badgeCell(row.risk || "-"));
    tr.appendChild(qualityCell(row));
    tr.appendChild(textCell(row.model || row.provider || "-"));
    tr.appendChild(textCell(shortDate(row.created_at)));
    tr.addEventListener("click", async () => {
      await selectDocument(row, tr);
    });
    body.appendChild(tr);
  }
}

function renderRunsTable(data) {
  const rows = data.items || [];
  const summary = data.summary || {};
  state.runsHasMore = Boolean(data.has_more);
  $("#runs-success").textContent = String(summary.success ?? 0);
  $("#runs-failed").textContent = String(summary.failed ?? 0);
  $("#runs-latest-status").textContent = summary.latest_status || "-";
  $("#runs-latest-time").textContent = shortDate(summary.latest_completed_at);
  $("#runs-selected").textContent = String(summary.selected ?? 0);
  $("#runs-analyzed").textContent = String(summary.analyzed ?? 0);
  $("#runs-skipped").textContent = String(summary.skipped_seen ?? 0);
  $("#runs-count").textContent =
    `${rows.length} runs / ${data.total ?? rows.length} total`;
  $("#runs-prev-button").disabled = (data.offset || 0) <= 0;
  $("#runs-next-button").disabled = !state.runsHasMore;
  $("#runs-page-label").textContent =
    `Page ${Math.floor((data.offset || 0) / (data.limit || state.runsLimit)) + 1}`;

  const body = $("#runs-table-body");
  body.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.textContent = "No run records yet.";
    tr.appendChild(td);
    body.appendChild(tr);
    $("#run-detail").textContent = "Select a run to view details.";
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(titleRunCell(row));
    tr.appendChild(statusCell(row.status || "-"));
    tr.appendChild(textCell(`${Number(row.duration_seconds || 0).toFixed(2)}s`));
    tr.appendChild(textCell(runSources(row)));
    tr.appendChild(textCell(runResultSummary(row)));
    tr.appendChild(textCell(shortDate(row.completed_at)));
    tr.addEventListener("click", () => {
      $$("#runs-table-body tr").forEach((item) => item.classList.remove("selected"));
      tr.classList.add("selected");
      $("#run-detail").textContent = JSON.stringify(row, null, 2);
    });
    body.appendChild(tr);
  }
}

function renderSourceState(data) {
  const rows = data.items || [];
  state.sourceState = rows;
  state.sourceStateData = data;
  const summary = data.summary || {};
  const filteredRows = filterSourceStateRows(rows);
  $("#source-state-count").textContent =
    `${filteredRows.length} visible / ${rows.length} sources · ${summary.success ?? 0} healthy · ${summary.failed ?? 0} failed · ${summary.seen_documents ?? 0} seen documents`;
  $("#source-state-backend").textContent = data.backend || "-";
  $("#source-state-health").textContent = `${Math.round(Number(summary.health_ratio || 0) * 100)}%`;
  $("#source-state-selected").textContent = String(summary.last_selected ?? 0);
  $("#source-state-skipped").textContent = String(summary.last_skipped_seen ?? 0);
  renderSourceAlerts(data.alerts || []);
  updateSourceStateCollectorFilter(rows);

  const body = $("#source-state-table-body");
  body.innerHTML = "";
  if (!filteredRows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.textContent = rows.length ? "No sources match the current filters." : "No source state yet.";
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }

  for (const row of filteredRows) {
    const tr = document.createElement("tr");
    tr.appendChild(sourceStateNameCell(row));
    tr.appendChild(statusCell(row.last_status || "never_run"));
    tr.appendChild(sourceStateDiagnosisCell(row));
    tr.appendChild(textCell(String(row.seen_count ?? 0)));
    tr.appendChild(textCell(String(row.last_selected ?? 0)));
    tr.appendChild(textCell(String(row.last_analyzed ?? 0)));
    tr.appendChild(textCell(String(row.last_skipped_seen ?? 0)));
    tr.appendChild(textCell(shortDate(row.last_completed_at || row.updated_at)));
    tr.addEventListener("click", () => {
      $$("#source-state-table-body tr").forEach((item) => item.classList.remove("selected"));
      tr.classList.add("selected");
      $("#source-state-detail").textContent = JSON.stringify(row, null, 2);
    });
    body.appendChild(tr);
  }
}

function renderSourceAlerts(alerts) {
  const container = $("#source-state-alerts");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!alerts.length) {
    const item = document.createElement("article");
    item.className = "source-alert source-alert-ok";
    const title = document.createElement("strong");
    title.textContent = "No active source alerts";
    const message = document.createElement("span");
    message.textContent = "Collection health is clear for the current state file.";
    item.append(title, message);
    container.appendChild(item);
    return;
  }

  for (const alert of alerts.slice(0, 4)) {
    const item = document.createElement("article");
    item.className = `source-alert source-alert-${alert.level || "info"}`;
    const badge = document.createElement("span");
    badge.className = `badge alert-${alert.level || "info"}`;
    badge.textContent = alert.level || "info";
    const body = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${alert.title || "Source alert"} · ${alert.source || "-"}`;
    const message = document.createElement("span");
    message.textContent = alert.action || alert.message || "-";
    body.append(title, message);
    item.append(badge, body);
    container.appendChild(item);
  }
}

function renderBrief(brief) {
  $("#brief-output").textContent = brief.markdown || JSON.stringify(brief, null, 2);
  const summary = brief.summary || "";
  const grid = $("#brief-summary-grid");
  grid.innerHTML = "";
  const topRisk = (brief.risk_counts || [])[0]?.name || "-";
  const topEvent = (brief.event_counts || [])[0]?.name || "-";
  const topSource = (brief.source_counts || [])[0]?.name || "-";
  for (const [label, value] of [
    ["Documents", String(brief.document_count ?? 0)],
    ["Top Event", topEvent],
    ["Top Risk", topRisk],
    ["Top Source", topSource],
    ["Summary", summary],
  ]) {
    const card = document.createElement("article");
    card.className = "metric compact";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    card.append(span, strong);
    grid.appendChild(card);
  }
  const artifacts = brief.artifacts || {};
  if (artifacts.markdown || artifacts.json) {
    const card = document.createElement("article");
    card.className = "metric compact";
    const span = document.createElement("span");
    span.textContent = "Artifacts";
    const strong = document.createElement("strong");
    strong.textContent = [artifacts.markdown, artifacts.json].filter(Boolean).join(" · ");
    card.append(span, strong);
    grid.appendChild(card);
  }
}

function filterSourceStateRows(rows) {
  const status = $("#source-state-status-filter")?.value || "";
  const collector = $("#source-state-collector-filter")?.value || "";
  const query = ($("#source-state-query")?.value || "").trim().toLowerCase();
  return rows.filter((row) => {
    if (status && row.last_status !== status) {
      return false;
    }
    if (collector && row.collector !== collector) {
      return false;
    }
    if (!query) {
      return true;
    }
    return [row.source, row.category, row.kind, row.collector, row.failure_type, row.remediation_hint]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
}

function updateSourceStateCollectorFilter(rows) {
  const select = $("#source-state-collector-filter");
  if (!select) {
    return;
  }
  const current = select.value;
  const collectors = Array.from(new Set(rows.map((row) => row.collector || "feed"))).sort();
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All";
  select.appendChild(all);
  for (const collector of collectors) {
    const option = document.createElement("option");
    option.value = collector;
    option.textContent = collector;
    select.appendChild(option);
  }
  select.value = collectors.includes(current) ? current : "";
}

function sourceStateNameCell(row) {
  const td = document.createElement("td");
  const title = document.createElement("div");
  title.className = "table-title";
  title.textContent = row.source || "-";
  const subtext = document.createElement("div");
  subtext.className = "table-subtext";
  subtext.textContent = `${row.collector || "feed"} · ${row.category || "-"}`;
  td.append(title, subtext);
  return td;
}

function sourceStateDiagnosisCell(row) {
  const td = document.createElement("td");
  const type = row.failure_type || "none";
  const badge = document.createElement("span");
  badge.className = `badge diagnosis-${type}`;
  badge.textContent = type;
  const hint = document.createElement("div");
  hint.className = "table-subtext compact";
  hint.textContent = row.remediation_hint || row.last_error || "-";
  td.append(badge, hint);
  return td;
}

function titleRunCell(row) {
  const td = document.createElement("td");
  const title = document.createElement("div");
  title.className = "table-title";
  title.textContent = row.job_name || "job";
  const subtext = document.createElement("div");
  subtext.className = "table-subtext";
  subtext.textContent = row.run_id || "";
  td.append(title, subtext);
  return td;
}

function statusCell(value) {
  const td = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `badge status-${value}`;
  badge.textContent = value;
  td.appendChild(badge);
  return td;
}

function runSources(row) {
  const sources = row.metadata?.sources;
  if (Array.isArray(sources)) {
    return sources.slice(0, 4).join(", ") + (sources.length > 4 ? "..." : "");
  }
  return "-";
}

function runResultSummary(row) {
  if (row.error) {
    return row.error;
  }
  if (Array.isArray(row.result)) {
    const selected = row.result.reduce((total, item) => total + Number(item.selected || 0), 0);
    const analyzed = row.result.reduce((total, item) => total + Number(item.analyzed || 0), 0);
    return `${row.result.length} sources · ${selected} selected · ${analyzed} analyzed`;
  }
  if (row.result && Array.isArray(row.result.fetch)) {
    const selected = row.result.fetch.reduce((total, item) => total + Number(item.selected || 0), 0);
    const analyzed = row.result.fetch.reduce((total, item) => total + Number(item.analyzed || 0), 0);
    const documents = Number(row.result.brief?.document_count || 0);
    return `${row.result.fetch.length} sources · ${selected} selected · ${analyzed} analyzed · ${documents} brief docs`;
  }
  return row.result == null ? "-" : "ok";
}

function titleCell(row) {
  const td = document.createElement("td");
  const title = document.createElement("div");
  title.className = "table-title";
  title.textContent = row.title || "Untitled";
  const summary = document.createElement("div");
  summary.className = "table-subtext";
  summary.textContent = row.summary || row.url || "";
  td.append(title, summary);
  return td;
}

function textCell(value) {
  const td = document.createElement("td");
  td.textContent = value;
  return td;
}

function badgeCell(value) {
  const td = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `badge ${value}`;
  badge.textContent = value;
  td.appendChild(badge);
  return td;
}

function qualityCell(row) {
  const td = document.createElement("td");
  const quality = document.createElement("span");
  quality.className = `badge quality-${row.body_quality || "unknown"}`;
  quality.textContent = row.body_quality || "-";
  const meta = document.createElement("div");
  meta.className = "table-subtext compact";
  const method = row.extraction_method ? ` · ${row.extraction_method}` : "";
  meta.textContent = `${row.text_length || 0} chars${method}`;
  td.append(quality, meta);
  return td;
}

function updateFacetSelect(selector, options) {
  const select = $(selector);
  const current = select.value;
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All";
  select.appendChild(all);
  for (const option of options) {
    const element = document.createElement("option");
    element.value = option;
    element.textContent = option;
    select.appendChild(element);
  }
  select.value = options.includes(current) ? current : "";
}

function shortDate(value) {
  if (!value) {
    return "-";
  }
  return String(value).replace("T", " ").slice(0, 16);
}

async function runAnalysis(path, button) {
  const text = $("#document-input").value.trim();
  if (!text) {
    renderResult({ error: "Enter text to analyze." });
    return;
  }
  setLoading(button, true);
  try {
    renderResult(await requestJson(path, { text }));
  } catch (error) {
    renderResult({ error: error.message });
  } finally {
    setLoading(button, false);
  }
}

async function selectDocument(row, tableRow) {
  $$("#documents-table-body tr").forEach((item) => item.classList.remove("selected"));
  tableRow.classList.add("selected");
  state.selectedDocumentId = row.id || "";
  state.selectedDocumentSource = row.source || "";
  renderDocumentDetail({ loading: true, row });
  try {
    const params = new URLSearchParams({
      path: $("#documents-path").value,
      source: row.source || "",
    });
    const detail = await getJson(
      `/api/documents/${encodeURIComponent(row.id || "")}?${params.toString()}`,
    );
    renderDocumentDetail(detail);
    renderResult(detail.insight || detail.record || {});
  } catch (error) {
    renderDocumentDetail({ error: error.message, row });
  }
}

function renderDocumentDetail(detail) {
  const container = $("#document-detail");
  container.innerHTML = "";
  if (!detail) {
    const empty = document.createElement("div");
    empty.className = "detail-empty";
    empty.textContent = "Select a document to view details.";
    container.appendChild(empty);
    return;
  }
  if (detail.loading) {
    const loading = document.createElement("div");
    loading.className = "detail-empty";
    loading.textContent = "Loading details.";
    container.appendChild(loading);
    return;
  }
  if (detail.error) {
    const error = document.createElement("div");
    error.className = "detail-empty error";
    error.textContent = detail.error;
    container.appendChild(error);
    return;
  }

  const doc = detail.document || {};
  const row = detail.row || {};
  const quality = detail.quality || {};
  const header = document.createElement("div");
  header.className = "detail-header";

  const titleWrap = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = doc.title || row.title || "Untitled";
  const meta = document.createElement("p");
  meta.className = "record-meta";
  meta.textContent = [
    doc.source || row.source || "-",
    detail.provider || row.provider || "-",
    detail.model || row.model || "-",
    shortDate(detail.created_at || row.created_at),
  ]
    .filter(Boolean)
    .join(" · ");
  titleWrap.append(title, meta);

  const actionWrap = document.createElement("div");
  actionWrap.className = "detail-actions";
  if (doc.url) {
    const link = document.createElement("a");
    link.href = doc.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Open Source";
    actionWrap.appendChild(link);
  }
  const loadButton = document.createElement("button");
  loadButton.className = "ghost";
  loadButton.textContent = "Load Body";
  loadButton.addEventListener("click", () => {
    $("#document-input").value = doc.text || doc.text_preview || "";
    activatePanel("document");
  });
  actionWrap.appendChild(loadButton);
  header.append(titleWrap, actionWrap);

  const metrics = document.createElement("div");
  metrics.className = "detail-metrics";
  for (const [label, value] of [
    ["Quality", quality.label || "-"],
    ["Characters", String(quality.text_length ?? 0)],
    ["Words", String(quality.word_count ?? 0)],
    ["Method", quality.extraction_method || "-"],
    ["Cleaned", quality.html_cleaned ? "yes" : "no"],
    ["Ratio", quality.clean_ratio == null ? "-" : String(quality.clean_ratio)],
  ]) {
    const metric = document.createElement("article");
    metric.className = "metric compact";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    metric.append(span, strong);
    metrics.appendChild(metric);
  }

  const previewTitle = document.createElement("div");
  previewTitle.className = "section-title";
  previewTitle.textContent = "Body Preview";
  const preview = document.createElement("pre");
  preview.className = "document-preview";
  preview.textContent = doc.text_preview || doc.text || "No body text available.";

  container.append(header, metrics, previewTitle, preview);
}

function wireNavigation() {
  $$(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      activatePanel(button.dataset.panel);
    });
  });

  $$(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".tab").forEach((tab) => tab.classList.remove("active"));
      $$(".result-view").forEach((view) => view.classList.remove("active"));
      button.classList.add("active");
      $(`#result-${button.dataset.result}`).classList.add("active");
    });
  });
}

function activatePanel(panelName) {
  $$(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.panel === panelName);
  });
  $$(".panel").forEach((panel) => panel.classList.remove("active"));
  $(`#panel-${panelName}`).classList.add("active");
  const activeNav = $(`.nav-item[data-panel="${panelName}"]`);
  $("#panel-title").textContent = activeNav ? activeNav.textContent : "Workbench";
}

async function loadHealthAndConfig() {
  try {
    const health = await fetch("/api/health").then((response) => response.json());
    $("#health-dot").classList.toggle("ok", health.status === "ok");
    $("#health-text").textContent = health.status === "ok" ? "Local service online" : "Service warning";
  } catch {
    $("#health-text").textContent = "Service offline";
  }

  try {
    const config = await fetch("/api/config").then((response) => response.json());
    $("#config-provider").textContent = config.provider;
    $("#config-model").textContent = config.model;
    $("#config-base-url").textContent = config.base_url;
    $("#config-api-key").textContent = config.has_api_key ? "Configured" : "Missing";
  } catch {
    $("#config-provider").textContent = "Unavailable";
  }

  await loadSources();
  await loadSourceProfiles();
  await loadSourceState();
  await loadDiagnostics();
}

async function loadSources() {
  try {
    const data = await getJson("/api/sources");
    state.sources = data.items || [];
    renderSourceOptions(state.sources);
  } catch (error) {
    const output = $("#job-output-json");
    if (output) {
      output.textContent = JSON.stringify({ error: error.message }, null, 2);
    }
  }
}

function renderSourceOptions(sources) {
  const select = $("#job-sources");
  if (!select) {
    return;
  }
  select.innerHTML = "";
  const selectedProfile = state.sourceProfiles.find((profile) => profile.name === state.selectedProfile);
  const defaults = new Set(
    selectedProfile?.source_names || [
      "fda_press_releases",
      "sec_biopharma_filings",
      "asx_biopharma_announcements",
    ],
  );
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source.name;
    option.textContent = `${source.name} · ${source.collector || "feed"} · ${source.category || "uncategorized"}`;
    option.disabled = !source.enabled;
    option.selected = defaults.has(source.name) && source.enabled;
    select.appendChild(option);
  }
}

async function loadSourceProfiles() {
  try {
    const data = await getJson("/api/source-profiles");
    state.sourceProfiles = data.items || [];
    if (!state.sourceProfiles.some((profile) => profile.name === state.selectedProfile)) {
      state.selectedProfile = state.sourceProfiles[0]?.name || "";
    }
    renderSourceProfiles();
    renderSourceOptions(state.sources);
  } catch (error) {
    state.sourceProfiles = [];
    const output = $("#job-output-json");
    if (output) {
      output.textContent = JSON.stringify({ error: error.message }, null, 2);
    }
  }
}

function renderSourceProfiles() {
  const container = $("#source-profile-strip");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  for (const profile of state.sourceProfiles) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `profile-button${profile.name === state.selectedProfile ? " active" : ""}`;
    button.dataset.profile = profile.name;

    const label = document.createElement("strong");
    label.textContent = profile.label || profile.name;
    const meta = document.createElement("span");
    meta.textContent = `${profile.source_names.length} sources · ${profile.category || "mixed"}`;
    button.append(label, meta);

    button.addEventListener("click", () => {
      applySourceProfile(profile.name);
    });
    container.appendChild(button);
  }
}

function applySourceProfile(profileName) {
  const profile = state.sourceProfiles.find((item) => item.name === profileName);
  if (!profile) {
    return;
  }
  state.selectedProfile = profile.name;
  $("#job-limit").value = String(profile.default_limit || 1);
  $("#job-analyze").checked = Boolean(profile.analyze);
  $("#job-fetch-details").checked = Boolean(profile.fetch_details);
  $("#job-clean-html").checked = Boolean(profile.clean_html_details);
  renderSourceProfiles();
  renderSourceOptions(state.sources);
  $("#job-output-json").textContent = JSON.stringify(
    {
      profile: profile.name,
      sources: profile.source_names,
      notes: profile.notes,
    },
    null,
    2,
  );
}

function matchingSourceProfile(selectedSources) {
  const selected = selectedSources.slice().sort().join("|");
  const profile = state.sourceProfiles.find((item) => item.source_names.slice().sort().join("|") === selected);
  return profile ? profile.name : "";
}

function selectedJobSources() {
  return Array.from($("#job-sources").selectedOptions).map((option) => option.value);
}

function jobPayload(overrides = {}) {
  const selectedSources = selectedJobSources();
  const matchingProfile = matchingSourceProfile(selectedSources);
  return {
    sources: selectedSources,
    profile: matchingProfile,
    limit: Number($("#job-limit").value || 1),
    analyze: $("#job-analyze").checked,
    fetch_details: $("#job-fetch-details").checked,
    clean_html_details: $("#job-clean-html").checked,
    incremental: $("#job-incremental").checked,
    state_path: $("#job-state-path").value,
    run_log: $("#runs-path").value,
    output: $("#job-output").value,
    archive_dir: "data/raw",
    graph_dir: "data/graph",
    ...overrides,
  };
}

async function refreshOperationalViews() {
  state.runsOffset = 0;
  renderRunsTable(await loadRuns());
  await loadSourceState();
  state.documentsOffset = 0;
  renderDocumentTable(await loadDocuments());
}

async function loadDiagnostics() {
  const output = $("#diagnostics-json");
  const grid = $("#diagnostics-grid");
  if (!output || !grid) {
    return;
  }
  try {
    const data = await getJson("/api/diagnostics");
    renderDiagnostics(data);
  } catch (error) {
    output.textContent = JSON.stringify({ error: error.message }, null, 2);
    grid.innerHTML = "";
    $("#diagnostics-status").textContent = "failed";
    $("#diagnostics-status").className = "badge status-failed";
  }
}

async function loadSourceState() {
  const input = $("#job-state-path");
  const path = input ? input.value : "data/runs/source_state.json";
  const params = new URLSearchParams({ path });
  const data = await getJson(`/api/source-state?${params.toString()}`);
  renderSourceState(data);
  return data;
}

async function loadSourceReport() {
  const params = new URLSearchParams({
    state_path: $("#job-state-path").value,
    run_log: $("#runs-path").value,
  });
  return getJson(`/api/source-report?${params.toString()}`);
}

function renderDiagnostics(data) {
  $("#diagnostics-json").textContent = JSON.stringify(data, null, 2);
  const status = data.status || "unknown";
  const statusBadge = $("#diagnostics-status");
  statusBadge.textContent = status;
  statusBadge.className = `badge status-${status}`;

  const grid = $("#diagnostics-grid");
  grid.innerHTML = "";
  const checks = data.checks || {};
  for (const [name, check] of Object.entries(checks)) {
    const card = document.createElement("article");
    card.className = "diagnostic-card";

    const header = document.createElement("div");
    header.className = "diagnostic-header";
    const title = document.createElement("h3");
    title.textContent = name;
    const badge = document.createElement("span");
    badge.className = `badge status-${check.status || "warning"}`;
    badge.textContent = check.status || "warning";
    header.append(title, badge);

    const facts = document.createElement("dl");
    facts.className = "diagnostic-facts";
    for (const [label, value] of diagnosticFacts(name, check)) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      facts.append(dt, dd);
    }

    const issues = document.createElement("div");
    issues.className = "diagnostic-issues";
    const issueList = Array.isArray(check.issues) ? check.issues : [];
    issues.textContent = issueList.length ? issueList.join(" | ") : "No issues detected.";

    card.append(header, facts, issues);
    grid.appendChild(card);
  }
}

function diagnosticFacts(name, check) {
  if (name === "llm") {
    return [
      ["Provider", check.provider || "-"],
      ["Model", check.model || "-"],
      ["API key", check.has_api_key ? "configured" : "missing"],
    ];
  }
  if (name === "storage") {
    return [
      ["Backend", check.backend || "-"],
      ["Driver", check.driver_available == null ? "-" : String(check.driver_available)],
      ["DSN", check.has_dsn == null ? "-" : String(check.has_dsn)],
    ];
  }
  if (name === "raw_archive") {
    return [
      ["Backend", check.backend || "-"],
      ["Bucket", check.bucket || "-"],
      ["Driver", check.driver_available == null ? "-" : String(check.driver_available)],
    ];
  }
  if (name === "graph") {
    return [
      ["Backend", check.backend || "-"],
      ["Path", check.path || "-"],
      ["URI", check.has_uri == null ? "-" : String(check.has_uri)],
      ["Driver", check.driver_available == null ? "-" : String(check.driver_available)],
    ];
  }
  if (name === "sources") {
    return [
      ["Total", String(check.total ?? 0)],
      ["Enabled", String(check.enabled ?? 0)],
      ["Disabled", String(check.disabled ?? 0)],
    ];
  }
  if (name === "docker") {
    return [
      ["Available", String(check.available ?? false)],
      ["Version", check.version || "-"],
      ["Compose", check.compose_version || "-"],
    ];
  }
  if (name === "git") {
    return [
      ["Branch", check.branch || "-"],
      ["Origin", check.origin || "-"],
      ["Changes", String(check.pending_changes ?? 0)],
    ];
  }
  return [
    ["Version", check.version || "-"],
    ["Executable", check.executable || "-"],
  ];
}

function wireActions() {
  $("#sample-button").addEventListener("click", () => {
    $("#document-input").value = sampleText;
  });
  $("#clear-button").addEventListener("click", () => {
    $("#document-input").value = "";
    renderResult({});
  });
  $("#deterministic-button").addEventListener("click", (event) => {
    runAnalysis("/api/analyze/deterministic", event.currentTarget);
  });
  $("#llm-button").addEventListener("click", (event) => {
    runAnalysis("/api/analyze/llm", event.currentTarget);
  });
  $("#route-button").addEventListener("click", (event) => {
    runAnalysis("/api/route", event.currentTarget);
  });
  $("#series-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const values = $("#series-input")
        .value.split(",")
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isFinite(value));
      $("#series-output").textContent = JSON.stringify(
        await requestJson("/api/analyze/timeseries", { values }),
        null,
        2,
      );
    } catch (error) {
      $("#series-output").textContent = JSON.stringify({ error: error.message }, null, 2);
    } finally {
      setLoading(button, false);
    }
  });
  $("#brief-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const params = new URLSearchParams({
        path: $("#brief-path").value,
        limit: $("#brief-limit").value,
        output_md: $("#brief-output-md").value,
        output_json: $("#brief-output-json-path").value,
      });
      renderBrief(await getJson(`/api/intelligence-brief?${params.toString()}`));
    } catch (error) {
      $("#brief-output").textContent = `Brief failed: ${error.message}`;
    } finally {
      setLoading(button, false);
    }
  });
  $("#feedback-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const payload = {
        document_id: $("#feedback-document-id").value,
        reviewer: $("#feedback-reviewer").value,
        decision: $("#feedback-decision").value,
        comment: $("#feedback-comment").value,
      };
      $("#feedback-output").textContent = JSON.stringify(
        await requestJson("/api/feedback", payload),
        null,
        2,
      );
    } catch (error) {
      $("#feedback-output").textContent = JSON.stringify({ error: error.message }, null, 2);
    } finally {
      setLoading(button, false);
    }
  });
  $("#load-documents-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      state.documentsOffset = 0;
      state.selectedDocumentId = "";
      state.selectedDocumentSource = "";
      renderDocumentTable(await loadDocuments());
    } catch (error) {
      $("#documents-count").textContent = error.message;
    } finally {
      setLoading(button, false);
    }
  });
  $("#documents-query").addEventListener("input", debounce(async () => {
    state.documentsOffset = 0;
    state.selectedDocumentId = "";
    state.selectedDocumentSource = "";
    renderDocumentTable(await loadDocuments());
  }, 250));
  for (const selector of [
    "#documents-source-filter",
    "#documents-event-filter",
    "#documents-risk-filter",
    "#documents-sort",
  ]) {
    $(selector).addEventListener("change", async () => {
      state.documentsOffset = 0;
      state.selectedDocumentId = "";
      state.selectedDocumentSource = "";
      renderDocumentTable(await loadDocuments());
    });
  }
  $("#documents-prev-button").addEventListener("click", async () => {
    state.documentsOffset = Math.max(0, state.documentsOffset - state.documentsLimit);
    renderDocumentTable(await loadDocuments());
  });
  $("#documents-next-button").addEventListener("click", async () => {
    if (!state.documentsHasMore) {
      return;
    }
    state.documentsOffset += state.documentsLimit;
    renderDocumentTable(await loadDocuments());
  });
  $("#load-feedback-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const path = encodeURIComponent($("#feedback-path").value);
      const data = await getJson(`/api/feedback?path=${path}&limit=50&offset=0`);
      renderRecords("#feedback-list", data.items || [], "feedback");
    } catch (error) {
      renderRecords("#feedback-list", [{ decision: "error", document_id: error.message }], "feedback");
    } finally {
      setLoading(button, false);
    }
  });
  $("#load-runs-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      state.runsOffset = 0;
      renderRunsTable(await loadRuns());
    } catch (error) {
      $("#runs-count").textContent = error.message;
    } finally {
      setLoading(button, false);
    }
  });
  $("#runs-prev-button").addEventListener("click", async () => {
    state.runsOffset = Math.max(0, state.runsOffset - state.runsLimit);
    renderRunsTable(await loadRuns());
  });
  $("#runs-next-button").addEventListener("click", async () => {
    if (!state.runsHasMore) {
      return;
    }
    state.runsOffset += state.runsLimit;
    renderRunsTable(await loadRuns());
  });
  $("#job-sources").addEventListener("change", () => {
    const selectedSources = selectedJobSources();
    state.selectedProfile = matchingSourceProfile(selectedSources);
    renderSourceProfiles();
  });
  $("#trigger-fetch-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const result = await requestJson("/api/jobs/fetch", jobPayload());
      $("#job-output-json").textContent = JSON.stringify(result, null, 2);
    } catch (error) {
      $("#job-output-json").textContent = JSON.stringify({ error: error.message }, null, 2);
    } finally {
      setLoading(button, false);
      try {
        await refreshOperationalViews();
      } catch {
        // Keep the job result visible even if a refresh fails.
      }
    }
  });
  $("#daily-cycle-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const result = await requestJson(
        "/api/jobs/daily-cycle",
        jobPayload({
          run_log: "data/runs/daily_cycles.jsonl",
          brief_limit: Number($("#brief-limit").value || 100),
          report_md: $("#brief-output-md").value,
          report_json: $("#brief-output-json-path").value,
        }),
      );
      $("#job-output-json").textContent = JSON.stringify(result, null, 2);
      const brief = result.record?.result?.brief;
      if (brief) {
        renderBrief(brief);
      }
      $("#runs-path").value = result.run_log || "data/runs/daily_cycles.jsonl";
    } catch (error) {
      $("#job-output-json").textContent = JSON.stringify({ error: error.message }, null, 2);
    } finally {
      setLoading(button, false);
      try {
        await refreshOperationalViews();
      } catch {
        // Keep the cycle result visible even if a refresh fails.
      }
    }
  });
  $("#load-diagnostics-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      await loadDiagnostics();
    } finally {
      setLoading(button, false);
    }
  });
  $("#load-source-state-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      await loadSourceState();
    } catch (error) {
      $("#source-state-count").textContent = error.message;
    } finally {
      setLoading(button, false);
    }
  });
  $("#load-source-report-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const report = await loadSourceReport();
      $("#source-report-output").textContent = report.markdown || JSON.stringify(report, null, 2);
    } catch (error) {
      $("#source-report-output").textContent = `Report failed: ${error.message}`;
    } finally {
      setLoading(button, false);
    }
  });
  $("#source-state-status-filter").addEventListener("change", () => {
    if (state.sourceStateData) {
      renderSourceState(state.sourceStateData);
    }
  });
  $("#source-state-collector-filter").addEventListener("change", () => {
    if (state.sourceStateData) {
      renderSourceState(state.sourceStateData);
    }
  });
  $("#source-state-query").addEventListener("input", debounce(() => {
    if (state.sourceStateData) {
      renderSourceState(state.sourceStateData);
    }
  }, 200));
}

async function loadDocuments() {
  const [sortBy, sortDirection] = $("#documents-sort").value.split(":");
  const params = new URLSearchParams({
    path: $("#documents-path").value,
    limit: String(state.documentsLimit),
    offset: String(state.documentsOffset),
    query: $("#documents-query").value,
    source: $("#documents-source-filter").value,
    event_type: $("#documents-event-filter").value,
    risk: $("#documents-risk-filter").value,
    sort_by: sortBy,
    sort_direction: sortDirection,
  });
  return getJson(`/api/documents?${params.toString()}`);
}

async function loadRuns() {
  const params = new URLSearchParams({
    path: $("#runs-path").value,
    limit: String(state.runsLimit),
    offset: String(state.runsOffset),
  });
  return getJson(`/api/runs?${params.toString()}`);
}

function debounce(callback, delayMs) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => callback(...args), delayMs);
  };
}

wireNavigation();
wireActions();
loadHealthAndConfig();
$("#document-input").value = sampleText;
renderResult({});
