"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  sessions: [],
  records: [],
  currentSession: null,
  localFile: null,
  selectedLine: null,
  rawTab: "pretty",
  query: "",
  enabledKinds: new Set(),
  toolName: "",
  forcedLine: null,
  live: true,
  loading: false,
  indexTimer: null,
  liveTimer: null,
};

const KINDS = [
  ["user", "User"],
  ["assistant", "Assistant"],
  ["reasoning", "Reasoning"],
  ["tool-call", "Tool call"],
  ["tool-result", "Tool result"],
  ["error", "Error"],
  ["metadata", "Metadata"],
];

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 1800);
}

function setLiveStatus(label, kind = "") {
  const status = $("#live-status");
  status.className = `live-status ${kind}`.trim();
  status.lastElementChild.textContent = label;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

function formatNumber(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat().format(value) : "-";
}

function timestampValue(record) {
  const data = record.data || {};
  const value = data.timestamp ?? data.message?.timestamp;
  if (typeof value === "number") return value;
  if (typeof value === "string") return Date.parse(value);
  return NaN;
}

function shortTime(record) {
  const value = timestampValue(record);
  if (!Number.isFinite(value)) return "";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function durationLabel(milliseconds) {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "-";
  const seconds = Math.round(milliseconds / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainder}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function textFromContent(content) {
  if (!Array.isArray(content)) return "";
  return content.map((block) => {
    if (!block || typeof block !== "object") return String(block ?? "");
    if (block.type === "text") return block.text || "";
    if (block.type === "thinking") return block.thinking || "";
    if (block.type === "toolCall") {
      return `${block.name || "tool"}\n${JSON.stringify(block.arguments ?? {}, null, 2)}`;
    }
    return JSON.stringify(block, null, 2);
  }).filter(Boolean).join("\n\n");
}

function searchableText(data, raw) {
  if (!data || typeof data !== "object") return raw.toLocaleLowerCase();
  const message = data.message || {};
  return [
    data.type,
    message.role,
    message.toolName,
    message.toolCallId,
    textFromContent(message.content),
    raw,
  ].filter(Boolean).join("\n").toLocaleLowerCase();
}

function parseLocalJsonl(text) {
  const lines = text.split(/\r?\n/);
  if (lines.at(-1) === "") lines.pop();
  return lines.map((raw, index) => {
    try {
      const data = JSON.parse(raw);
      return {
        line: index + 1,
        raw,
        data,
        parseError: null,
        searchText: searchableText(data, raw),
      };
    } catch (error) {
      return {
        line: index + 1,
        raw,
        data: null,
        parseError: { message: error.message, column: null },
        searchText: raw.toLocaleLowerCase(),
      };
    }
  });
}

function contentTypes(record) {
  const message = record.data?.message;
  if (!message || !Array.isArray(message.content)) return [];
  return message.content.map((block) => block?.type).filter(Boolean);
}

function recordKind(record) {
  if (record.parseError) return "error";
  const data = record.data || {};
  if (data.type !== "message") return "metadata";
  const message = data.message || {};
  if (message.role === "user") return "user";
  if (message.role === "toolResult") return message.isError ? "error" : "tool-result";
  if (message.role === "assistant") {
    const types = contentTypes(record);
    if (types.includes("text")) return "assistant";
    if (types.includes("toolCall")) return "tool-call";
    if (types.includes("thinking")) return "reasoning";
    return "assistant";
  }
  return "metadata";
}

function recordKinds(record) {
  const primary = recordKind(record);
  const kinds = new Set([primary]);
  const types = contentTypes(record);
  if (types.includes("thinking")) kinds.add("reasoning");
  if (types.includes("toolCall")) kinds.add("tool-call");
  if (record.data?.message?.isError) kinds.add("error");
  return kinds;
}

function recordTitle(record) {
  if (record.parseError) return `Malformed JSON: ${record.parseError.message}`;
  const data = record.data || {};
  if (data.type !== "message") {
    const labels = {
      session: "Session started",
      model_change: "Model selected",
      thinking_level_change: "Thinking level selected",
    };
    return labels[data.type] || data.type || "Metadata";
  }
  const message = data.message || {};
  if (message.role === "user") return "User prompt";
  if (message.role === "toolResult") {
    return `${message.isError ? "Failed" : "Result"}: ${message.toolName || "tool"}`;
  }
  const blocks = message.content || [];
  const toolCalls = blocks.filter((block) => block?.type === "toolCall");
  if (toolCalls.length) {
    const names = [...new Set(toolCalls.map((block) => block.name || "tool"))];
    return `Tool call${toolCalls.length > 1 ? "s" : ""}: ${names.join(", ")}`;
  }
  if (blocks.some((block) => block?.type === "thinking")) return "Assistant reasoning";
  return "Assistant message";
}

function recordPreview(record) {
  if (record.parseError) return record.raw.slice(0, 500);
  const data = record.data || {};
  if (data.type !== "message") {
    if (data.type === "session") return `${data.cwd || ""}  ${data.id || ""}`.trim();
    if (data.type === "model_change") return `${data.provider || ""}/${data.modelId || ""}`.replace(/^\//, "");
    if (data.type === "thinking_level_change") return data.thinkingLevel || "";
    return JSON.stringify(data);
  }
  return textFromContent(data.message?.content).slice(0, 1200);
}

function recordIcon(kind) {
  return {
    user: "U",
    assistant: "A",
    reasoning: "R",
    "tool-call": ">_",
    "tool-result": "✓",
    error: "!",
    metadata: "i",
  }[kind] || "·";
}

function recordToolNames(record) {
  const message = record.data?.message || {};
  const names = [];
  if (message.toolName) names.push(message.toolName);
  for (const block of message.content || []) {
    if (block?.type === "toolCall" && block.name) names.push(block.name);
  }
  return [...new Set(names)];
}

function toolMaps() {
  const calls = new Map();
  const results = new Map();
  for (const record of state.records) {
    const message = record.data?.message || {};
    for (const block of message.content || []) {
      if (block?.type === "toolCall" && block.id) calls.set(block.id, record.line);
    }
    if (message.toolCallId) results.set(message.toolCallId, record.line);
  }
  return { calls, results };
}

function filteredRecords() {
  const query = state.query.trim().toLocaleLowerCase();
  return state.records.filter((record) => {
    if (record.line === state.forcedLine) return true;
    const kinds = recordKinds(record);
    if (![...kinds].some((kind) => state.enabledKinds.has(kind))) return false;
    if (state.toolName && !recordToolNames(record).includes(state.toolName)) return false;
    return !query || record.searchText.includes(query);
  });
}

function appendTextWithLinks(parent, text) {
  const pattern = /https?:\/\/[^\s<>"']+/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(offset, match.index)));
    const link = document.createElement("a");
    link.href = match[0];
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = match[0];
    parent.append(link);
    offset = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(offset)));
}

function renderSafeMarkdown(text, parent) {
  const lines = String(text).split("\n");
  let code = null;
  let paragraph = [];
  const flushParagraph = () => {
    if (!paragraph.length) return;
    const block = document.createElement("div");
    block.className = "markdown-block";
    appendTextWithLinks(block, paragraph.join("\n"));
    parent.append(block);
    paragraph = [];
  };
  for (const line of lines) {
    if (line.startsWith("```")) {
      flushParagraph();
      if (code === null) {
        code = [];
      } else {
        const pre = document.createElement("pre");
        pre.className = "markdown-code";
        pre.textContent = code.join("\n");
        parent.append(pre);
        code = null;
      }
      continue;
    }
    if (code !== null) {
      code.push(line);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      continue;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      const element = document.createElement(`h${Math.min(heading[1].length + 2, 6)}`);
      element.className = "markdown-block";
      appendTextWithLinks(element, heading[2]);
      parent.append(element);
      continue;
    }
    paragraph.push(line);
  }
  flushParagraph();
  if (code !== null) {
    const pre = document.createElement("pre");
    pre.className = "markdown-code";
    pre.textContent = code.join("\n");
    parent.append(pre);
  }
}

function contentDetails(label, text, open = false) {
  const details = document.createElement("details");
  details.className = "content-block";
  details.open = open;
  const summary = document.createElement("summary");
  summary.textContent = label;
  const body = document.createElement("div");
  body.className = "content-body";
  renderSafeMarkdown(text, body);
  details.append(summary, body);
  if (text.length > 6000) {
    const actions = document.createElement("div");
    actions.className = "record-actions";
    const show = document.createElement("button");
    show.type = "button";
    show.className = "mini-action";
    show.textContent = "Show all";
    show.addEventListener("click", (event) => {
      event.stopPropagation();
      body.classList.toggle("expanded");
      show.textContent = body.classList.contains("expanded") ? "Limit height" : "Show all";
    });
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "mini-action";
    copy.textContent = "Copy content";
    copy.addEventListener("click", async (event) => {
      event.stopPropagation();
      await copyText(text);
    });
    const download = document.createElement("button");
    download.type = "button";
    download.className = "mini-action";
    download.textContent = "Download content";
    download.addEventListener("click", (event) => {
      event.stopPropagation();
      downloadText(text, "trajectory-content.txt");
    });
    actions.append(show, copy, download);
    body.append(actions);
  }
  return details;
}

function addRecordContent(record, main, maps) {
  const data = record.data;
  if (!data || data.type !== "message") return;
  const message = data.message || {};
  for (const block of message.content || []) {
    if (!block || typeof block !== "object") continue;
    if (block.type === "thinking") {
      main.append(contentDetails("Reasoning", block.thinking || "", false));
    } else if (block.type === "toolCall") {
      const argumentsText = typeof block.arguments === "string"
        ? block.arguments
        : JSON.stringify(block.arguments ?? {}, null, 2);
      const detail = contentDetails(`Call ${block.name || "tool"}`, argumentsText, false);
      const resultLine = maps.results.get(block.id);
      if (resultLine) detail.querySelector(".content-body").append(jumpButton(`Jump to result on line ${resultLine}`, resultLine));
      main.append(detail);
    } else if (block.type === "text") {
      main.append(contentDetails(message.role === "toolResult" ? "Tool output" : "Message", block.text || "", false));
    } else {
      main.append(contentDetails(block.type || "Content", JSON.stringify(block, null, 2), false));
    }
  }
  if (message.toolCallId) {
    const callLine = maps.calls.get(message.toolCallId);
    if (callLine) main.append(jumpButton(`Jump to call on line ${callLine}`, callLine));
  }
}

function jumpButton(label, line) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "mini-action";
  button.textContent = label;
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    selectLine(line, { scroll: true, history: "push" });
  });
  return button;
}

