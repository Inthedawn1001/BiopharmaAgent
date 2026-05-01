const sampleText = `某生物技术公司宣布完成B轮融资，募集资金将用于推进PD-1联合疗法的临床II期研究，并扩展自身免疫疾病管线。公司表示，本轮融资由产业基金和多家投资机构共同参与。分析人士认为，该事件可能改善公司研发资金状况，但临床失败、监管审批和市场竞争仍是主要风险。`;

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
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function setLoading(button, loading) {
  if (!button) {
    return;
  }
  button.disabled = loading;
  button.dataset.originalText ||= button.textContent;
  button.textContent = loading ? "处理中" : button.dataset.originalText;
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
    result.summary || result.reason || result.error || "等待分析结果。";

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
    empty.textContent = "暂无记录。";
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
        : raw.title || insight.summary || raw.document_id || "未命名文档";

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
        ? record.comment || "无备注"
        : insight.summary || doc.text || "无摘要";

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
    `${rows.length} 条记录 / 筛选 ${filteredTotal} 条 / 全部 ${data.total ?? rows.length} 条`;
  state.documentsHasMore = Boolean(data.has_more);
  $("#documents-prev-button").disabled = (data.offset || 0) <= 0;
  $("#documents-next-button").disabled = !state.documentsHasMore;
  $("#documents-page-label").textContent =
    `第 ${Math.floor((data.offset || 0) / (data.limit || state.documentsLimit)) + 1} 页`;
  updateFacetSelect("#documents-source-filter", data.facets?.sources || []);
  updateFacetSelect("#documents-event-filter", data.facets?.event_types || []);
  updateFacetSelect("#documents-risk-filter", data.facets?.risks || []);

  const body = $("#documents-table-body");
  body.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.textContent = "暂无记录。";
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
  $("#runs-count").textContent =
    `${rows.length} 条运行 / 全部 ${data.total ?? rows.length} 条`;
  $("#runs-prev-button").disabled = (data.offset || 0) <= 0;
  $("#runs-next-button").disabled = !state.runsHasMore;
  $("#runs-page-label").textContent =
    `第 ${Math.floor((data.offset || 0) / (data.limit || state.runsLimit)) + 1} 页`;

  const body = $("#runs-table-body");
  body.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.textContent = "暂无运行记录。";
    tr.appendChild(td);
    body.appendChild(tr);
    $("#run-detail").textContent = "选择一条运行后显示详情。";
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
  all.textContent = "全部";
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
    renderResult({ error: "请输入待分析文本。" });
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
    empty.textContent = "选择一条文档后显示详情。";
    container.appendChild(empty);
    return;
  }
  if (detail.loading) {
    const loading = document.createElement("div");
    loading.className = "detail-empty";
    loading.textContent = "正在加载详情。";
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
    link.textContent = "打开来源";
    actionWrap.appendChild(link);
  }
  const loadButton = document.createElement("button");
  loadButton.className = "ghost";
  loadButton.textContent = "载入正文";
  loadButton.addEventListener("click", () => {
    $("#document-input").value = doc.text || doc.text_preview || "";
    activatePanel("document");
  });
  actionWrap.appendChild(loadButton);
  header.append(titleWrap, actionWrap);

  const metrics = document.createElement("div");
  metrics.className = "detail-metrics";
  for (const [label, value] of [
    ["质量", quality.label || "-"],
    ["字符", String(quality.text_length ?? 0)],
    ["词数", String(quality.word_count ?? 0)],
    ["方式", quality.extraction_method || "-"],
    ["清洗", quality.html_cleaned ? "是" : "否"],
    ["比例", quality.clean_ratio == null ? "-" : String(quality.clean_ratio)],
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
  previewTitle.textContent = "正文预览";
  const preview = document.createElement("pre");
  preview.className = "document-preview";
  preview.textContent = doc.text_preview || doc.text || "暂无正文。";

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
    $("#health-text").textContent = health.status === "ok" ? "本地服务在线" : "服务异常";
  } catch {
    $("#health-text").textContent = "服务离线";
  }

  try {
    const config = await fetch("/api/config").then((response) => response.json());
    $("#config-provider").textContent = config.provider;
    $("#config-model").textContent = config.model;
    $("#config-base-url").textContent = config.base_url;
    $("#config-api-key").textContent = config.has_api_key ? "已配置" : "未配置";
  } catch {
    $("#config-provider").textContent = "无法读取";
  }

  await loadSources();
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
  const defaults = new Set(["fda_press_releases", "sec_biopharma_filings", "asx_biopharma_announcements"]);
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source.name;
    option.textContent = `${source.name} · ${source.collector || "feed"}`;
    option.disabled = !source.enabled;
    option.selected = defaults.has(source.name) && source.enabled;
    select.appendChild(option);
  }
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
  $("#trigger-fetch-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const selectedSources = Array.from($("#job-sources").selectedOptions).map((option) => option.value);
      const payload = {
        sources: selectedSources,
        limit: Number($("#job-limit").value || 1),
        analyze: $("#job-analyze").checked,
        fetch_details: $("#job-fetch-details").checked,
        clean_html_details: $("#job-clean-html").checked,
        run_log: $("#runs-path").value,
        output: $("#job-output").value,
        archive_dir: "data/raw",
        graph_dir: "data/graph",
      };
      const result = await requestJson("/api/jobs/fetch", payload);
      $("#job-output-json").textContent = JSON.stringify(result, null, 2);
    } catch (error) {
      $("#job-output-json").textContent = JSON.stringify({ error: error.message }, null, 2);
    } finally {
      setLoading(button, false);
      try {
        state.runsOffset = 0;
        renderRunsTable(await loadRuns());
        state.documentsOffset = 0;
        renderDocumentTable(await loadDocuments());
      } catch {
        // Keep the job result visible even if a refresh fails.
      }
    }
  });
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