function renderTimeline() {
  const timeline = $("#timeline");
  const records = filteredRecords();
  const maps = toolMaps();
  timeline.replaceChildren();
  $("#result-count").textContent = `${formatNumber(records.length)} / ${formatNumber(state.records.length)}`;
  $("#filter-notice").hidden = state.forcedLine === null;
  if (!records.length) {
    const empty = document.createElement("div");
    empty.className = "empty-results";
    empty.textContent = "No records match the current search and filters.";
    timeline.append(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const record of records) {
    const kind = recordKind(record);
    const element = document.createElement("article");
    element.className = "record";
    if (record.line === state.selectedLine) element.classList.add("selected");
    if (record.line === state.forcedLine) element.classList.add("force-visible");
    element.dataset.line = record.line;
    element.dataset.kind = kind;
    element.tabIndex = record.line === state.selectedLine ? 0 : -1;
    element.setAttribute("role", "option");
    element.setAttribute("aria-selected", String(record.line === state.selectedLine));
    const number = document.createElement("span");
    number.className = "line-number";
    number.textContent = `L${record.line}`;
    const icon = document.createElement("span");
    icon.className = "record-icon";
    icon.textContent = recordIcon(kind);
    const main = document.createElement("div");
    main.className = "record-main";
    const head = document.createElement("div");
    head.className = "record-head";
    const title = document.createElement("span");
    title.className = "record-title";
    title.textContent = recordTitle(record);
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = kind.replace("-", " ");
    const time = document.createElement("time");
    time.className = "record-time";
    time.textContent = shortTime(record);
    head.append(title, chip, time);
    const previewText = recordPreview(record);
    const preview = document.createElement("p");
    preview.className = "record-preview";
    preview.textContent = previewText || "No display content";
    main.append(head, preview);
    addRecordContent(record, main, maps);
    element.append(number, icon, main);
    element.addEventListener("click", () => selectLine(record.line, { history: "push" }));
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        const detail = element.querySelector("details");
        if (detail) detail.open = !detail.open;
      }
    });
    fragment.append(element);
  }
  timeline.append(fragment);
}

function syntaxHighlightedJson(value) {
  const escaped = JSON.stringify(value, null, 2)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
  return escaped.replace(
    /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"\s*:)|("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*")|\b(true|false)\b|\b(null)\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?/g,
    (match, key, string, booleanValue, nullValue) => {
      let className = "json-number";
      if (key) className = "json-key";
      else if (string) className = "json-string";
      else if (booleanValue) className = "json-boolean";
      else if (nullValue) className = "json-null";
      return `<span class="${className}">${match}</span>`;
    },
  );
}

function selectedRecord() {
  return state.records.find((record) => record.line === state.selectedLine) || null;
}

function renderRaw() {
  const record = selectedRecord();
  const output = $("#raw-content");
  if (!record) {
    $("#raw-title").textContent = "Select a line";
    output.textContent = "";
    return;
  }
  $("#raw-title").textContent = `Line ${record.line} · ${recordTitle(record)}`;
  if (state.rawTab === "exact" || !record.data) {
    output.textContent = record.raw;
  } else {
    output.innerHTML = syntaxHighlightedJson(record.data);
  }
}

function lineIsFiltered(line) {
  const record = state.records.find((item) => item.line === line);
  if (!record) return false;
  const previous = state.forcedLine;
  state.forcedLine = null;
  const hidden = !filteredRecords().includes(record);
  state.forcedLine = previous;
  return hidden;
}

function selectLine(line, options = {}) {
  const record = state.records.find((item) => item.line === Number(line));
  if (!record) {
    showToast(`Line ${line} does not exist`);
    return false;
  }
  state.selectedLine = record.line;
  state.forcedLine = lineIsFiltered(record.line) ? record.line : null;
  renderTimeline();
  renderRaw();
  if (options.history) updateUrl(options.history);
  if (options.scroll) {
    requestAnimationFrame(() => {
      const element = document.querySelector(`.record[data-line="${record.line}"]`);
      const pane = $("#timeline-pane");
      if (element) {
        const elementBounds = element.getBoundingClientRect();
        const paneBounds = pane.getBoundingClientRect();
        const top = pane.scrollTop + elementBounds.top - paneBounds.top
          - (pane.clientHeight - element.offsetHeight) / 2;
        pane.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
        element.focus({ preventScroll: true });
      }
    });
  }
  return true;
}

function summarizeSession() {
  const times = state.records.map(timestampValue).filter(Number.isFinite);
  let tokens = 0;
  let toolCalls = 0;
  let errors = state.records.filter((record) => record.parseError).length;
  for (const record of state.records) {
    const message = record.data?.message || {};
    const usage = message.usage || {};
    tokens += Number(usage.totalTokens || usage.total || 0);
    if (message.isError) errors += 1;
    toolCalls += (message.content || []).filter((block) => block?.type === "toolCall").length;
  }
  return {
    duration: times.length > 1 ? Math.max(...times) - Math.min(...times) : NaN,
    tokens,
    toolCalls,
    errors,
  };
}

function renderOverview() {
  const session = state.currentSession || {};
  const sessionRecord = state.records.find((record) => record.data?.type === "session")?.data || {};
  const modelRecord = state.records.find((record) => record.data?.type === "model_change")?.data || {};
  const summary = summarizeSession();
  const title = state.localFile?.name || [session.task, session.model].filter(Boolean).join(" · ") || "Local session";
  $("#session-title").textContent = title;
  $("#session-path").textContent = state.localFile?.name || session.id || "Browser-local file";
  const start = sessionRecord.timestamp ? new Date(sessionRecord.timestamp).toLocaleString() : "-";
  const metrics = [
    ["Model", session.model || modelRecord.modelId || "-"],
    ["Started", start],
    ["Duration", durationLabel(summary.duration)],
    ["Records", formatNumber(state.records.length)],
    ["Tokens", formatNumber(summary.tokens)],
    ["Tool calls", formatNumber(summary.toolCalls)],
    ["Errors", formatNumber(summary.errors)],
  ];
  const container = $("#metrics");
  container.replaceChildren();
  for (const [label, value] of metrics) {
    const metric = document.createElement("div");
    metric.className = "metric";
    const name = document.createElement("span");
    name.textContent = label;
    const result = document.createElement("strong");
    result.textContent = value;
    result.title = value;
    metric.append(name, result);
    container.append(metric);
  }
}

function renderToolFilter() {
  const names = [...new Set(state.records.flatMap(recordToolNames))].sort((a, b) => a.localeCompare(b));
  const select = $("#tool-filter");
  const selected = state.toolName;
  select.replaceChildren(new Option("All tools", ""), ...names.map((name) => new Option(name, name)));
  select.value = names.includes(selected) ? selected : "";
  state.toolName = select.value;
}

function finishLoad(preferredLine = null, history = "replace") {
  $("#empty-state").hidden = true;
  $("#viewer").hidden = false;
  renderOverview();
  renderToolFilter();
  const requested = Number(preferredLine);
  const defaultRecord = state.records.find((record) => recordKind(record) === "user") || state.records[0];
  const line = Number.isInteger(requested) && requested > 0 ? requested : defaultRecord?.line;
  const shouldScroll = Number.isInteger(requested) && requested > 0;
  if (line && !selectLine(line, { history, scroll: shouldScroll })) {
    selectLine(defaultRecord?.line, { history });
  } else if (!line) {
    renderTimeline();
    renderRaw();
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  const payload = await response.json().catch(() => ({ error: response.statusText }));
  if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

async function loadSession(session, preferredLine = null, history = "push") {
  if (!session || state.loading) return;
  state.loading = true;
  setLiveStatus("Loading...");
  try {
    const payload = await fetchJson(`/api/session?id=${encodeURIComponent(session.id)}`);
    state.currentSession = payload.session || session;
    state.localFile = null;
    state.records = payload.records;
    state.selectedLine = null;
    state.forcedLine = null;
    finishLoad(preferredLine, history);
    setLiveStatus(state.live ? "Live" : "Paused", state.live ? "live" : "");
  } catch (error) {
    setLiveStatus("Load failed", "error");
    showToast(error.message);
  } finally {
    state.loading = false;
  }
}

async function refreshCurrentSession() {
  if (!state.live || !state.currentSession || state.localFile || state.loading) return;
  try {
    const previousCount = state.records.length;
    let payload = await fetchJson(`/api/session?id=${encodeURIComponent(state.currentSession.id)}&after=${previousCount}`);
    const anchorChanged = previousCount > 0
      && payload.anchorRaw !== state.records.at(-1)?.raw;
    if (payload.reset || anchorChanged) {
      payload = await fetchJson(`/api/session?id=${encodeURIComponent(state.currentSession.id)}`);
      state.records = payload.records;
    } else if (payload.records.length) {
      state.records.push(...payload.records);
    }
    if (payload.modifiedNs !== state.currentSession.modifiedNs || payload.lineCount !== previousCount) {
      state.currentSession = payload.session;
      renderOverview();
      renderToolFilter();
      const selected = Math.min(state.selectedLine || 1, Math.max(state.records.length, 1));
      selectLine(selected, { history: "replace" });
      const difference = state.records.length - previousCount;
      if (difference > 0) showToast(`${difference} new record${difference === 1 ? "" : "s"}`);
    }
    setLiveStatus("Live", "live");
  } catch (error) {
    setLiveStatus("Refresh failed", "error");
  }
}

function uniqueValues(items, key) {
  return [...new Set(items.map((item) => item[key]))].sort((a, b) => String(a).localeCompare(String(b)));
}

function setOptions(select, values, placeholder, preferred) {
  select.replaceChildren(new Option(placeholder, ""), ...values.map((value) => new Option(value, value)));
  if (preferred && values.includes(preferred)) select.value = preferred;
  else if (values.length === 1) select.value = values[0];
}

function filteredSessionsForPicker() {
  const query = $("#session-search").value.trim().toLocaleLowerCase();
  if (!query) return state.sessions;
  return state.sessions.filter((session) => [session.task, session.model, session.run, session.attempt, session.id].join(" ").toLocaleLowerCase().includes(query));
}

function updatePickers(level = "task", preferred = {}) {
  const all = filteredSessionsForPicker();
  const taskSelect = $("#task-select");
  const modelSelect = $("#model-select");
  const runSelect = $("#run-select");
  const attemptSelect = $("#attempt-select");
  const previous = {
    task: preferred.task ?? taskSelect.value,
    model: preferred.model ?? modelSelect.value,
    run: preferred.run ?? runSelect.value,
    attempt: preferred.attempt ?? attemptSelect.value,
  };
  if (level === "task") setOptions(taskSelect, uniqueValues(all, "task"), "Select a task", previous.task);
  const byTask = all.filter((item) => item.task === taskSelect.value);
  if (["task", "model"].includes(level)) setOptions(modelSelect, uniqueValues(byTask, "model"), "Select a model", previous.model);
  const byModel = byTask.filter((item) => item.model === modelSelect.value);
  if (["task", "model", "run"].includes(level)) setOptions(runSelect, uniqueValues(byModel, "run"), "Select a run", previous.run);
  const byRun = byModel.filter((item) => item.run === runSelect.value);
  setOptions(attemptSelect, uniqueValues(byRun, "attempt"), "Select an attempt", previous.attempt);
  maybeLoadPickerSession();
}

function maybeLoadPickerSession() {
  const match = state.sessions.find((session) =>
    session.task === $("#task-select").value &&
    session.model === $("#model-select").value &&
    session.run === $("#run-select").value &&
    session.attempt === $("#attempt-select").value
  );
  if (match && match.id !== state.currentSession?.id) loadSession(match);
}

async function loadSessionIndex({ preserve = true } = {}) {
  try {
    const payload = await fetchJson("/api/sessions");
    state.sessions = payload.sessions;
    $("#root-label").textContent = `${payload.root} · ${payload.sessions.length} session${payload.sessions.length === 1 ? "" : "s"}`;
    const preferred = preserve && state.currentSession ? state.currentSession : {};
    updatePickers("task", preferred);
    return payload;
  } catch (error) {
    $("#root-label").textContent = error.message;
    setLiveStatus("Index failed", "error");
    return null;
  }
}

function updateUrl(mode = "replace") {
  if (state.localFile) return;
  const url = new URL(window.location.href);
  if (state.currentSession?.id) url.searchParams.set("session", state.currentSession.id);
  else url.searchParams.delete("session");
  if (state.selectedLine) url.searchParams.set("line", state.selectedLine);
  else url.searchParams.delete("line");
  history[`${mode}State`]({ session: state.currentSession?.id, line: state.selectedLine }, "", url);
}

async function restoreFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session");
  const line = params.get("line");
  if (!sessionId) return false;
  const session = state.sessions.find((item) => item.id === sessionId);
  if (!session) {
    showToast("The linked session was not found");
    return false;
  }
  await loadSession(session, line, "replace");
  updatePickers("task", session);
  return true;
}

async function openLocalFile(file) {
  if (!file) return;
  try {
    const text = await file.text();
    state.localFile = file;
    state.currentSession = { task: file.name, model: "Local file", id: null };
    state.records = parseLocalJsonl(text);
    state.selectedLine = null;
    state.forcedLine = null;
    finishLoad(null, null);
    setLiveStatus("Local file");
    showToast(`Opened ${file.name}`);
  } catch (error) {
    showToast(`Could not open file: ${error.message}`);
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast("Copied");
  } catch {
    showToast("Clipboard access was blocked");
  }
}

function downloadText(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function applyTheme(theme) {
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset.theme = theme;
  localStorage.setItem("trajectory-theme", theme);
  $("#theme-toggle").textContent = `Theme: ${theme}`;
}

function cycleTheme() {
  const current = localStorage.getItem("trajectory-theme") || "system";
  const order = ["system", "light", "dark"];
  applyTheme(order[(order.indexOf(current) + 1) % order.length]);
}

function initFilters() {
  const container = $("#kind-filters");
  for (const [value, label] of KINDS) {
    state.enabledKinds.add(value);
    const wrapper = document.createElement("label");
    wrapper.className = "filter-check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = value;
    input.checked = true;
    input.addEventListener("change", () => {
      if (input.checked) state.enabledKinds.add(value);
      else state.enabledKinds.delete(value);
      state.forcedLine = null;
      renderTimeline();
    });
    wrapper.append(input, document.createTextNode(label));
    container.append(wrapper);
  }
}

function installSplitter() {
  const splitter = $("#splitter");
  const splitView = $("#split-view");
  const saved = Number(localStorage.getItem("trajectory-split"));
  if (saved >= 30 && saved <= 75) document.documentElement.style.setProperty("--timeline-width", `${saved}%`);
  let dragging = false;
  splitter.addEventListener("pointerdown", (event) => {
    dragging = true;
    splitter.setPointerCapture(event.pointerId);
  });
  splitter.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const bounds = splitView.getBoundingClientRect();
    const percent = Math.min(75, Math.max(30, ((event.clientX - bounds.left) / bounds.width) * 100));
    document.documentElement.style.setProperty("--timeline-width", `${percent}%`);
    localStorage.setItem("trajectory-split", percent.toFixed(1));
  });
  splitter.addEventListener("pointerup", () => { dragging = false; });
  splitter.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--timeline-width")) || 55;
    const next = Math.min(75, Math.max(30, current + (event.key === "ArrowLeft" ? -2 : 2)));
    document.documentElement.style.setProperty("--timeline-width", `${next}%`);
    localStorage.setItem("trajectory-split", String(next));
  });
}

function installEvents() {
  $("#open-file").addEventListener("click", () => $("#file-input").click());
  $("#file-input").addEventListener("change", (event) => openLocalFile(event.target.files[0]));
  let dragDepth = 0;
  window.addEventListener("dragenter", (event) => {
    event.preventDefault();
    dragDepth += 1;
    document.body.classList.add("dragging");
  });
  window.addEventListener("dragleave", () => {
    dragDepth -= 1;
    if (dragDepth <= 0) document.body.classList.remove("dragging");
  });
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    document.body.classList.remove("dragging");
    openLocalFile(event.dataTransfer.files[0]);
  });
  $("#theme-toggle").addEventListener("click", cycleTheme);
  $("#refresh-sessions").addEventListener("click", async () => {
    await loadSessionIndex();
    showToast("Session list refreshed");
  });
  $("#session-search").addEventListener("input", () => updatePickers("task"));
  $("#task-select").addEventListener("change", () => updatePickers("model"));
  $("#model-select").addEventListener("change", () => updatePickers("run"));
  $("#run-select").addEventListener("change", () => updatePickers("attempt"));
  $("#attempt-select").addEventListener("change", maybeLoadPickerSession);
  $("#global-search").addEventListener("input", (event) => {
    state.query = event.target.value;
    state.forcedLine = null;
    renderTimeline();
  });
  $("#filter-button").addEventListener("click", () => {
    const panel = $("#filter-panel");
    panel.hidden = !panel.hidden;
    $("#filter-button").setAttribute("aria-expanded", String(!panel.hidden));
  });
  $("#tool-filter").addEventListener("change", (event) => {
    state.toolName = event.target.value;
    state.forcedLine = null;
    renderTimeline();
  });
  $("#clear-filters").addEventListener("click", () => {
    state.enabledKinds = new Set(KINDS.map(([kind]) => kind));
    $$("#kind-filters input").forEach((input) => { input.checked = true; });
    state.toolName = "";
    $("#tool-filter").value = "";
    state.query = "";
    $("#global-search").value = "";
    state.forcedLine = null;
    renderTimeline();
  });
  $("#goto-form").addEventListener("submit", (event) => {
    event.preventDefault();
    selectLine(Number($("#goto-line").value), { scroll: true, history: "push" });
  });
  $("#live-toggle").addEventListener("click", () => {
    state.live = !state.live;
    $("#live-toggle").textContent = state.live ? "Pause" : "Resume";
    $("#live-toggle").title = state.live ? "Pause live refresh" : "Resume live refresh";
    setLiveStatus(state.live ? "Live" : "Paused", state.live ? "live" : "");
    if (state.live) refreshCurrentSession();
  });
  $("#copy-link").addEventListener("click", () => {
    if (state.localFile) showToast("Browser-local files do not have shareable links");
    else copyText(window.location.href);
  });
  $("#copy-record").addEventListener("click", () => {
    const record = selectedRecord();
    if (record) copyText(state.rawTab === "pretty" && record.data ? JSON.stringify(record.data, null, 2) : record.raw);
  });
  $("#download-record").addEventListener("click", () => {
    const record = selectedRecord();
    if (record) downloadText(record.raw, `trajectory-line-${record.line}.json`);
  });
  $$(".raw-tab").forEach((tab) => tab.addEventListener("click", () => {
    state.rawTab = tab.dataset.rawTab;
    $$(".raw-tab").forEach((item) => item.classList.toggle("active", item === tab));
    renderRaw();
  }));
  $$(".mobile-tab").forEach((tab) => tab.addEventListener("click", () => {
    $$(".mobile-tab").forEach((item) => item.classList.toggle("active", item === tab));
    $("#split-view").classList.toggle("show-raw", tab.dataset.pane === "raw");
  }));
  window.addEventListener("popstate", async () => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session");
    const line = Number(params.get("line"));
    if (sessionId && sessionId !== state.currentSession?.id) {
      const session = state.sessions.find((item) => item.id === sessionId);
      if (session) await loadSession(session, line, "replace");
    } else if (line) selectLine(line, { scroll: true });
  });
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing = target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement;
    if (event.key === "/" && !typing) {
      event.preventDefault();
      $("#global-search").focus();
    } else if ((event.key === "g" || event.key === "G") && !typing) {
      event.preventDefault();
      $("#goto-line").focus();
      $("#goto-line").select();
    } else if (["j", "k", "J", "K"].includes(event.key) && !typing) {
      event.preventDefault();
      const visible = filteredRecords();
      const index = visible.findIndex((record) => record.line === state.selectedLine);
      const delta = event.key.toLocaleLowerCase() === "j" ? 1 : -1;
      const next = visible[Math.min(visible.length - 1, Math.max(0, index + delta))];
      if (next) selectLine(next.line, { scroll: true, history: "push" });
    } else if (event.key === "Escape") {
      target.blur?.();
      $("#filter-panel").hidden = true;
      $("#filter-button").setAttribute("aria-expanded", "false");
    }
  });
}

async function init() {
  applyTheme(localStorage.getItem("trajectory-theme") || "system");
  initFilters();
  installSplitter();
  installEvents();
  await loadSessionIndex({ preserve: false });
  await restoreFromUrl();
  state.liveTimer = setInterval(refreshCurrentSession, 2000);
  state.indexTimer = setInterval(() => loadSessionIndex(), 10000);
}

init();
