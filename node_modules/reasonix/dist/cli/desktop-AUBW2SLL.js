#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  collectMemoryEntriesForWorkspace,
  readMemoryEntryDetail
} from "./chunk-B5JISV5I.js";
import {
  QQChannel,
  createMcpRuntime
} from "./chunk-GOASYYZ4.js";
import {
  applyPlanMode,
  buildCodeToolset
} from "./chunk-2WZT27GR.js";
import "./chunk-URAI4YRL.js";
import {
  Eventizer,
  autoResolveVerdict
} from "./chunk-GMQVINZK.js";
import "./chunk-LRO63VNK.js";
import "./chunk-MQJR7YQ2.js";
import {
  CacheFirstLoop,
  ImmutablePrefix,
  listDirectory,
  listFilesWithStatsAsync,
  parseAtQuery,
  rankPickerCandidates
} from "./chunk-DFHI2MRB.js";
import "./chunk-4SBXAHR6.js";
import "./chunk-J26XOB2T.js";
import "./chunk-R7JMQMLD.js";
import {
  pauseGate,
  toApprovalPrompt
} from "./chunk-4V4TKQMB.js";
import "./chunk-FK7NXDRP.js";
import "./chunk-V4AXMN4X.js";
import {
  codeSystemPrompt
} from "./chunk-XHP6NYOT.js";
import {
  SkillStore
} from "./chunk-J4MYMBJ7.js";
import "./chunk-PLHAZOLZ.js";
import "./chunk-L3VPEESB.js";
import "./chunk-I4SH5Z7S.js";
import {
  countTokensBounded
} from "./chunk-BOWSNGQC.js";
import {
  DeepSeekClient,
  pickPrimaryBalance
} from "./chunk-QSKDP3OS.js";
import "./chunk-25T6CVUP.js";
import {
  formatHookOutcomeMessage,
  loadHooks,
  runHooks
} from "./chunk-NVI4XPOQ.js";
import "./chunk-6UNHNVJR.js";
import {
  deleteSession,
  detectGitBranch,
  listSessionsForWorkspace,
  loadSessionMessages,
  loadSessionMeta,
  patchSessionMeta,
  patchSessionWorkspaceIfMissing,
  rewriteSession,
  sessionPath,
  sessionsDir,
  timestampSuffix
} from "./chunk-P5SUHDUQ.js";
import {
  VERSION
} from "./chunk-XXC2BYTV.js";
import {
  loadDotenv
} from "./chunk-2UQP6H6T.js";
import "./chunk-U7G72DHQ.js";
import {
  DEFAULT_MODEL,
  bridgeEndpointEnv,
  describeQQAccess,
  isPlausibleKey,
  isReasoningEffort,
  loadApiKey,
  loadBraveApiKey,
  loadDesktopOpenTabs,
  loadEditMode,
  loadEditor,
  loadEndpoint,
  loadExaApiKey,
  loadMetasoApiKey,
  loadModel,
  loadOllamaApiKey,
  loadPerplexityApiKey,
  loadQQConfig,
  loadReasoningEffort,
  loadRecentWorkspaces,
  loadResolvedSkillPaths,
  loadShowSystemEvents,
  loadSubagentModels,
  loadTavilyApiKey,
  loadWorkspaceDir,
  parseMcpSpec,
  pushRecentWorkspace,
  readConfig,
  saveApiKey,
  saveBaseUrl,
  saveDesktopOpenTabs,
  saveEditMode,
  saveEditor,
  saveModel,
  saveQQConfig,
  saveReasoningEffort,
  saveShowSystemEvents,
  saveSubagentModels,
  saveWorkspaceDir,
  webSearchEngine,
  writeConfig
} from "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/cli/commands/desktop.ts
import { AsyncLocalStorage } from "async_hooks";
import { existsSync as existsSync2, statSync as statSync2, writeSync } from "fs";
import { readFile } from "fs/promises";
import { isAbsolute, join as join2, resolve } from "path";
import { stdin } from "process";
import { createInterface } from "readline";

// src/desktop/login-shell-path.ts
import { spawnSync } from "child_process";
var cached;
function resolveLoginShellPath(opts = {}) {
  if (cached !== void 0) return cached.value;
  cached = { value: null };
  if (process.platform === "win32") return null;
  const shell = process.env.SHELL || "/bin/bash";
  const marker = "__REASONIX_PATH__=";
  try {
    const result = spawnSync(shell, ["-ilc", `printf '${marker}%s\\n' "$PATH"`], {
      encoding: "utf8",
      timeout: opts.timeoutMs ?? 2e3,
      stdio: ["ignore", "pipe", "ignore"]
    });
    if (result.status !== 0 && result.signal === null) return null;
    const stdout = result.stdout ?? "";
    const idx = stdout.lastIndexOf(marker);
    if (idx < 0) return null;
    const tail = stdout.slice(idx + marker.length);
    const newline = tail.indexOf("\n");
    const path = (newline >= 0 ? tail.slice(0, newline) : tail).trim();
    if (!path || !path.includes("/")) return null;
    cached.value = path;
    return path;
  } catch {
    return null;
  }
}
function augmentProcessPath() {
  const loginPath = resolveLoginShellPath();
  if (!loginPath) return { added: [] };
  const current = process.env.PATH ?? "";
  const seen = new Set(
    current.split(":").map((s) => s.trim()).filter(Boolean)
  );
  const additions = [];
  for (const entry of loginPath.split(":")) {
    const t = entry.trim();
    if (!t || seen.has(t)) continue;
    seen.add(t);
    additions.push(t);
  }
  if (additions.length === 0) return { added: [] };
  process.env.PATH = additions.concat(current ? [current] : []).join(":");
  return { added: additions };
}

// src/desktop/qq-settings.ts
function trimOptional(value) {
  const trimmed = value?.trim();
  return trimmed ? trimmed : void 0;
}
function toPreview(appId) {
  if (!appId) return void 0;
  return appId.length > 6 ? `${appId.slice(0, 6)}...` : appId;
}
function toAccess(config) {
  return describeQQAccess({
    ownerOpenId: config.ownerOpenId,
    allowlist: config.allowlist
  });
}
function loadDesktopQQState(path) {
  const config = loadQQConfig(path);
  const configured = Boolean(config.appId && config.appSecret);
  return {
    ...config,
    sandbox: config.sandbox ?? false,
    enabled: config.enabled === true,
    configured,
    runtimeState: "disconnected",
    appIdPreview: toPreview(config.appId),
    access: toAccess(config)
  };
}
function saveDesktopQQSettings(patch, path) {
  const existing = loadQQConfig(path);
  saveQQConfig(
    {
      ...existing,
      appId: trimOptional(patch.appId),
      appSecret: trimOptional(patch.appSecret),
      sandbox: patch.sandbox
    },
    path
  );
  return loadDesktopQQState(path);
}
function setDesktopQQEnabled(enabled, path) {
  const existing = loadQQConfig(path);
  if (enabled && !(existing.appId && existing.appSecret)) {
    throw new Error("QQ App ID and App Secret are required.");
  }
  saveQQConfig({ ...existing, enabled }, path);
  return loadDesktopQQState(path);
}

// src/desktop/qq-turn-routing.ts
function createQQTurnRoutingState() {
  return {
    replyTabs: /* @__PURE__ */ new Set(),
    pendingByTab: /* @__PURE__ */ new Map()
  };
}
function markQQTurnStarted(state, tabId) {
  state.replyTabs.add(tabId);
}
function markQQTurnFinished(state, tabId) {
  state.replyTabs.delete(tabId);
  state.pendingByTab.delete(tabId);
}
function shouldRouteQQForTab(state, tabId) {
  return state.replyTabs.has(tabId);
}
function setQQPendingInteraction(state, tabId, gateId, kind, payload) {
  if (!shouldRouteQQForTab(state, tabId)) return;
  state.pendingByTab.set(tabId, { gateId, kind, payload });
}
function takeQQPendingInteraction(state, tabId) {
  const hit = state.pendingByTab.get(tabId);
  if (!hit) return null;
  state.pendingByTab.delete(tabId);
  return hit;
}
function clearQQTurnRouting(state) {
  state.replyTabs.clear();
  state.pendingByTab.clear();
}

// src/session-import.ts
import { existsSync, readFileSync, readdirSync, statSync } from "fs";
import { homedir } from "os";
import { basename, extname, join } from "path";
function parseExternalSessionFile(source, path) {
  if (!existsSync(path)) {
    throw new Error(`source file not found: ${path}`);
  }
  return source === "claude" ? parseClaudeSessionFile(path) : parseCodexSessionFile(path);
}
function buildImportedSessionName(source, path, imported) {
  const stem = basename(path, extname(path));
  const hint = oneLine(imported.nameHint || imported.summary || stem, 48);
  return `${source}-${hint || stem || "session"}`;
}
function importExternalSession(opts) {
  const imported = parseExternalSessionFile(opts.source, opts.path);
  if (imported.messages.length === 0) {
    throw new Error(`no importable chat messages found in ${opts.path}`);
  }
  const name = opts.name?.trim() || buildImportedSessionName(opts.source, opts.path, imported);
  const outputPath = sessionPath(name);
  if (existsSync(outputPath) && !opts.force) {
    throw new Error(`target session already exists: ${name}`);
  }
  rewriteSession(name, imported.messages);
  const workspace = opts.workspace?.trim() || imported.workspace;
  const summary = opts.summary?.trim() || imported.summary;
  const branch = workspace ? detectGitBranch(workspace) : void 0;
  patchSessionMeta(name, {
    workspace,
    summary,
    branch,
    importedSource: opts.source,
    importedPath: opts.path
  });
  return {
    source: opts.source,
    path: opts.path,
    name,
    messageCount: imported.messages.length,
    workspace,
    summary,
    branch
  };
}
function discoverExternalSessionApps() {
  return ["claude", "codex"].map((source) => {
    const root = defaultSessionRoot(source);
    const files = scanExternalSessionFiles(source);
    const latest = files[0];
    return {
      source,
      label: source === "claude" ? "Claude Code" : "Codex",
      root,
      available: files.length > 0,
      sessionCount: files.length,
      latestMtime: latest ? new Date(latest.mtimeMs).toISOString() : void 0
    };
  });
}
function importExternalSessions(opts) {
  let imported = 0;
  let skipped = 0;
  let failed = 0;
  let latestName;
  const existing = importedPathKeys();
  for (const source of opts.sources) {
    const files = scanExternalSessionFiles(source);
    for (const file of files) {
      const key = importKey(source, file.path);
      if (existing.has(key)) {
        skipped++;
        continue;
      }
      try {
        const result = importExternalSession({
          source,
          path: file.path,
          workspace: opts.workspace
        });
        existing.add(key);
        imported++;
        latestName ||= result.name;
      } catch {
        failed++;
      }
    }
  }
  return { imported, skipped, failed, latestName };
}
function defaultSessionRoot(source) {
  return source === "claude" ? join(homedir(), ".claude", "projects") : join(homedir(), ".codex", "sessions");
}
function scanExternalSessionFiles(source) {
  const root = defaultSessionRoot(source);
  const out = [];
  collectJsonl(root, source, out);
  out.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return out;
}
function collectJsonl(dir, source, out) {
  if (!existsSync(dir)) return;
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return;
  }
  for (const entry of entries) {
    const path = join(dir, entry);
    let stat;
    try {
      stat = statSync(path);
    } catch {
      continue;
    }
    if (stat.isDirectory()) {
      collectJsonl(path, source, out);
    } else if (stat.isFile() && entry.endsWith(".jsonl")) {
      out.push({ source, path, mtimeMs: stat.mtimeMs });
    }
  }
}
function importedPathKeys() {
  const out = /* @__PURE__ */ new Set();
  const dir = sessionsDir();
  if (!existsSync(dir)) return out;
  let files;
  try {
    files = readdirSync(dir);
  } catch {
    return out;
  }
  for (const file of files) {
    if (!file.endsWith(".jsonl") || file.endsWith(".events.jsonl")) continue;
    const name = file.replace(/\.jsonl$/, "");
    const meta = loadSessionMeta(name);
    if (meta.importedSource && meta.importedPath) {
      out.add(importKey(meta.importedSource, meta.importedPath));
    }
  }
  return out;
}
function importKey(source, path) {
  return `${source}:${path}`;
}
function parseClaudeSessionFile(path) {
  const records = readJsonl(path);
  const messages = [];
  const toolNames = /* @__PURE__ */ new Map();
  let workspace;
  let firstUserText;
  for (const record of records) {
    if (!workspace) workspace = firstString(record.cwd) || firstString(record.project);
    if (record.isMeta === true) continue;
    if (!record.message || typeof record.message !== "object") continue;
    const role = normalizeRole(record.message.role);
    if (!role) continue;
    if (role === "assistant") {
      const assistant = normalizeClaudeAssistant(record.message.content);
      for (const call of assistant.toolCalls) {
        if (call.id && call.function?.name) toolNames.set(call.id, call.function.name);
      }
      if (assistant.content || assistant.toolCalls.length > 0) {
        messages.push({
          role: "assistant",
          content: assistant.content || null,
          tool_calls: assistant.toolCalls.length > 0 ? assistant.toolCalls : void 0,
          reasoning_content: assistant.reasoning || void 0
        });
      }
      continue;
    }
    const user = normalizeClaudeUser(record.message.content, toolNames);
    if (user.content) {
      messages.push({ role: "user", content: user.content });
      if (!firstUserText) firstUserText = user.content;
    }
    messages.push(...user.toolMessages);
  }
  return {
    messages,
    workspace,
    nameHint: firstUserText,
    summary: summarize(firstUserText)
  };
}
function parseCodexSessionFile(path) {
  const records = readJsonl(path);
  const messages = [];
  const fallback = [];
  let workspace;
  let firstUserText;
  for (const record of records) {
    if (record.type === "session_meta" || record.type === "turn_context") {
      workspace ||= firstString(record.payload?.cwd);
    }
    if (record.type === "response_item" && record.payload?.type === "message") {
      const role = normalizeRole(record.payload.role);
      if (!role) continue;
      const content = normalizeCodexMessageContent(role, record.payload.content);
      if (!content) continue;
      messages.push({ role, content });
      if (role === "user" && !firstUserText) firstUserText = content;
      continue;
    }
    if (record.type === "event_msg") {
      const eventType = firstString(record.payload?.type);
      const content = firstString(record.payload?.message);
      if (!content) continue;
      if (eventType === "user_message") {
        fallback.push({ role: "user", content });
        if (!firstUserText) firstUserText = content;
      } else if (eventType === "agent_message") {
        fallback.push({ role: "assistant", content });
      }
    }
  }
  const importedMessages = messages.length > 0 ? messages : dedupeAdjacentMessages(fallback);
  return {
    messages: importedMessages,
    workspace,
    nameHint: firstUserText,
    summary: summarize(firstUserText)
  };
}
function normalizeClaudeAssistant(content) {
  if (typeof content === "string") {
    return { content: content.trim(), toolCalls: [] };
  }
  if (!Array.isArray(content)) {
    return { content: "", toolCalls: [] };
  }
  const textParts = [];
  const toolCalls = [];
  const reasoningParts = [];
  for (const item of content) {
    if (!item || typeof item !== "object") continue;
    const type = firstString(item.type);
    if (type === "text") {
      const text = firstString(item.text);
      if (text) textParts.push(text);
      continue;
    }
    if (type === "thinking") {
      const text = firstString(item.thinking);
      if (text) reasoningParts.push(text);
      continue;
    }
    if (type === "tool_use") {
      const name = firstString(item.name);
      if (!name) continue;
      toolCalls.push({
        id: firstString(item.id),
        type: "function",
        function: {
          name,
          arguments: safeJson(item.input ?? {})
        }
      });
    }
  }
  return {
    content: joinParts(textParts),
    toolCalls,
    reasoning: joinParts(reasoningParts) || void 0
  };
}
function normalizeClaudeUser(content, toolNames) {
  if (typeof content === "string") {
    return { content: content.trim(), toolMessages: [] };
  }
  if (!Array.isArray(content)) {
    return { content: "", toolMessages: [] };
  }
  const userText = [];
  const toolMessages = [];
  for (const item of content) {
    if (!item || typeof item !== "object") continue;
    const type = firstString(item.type);
    if (type === "text") {
      const text = firstString(item.text);
      if (text) userText.push(text);
      continue;
    }
    if (type === "image") {
      userText.push("[image omitted]");
      continue;
    }
    if (type === "tool_result") {
      const callId = firstString(item.tool_use_id);
      toolMessages.push({
        role: "tool",
        content: normalizeArbitraryContent(item.content),
        tool_call_id: callId,
        name: callId ? toolNames.get(callId) : void 0
      });
    }
  }
  return { content: joinParts(userText), toolMessages };
}
function normalizeCodexMessageContent(role, content) {
  if (typeof content === "string") return content.trim();
  if (!Array.isArray(content)) return "";
  const textParts = [];
  for (const item of content) {
    if (!item || typeof item !== "object") continue;
    const type = firstString(item.type);
    if (type === "input_text" || type === "output_text" || type === "text") {
      const text = firstString(item.text);
      if (!text) continue;
      if (role === "user" && looksLikeCodexBootstrapBlock(text)) continue;
      textParts.push(text);
    }
  }
  return joinParts(textParts);
}
function looksLikeCodexBootstrapBlock(text) {
  const trimmed = text.trimStart();
  return trimmed.startsWith("# AGENTS.md instructions for ") || trimmed.startsWith("<environment_context>");
}
function dedupeAdjacentMessages(messages) {
  const out = [];
  for (const msg of messages) {
    const prev = out[out.length - 1];
    if (prev && prev.role === msg.role && prev.content === msg.content) continue;
    out.push(msg);
  }
  return out;
}
function normalizeArbitraryContent(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    const textParts = value.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        return firstString(item.text);
      }
      return "";
    }).filter(Boolean);
    if (textParts.length > 0) return joinParts(textParts);
  }
  return safeJson(value);
}
function readJsonl(path) {
  const raw = readFileSync(path, "utf8");
  return raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).flatMap((line) => {
    try {
      return [JSON.parse(line)];
    } catch {
      return [];
    }
  });
}
function normalizeRole(value) {
  return value === "user" || value === "assistant" ? value : void 0;
}
function firstString(value) {
  return typeof value === "string" && value.trim().length > 0 ? value : void 0;
}
function safeJson(value) {
  try {
    return JSON.stringify(value ?? null);
  } catch {
    return JSON.stringify(String(value));
  }
}
function joinParts(parts) {
  return parts.map((part) => part.trim()).filter(Boolean).join("\n\n");
}
function summarize(text) {
  const flat = oneLine(text || "", 120);
  return flat || void 0;
}
function oneLine(text, max) {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}...` : flat;
}

// src/cli/commands/desktop.ts
function desktopUserAbortLoopOptions() {
  return void 0;
}
var desktopQqRuntimeSnapshot = {
  runtimeState: "disconnected"
};
var STDOUT_BACKPRESSURE_WAIT = new Int32Array(new SharedArrayBuffer(4));
var SESSION_TITLE_MAX_CHARS = 200;
function normalizeSessionTitle(raw) {
  return raw.replace(/\s+/g, " ").trim().slice(0, SESSION_TITLE_MAX_CHARS);
}
function writeAllSync(fd, buffer, opts = {}) {
  const write = opts.write ?? writeSync;
  const wait = opts.wait ?? (() => Atomics.wait(STDOUT_BACKPRESSURE_WAIT, 0, 0, 5));
  let offset = 0;
  while (offset < buffer.length) {
    let written;
    try {
      written = write(fd, buffer, offset, buffer.length - offset);
    } catch (err) {
      if (err.code === "EAGAIN") {
        wait();
        continue;
      }
      throw err;
    }
    if (written <= 0) throw new Error("stdout write returned 0 bytes");
    offset += written;
  }
}
function emit(ev, tabId) {
  const payload = tabId ? { ...ev, tabId } : ev;
  writeAllSync(1, Buffer.from(`${JSON.stringify(payload)}
`, "utf8"));
}
function tailLines(s, n) {
  if (!s) return "";
  const lines = s.split(/\r?\n/);
  return lines.slice(-n).join("\n");
}
var LOADED_RECENT_MESSAGE_WINDOW = 200;
var LOADED_MIN_ELIDE_CHARS = 4096;
var LOADED_ELIDED_PREFIX = "[elided \u2014 older than the last ";
function elideLoadedField(value) {
  if (value.length <= LOADED_MIN_ELIDE_CHARS) return value;
  if (value.startsWith(LOADED_ELIDED_PREFIX)) return value;
  return `${LOADED_ELIDED_PREFIX}${LOADED_RECENT_MESSAGE_WINDOW} messages; ${value.length.toLocaleString()} chars dropped to save memory. Full content is on disk in the session log.]`;
}
function elideLoadedMessages(messages) {
  if (messages.length < LOADED_RECENT_MESSAGE_WINDOW) return messages;
  const cutoff = messages.length - LOADED_RECENT_MESSAGE_WINDOW;
  return messages.map((msg, i) => {
    if (i >= cutoff || msg.kind !== "assistant") return msg;
    return {
      ...msg,
      segments: msg.segments.map((segment) => {
        switch (segment.kind) {
          case "reasoning":
          case "text":
            return { ...segment, text: elideLoadedField(segment.text) };
          case "tool":
            return {
              ...segment,
              args: elideLoadedField(segment.args),
              ...segment.result !== void 0 ? { result: elideLoadedField(segment.result) } : {}
            };
          default:
            return segment;
        }
      })
    };
  });
}
function buildLoadedMessages(records) {
  const out = [];
  let turn = 0;
  let pendingAssistantIdx = -1;
  for (const rec of records) {
    if (rec.role === "system") continue;
    if (rec.role === "user") {
      out.push({ kind: "user", text: rec.content ?? "" });
      pendingAssistantIdx = -1;
      continue;
    }
    if (rec.role === "assistant") {
      turn++;
      const segments = [];
      if (rec.reasoning_content) segments.push({ kind: "reasoning", text: rec.reasoning_content });
      if (rec.content) segments.push({ kind: "text", text: rec.content });
      if (rec.tool_calls) {
        for (let i = 0; i < rec.tool_calls.length; i++) {
          const tc = rec.tool_calls[i];
          if (!tc) continue;
          segments.push({
            kind: "tool",
            callId: tc.id ?? `tc-r-${turn}-${i}`,
            name: tc.function?.name ?? "",
            args: tc.function?.arguments ?? ""
          });
        }
      }
      out.push({ kind: "assistant", turn, segments, pending: false });
      pendingAssistantIdx = out.length - 1;
      continue;
    }
    if (rec.role === "tool") {
      if (pendingAssistantIdx < 0) continue;
      const host = out[pendingAssistantIdx];
      if (host?.kind !== "assistant") continue;
      const callId = rec.tool_call_id;
      if (!callId) continue;
      const seg = host.segments.find((s) => s.kind === "tool" && s.callId === callId);
      if (seg && seg.kind === "tool") {
        seg.result = rec.content ?? "";
        seg.ok = !/error|failed/i.test(seg.result.slice(0, 200));
      }
    }
  }
  return elideLoadedMessages(out);
}
function maskApiKey(key) {
  if (!key) return void 0;
  if (key.length <= 7) return `${key.slice(0, 2)}\u2026`;
  return `${key.slice(0, 6)}\u2026${key.slice(-3)}`;
}
function collectWebSearchApiKeyPrefixes() {
  return {
    metaso: maskApiKey(loadMetasoApiKey()),
    tavily: maskApiKey(loadTavilyApiKey()),
    perplexity: maskApiKey(loadPerplexityApiKey()),
    exa: maskApiKey(loadExaApiKey()),
    ollama: maskApiKey(loadOllamaApiKey()),
    brave: maskApiKey(loadBraveApiKey())
  };
}
function emitSettings(tab) {
  const ep = loadEndpoint();
  const editMode = loadEditMode();
  if (tab.toolset) applyPlanMode(tab.toolset.tools, editMode);
  const recent = loadRecentWorkspaces().filter((p) => p !== tab.rootDir);
  emit(
    {
      type: "$settings",
      reasoningEffort: loadReasoningEffort(),
      editMode,
      budgetUsd: tab.runtime?.loop.budgetUsd ?? null,
      baseUrl: ep.baseUrl,
      apiKeyPrefix: ep.apiKey ? `${ep.apiKey.slice(0, 6)}\u2026${ep.apiKey.slice(-3)}` : void 0,
      workspaceDir: tab.rootDir,
      recentWorkspaces: recent,
      model: tab.currentModel,
      editor: loadEditor(),
      webSearchEngine: webSearchEngine(),
      webSearchEndpoint: readConfig().webSearchEndpoint,
      webSearchApiKeys: collectWebSearchApiKeyPrefixes(),
      subagentModels: loadSubagentModels(),
      showSystemEvents: loadShowSystemEvents(),
      version: VERSION
    },
    tab.id
  );
}
function emitQQSettings(tab) {
  const base = loadDesktopQQState();
  emit(
    {
      type: "$qq_settings",
      ...base,
      runtimeState: desktopQqRuntimeSnapshot.runtimeState,
      lastError: desktopQqRuntimeSnapshot.lastError
    },
    tab.id
  );
}
async function emitBalance(tab) {
  if (!tab.runtime) return;
  const bal = await tab.runtime.loop.client.getBalance().catch(() => null);
  if (!bal) return;
  const primary = pickPrimaryBalance(bal.balance_infos);
  if (!primary) return;
  const balanceInfos = bal.balance_infos.map((info) => ({
    currency: info.currency,
    total: Number(info.total_balance),
    granted: info.granted_balance ? Number(info.granted_balance) : void 0,
    toppedUp: info.topped_up_balance ? Number(info.topped_up_balance) : void 0
  }));
  emit(
    {
      type: "$balance",
      currency: primary.currency,
      total: Number(primary.total_balance),
      isAvailable: bal.is_available,
      balanceInfos
    },
    tab.id
  );
}
function emitSessions(tab) {
  try {
    const items = listSessionsForWorkspace(tab.rootDir).map((s) => ({
      name: s.name,
      messageCount: s.messageCount,
      mtime: s.mtime.toISOString(),
      summary: s.meta.summary,
      workspaceStatus: s.workspaceStatus
    }));
    emit({ type: "$sessions", items }, tab.id);
  } catch (err) {
    emit({ type: "$error", message: `session_list failed: ${err.message}` }, tab.id);
  }
}
function loadSessionIntoTab(tab, name, actions) {
  const records = loadSessionMessages(name);
  const backfilledWorkspace = patchSessionWorkspaceIfMissing(name, tab.rootDir);
  const meta = loadSessionMeta(name);
  if (tab.aborter) tab.switching = true;
  actions.abortTurn(tab);
  actions.cancelPendingGates(tab);
  tab.currentSession = name;
  actions.persistOpenTabs();
  if (tab.runtime) tab.runtime = buildRuntimeFor(tab);
  const loadedMessages = buildLoadedMessages(records);
  if (loadedMessages.length === 0) {
    let sizeBytes = 0;
    try {
      sizeBytes = statSync2(sessionPath(name)).size;
    } catch {
    }
    process.stderr.write(
      `session_load: "${name}" returned 0 messages (file size=${sizeBytes}B) \u2014 empty or unreadable jsonl
`
    );
    emit({ type: "$session_empty", name, sizeBytes }, tab.id);
  }
  emit(
    {
      type: "$session_loaded",
      name,
      messages: loadedMessages,
      carryover: {
        totalCostUsd: meta.totalCostUsd ?? 0,
        cacheHitTokens: meta.cacheHitTokens ?? 0,
        cacheMissTokens: meta.cacheMissTokens ?? 0,
        totalCompletionTokens: meta.totalCompletionTokens ?? 0
      }
    },
    tab.id
  );
  emitCtxBreakdown(tab);
  if (backfilledWorkspace) emitSessions(tab);
}
function summarizeMcpSpec(raw) {
  try {
    const parsed = parseMcpSpec(raw);
    if (parsed.transport === "stdio") {
      const argv = [parsed.command, ...parsed.args].join(" ");
      return {
        raw,
        name: parsed.name,
        transport: "stdio",
        summary: `stdio \xB7 ${argv}`,
        status: "configured"
      };
    }
    return {
      raw,
      name: parsed.name,
      transport: parsed.transport,
      summary: `${parsed.transport} \xB7 ${parsed.url}`,
      status: "configured"
    };
  } catch (err) {
    return {
      raw,
      name: null,
      transport: "stdio",
      summary: raw,
      parseError: err.message,
      status: "failed",
      statusReason: err.message
    };
  }
}
function emitMcpSpecs(tab) {
  const cfg = readConfig();
  const specs = (cfg.mcp ?? []).map((raw) => {
    const base = summarizeMcpSpec(raw);
    const live = tab.mcpStatuses.get(raw);
    if (!live) return base;
    return { ...base, status: live.kind, statusReason: live.reason, toolCount: live.toolCount };
  });
  const bridged = specs.length > 0 && specs.every((s) => s.status === "connected");
  emit({ type: "$mcp_specs", specs, bridged }, tab.id);
}
function emitMemory(tab) {
  try {
    const entries = collectMemoryEntriesForWorkspace(tab.rootDir);
    emit({ type: "$memory", entries }, tab.id);
  } catch (err) {
    emit({ type: "$error", message: `memory_get failed: ${err.message}` }, tab.id);
  }
}
function countTokensForMeter(text) {
  try {
    return countTokensBounded(text);
  } catch {
    return text.length === 0 ? 0 : Math.max(1, Math.ceil(text.length * 0.3));
  }
}
function emitCtxBreakdown(tab) {
  if (!tab.runtime) return;
  const sys = countTokensForMeter(tab.runtime.loop.prefix.system);
  const tools = countTokensForMeter(JSON.stringify(tab.runtime.loop.prefix.toolSpecs));
  let logTokens = 0;
  try {
    logTokens = tab.runtime.loop.getCurrentLogTokens();
  } catch {
    for (const msg of tab.runtime.loop.log.toMessages()) {
      logTokens += countTokensForMeter(typeof msg.content === "string" ? msg.content : "");
      if (msg.role === "assistant" && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) {
        logTokens += countTokensForMeter(JSON.stringify(msg.tool_calls));
      }
    }
  }
  emit({ type: "$ctx_breakdown", reservedTokens: sys + tools, logTokens }, tab.id);
}
function emitSkills(tab) {
  try {
    const store = new SkillStore({
      projectRoot: tab.rootDir,
      customSkillPaths: loadResolvedSkillPaths(tab.rootDir),
      subagentModels: loadSubagentModels()
    });
    const items = store.list().map((s) => ({
      name: s.name,
      description: s.description,
      scope: s.scope,
      path: s.path,
      runAs: s.runAs,
      model: s.model
    }));
    emit({ type: "$skills", items }, tab.id);
  } catch (err) {
    emit({ type: "$error", message: `skills_get failed: ${err.message}` }, tab.id);
  }
}
var tabCounter = 0;
function nextTabId() {
  tabCounter++;
  return `t${tabCounter}`;
}
function mintSessionFor(rootDir) {
  const name = `desktop-${timestampSuffix()}-${tabCounter}`;
  try {
    patchSessionMeta(name, { workspace: rootDir });
  } catch {
  }
  return name;
}
function buildRuntimeFor(tab) {
  if (!tab.toolset) throw new Error("buildRuntimeFor called before initTabToolset finished");
  const toolset = tab.toolset;
  applyPlanMode(toolset.tools, loadEditMode());
  const ep = loadEndpoint();
  const client = new DeepSeekClient({ apiKey: ep.apiKey, baseUrl: ep.baseUrl });
  const prefix = new ImmutablePrefix({ system: tab.system, toolSpecs: toolset.tools.specs() });
  const reasoningEffort = loadReasoningEffort();
  const loop = new CacheFirstLoop({
    client,
    prefix,
    tools: toolset.tools,
    model: tab.currentModel,
    budgetUsd: tab.budgetUsd,
    session: tab.currentSession,
    reasoningEffort,
    hooks: tab.hooks,
    hookCwd: tab.rootDir
  });
  const eventizer = new Eventizer();
  const ctx = { model: tab.currentModel, prefixHash: prefix.fingerprint, reasoningEffort };
  return { loop, eventizer, ctx };
}
var TS_EXPORT_RE = /^export\s+(?:default\s+)?(?:async\s+)?(function|class|const|let|var|interface|type|enum)\s+\*?\s*(\w+)/;
var FILE_INDEX_TTL_MS = 1e4;
async function getFileIndexFor(tab) {
  const fresh = tab.fileIndex && Date.now() - tab.fileIndexBuiltAt < FILE_INDEX_TTL_MS;
  if (fresh) return tab.fileIndex;
  if (tab.fileIndexBuilding) return tab.fileIndexBuilding;
  tab.fileIndexBuilding = listFilesWithStatsAsync(tab.rootDir, { maxResults: 5e3 }).then((res) => {
    tab.fileIndex = res;
    tab.fileIndexBuiltAt = Date.now();
    tab.fileIndexBuilding = null;
    return res;
  }).catch((err) => {
    tab.fileIndexBuilding = null;
    throw err;
  });
  return tab.fileIndexBuilding;
}
async function getSymbolIndexFor(tab) {
  if (tab.symbolIndex) return tab.symbolIndex;
  if (tab.symbolBuilding) return tab.symbolBuilding;
  tab.symbolBuilding = (async () => {
    const files = await getFileIndexFor(tab);
    const sourceExts = /\.(?:ts|tsx|js|jsx|mts|cts)$/;
    const candidates = files.filter((f) => sourceExts.test(f.path)).slice(0, 1500);
    const out = [];
    const PARALLEL = 16;
    for (let i = 0; i < candidates.length; i += PARALLEL) {
      const batch = candidates.slice(i, i + PARALLEL);
      await Promise.all(
        batch.map(async (entry) => {
          const abs = isAbsolute(entry.path) ? entry.path : join2(tab.rootDir, entry.path);
          try {
            const text = await readFile(abs, "utf8");
            const lines = text.split(/\r?\n/);
            for (let li = 0; li < lines.length; li++) {
              const line = lines[li];
              if (!line.startsWith("export ")) continue;
              const m = TS_EXPORT_RE.exec(line);
              if (m) out.push({ kind: m[1], name: m[2], path: entry.path, line: li + 1 });
            }
          } catch {
          }
        })
      );
    }
    tab.symbolIndex = out;
    tab.symbolBuilding = null;
    return out;
  })().catch((err) => {
    tab.symbolBuilding = null;
    throw err;
  });
  return tab.symbolBuilding;
}
function rankSymbols(syms, q, limit) {
  const needle = q.toLowerCase();
  const scored = [];
  for (const s of syms) {
    const lower = s.name.toLowerCase();
    let score;
    if (lower === needle) score = 0;
    else if (lower.startsWith(needle)) score = 100;
    else if (lower.includes(needle)) score = 500 + lower.indexOf(needle);
    else continue;
    scored.push({ entry: s, score });
  }
  scored.sort((a, b) => a.score - b.score || a.entry.name.localeCompare(b.entry.name));
  return scored.slice(0, limit).map((s) => `${s.entry.path}:${s.entry.line}`);
}
function pushMentionRecent(tab, path) {
  const MAX = 20;
  const idx = tab.recentMentions.indexOf(path);
  if (idx >= 0) tab.recentMentions.splice(idx, 1);
  tab.recentMentions.unshift(path);
  if (tab.recentMentions.length > MAX) tab.recentMentions.length = MAX;
}
function installDesktopCrashGuards(stderr = process.stderr) {
  process.on("unhandledRejection", (reason) => {
    const err = reason instanceof Error ? reason : new Error(String(reason));
    stderr.write(`[desktop] unhandledRejection: ${err.stack ?? err.message}
`);
  });
  process.on("uncaughtException", (err) => {
    stderr.write(`[desktop] uncaughtException: ${err.stack ?? err.message}
`);
  });
}
async function desktopCommand(opts) {
  loadDotenv();
  const augmented = augmentProcessPath();
  if (augmented.added.length > 0) {
    process.stderr.write(
      `[desktop] augmented PATH with ${augmented.added.length} login-shell entries
`
    );
  }
  installDesktopCrashGuards();
  const tabs = /* @__PURE__ */ new Map();
  const tabContext = new AsyncLocalStorage();
  let lastActiveTabId = "";
  function activeRunningTab() {
    const id = tabContext.getStore();
    return id ? tabs.get(id) : void 0;
  }
  let first;
  const qqRuntime = {
    channel: null,
    runtimeState: "disconnected",
    lastError: void 0,
    routing: createQQTurnRoutingState()
  };
  function currentQqSettings() {
    const base = loadDesktopQQState();
    return {
      type: "$qq_settings",
      ...base,
      runtimeState: qqRuntime.runtimeState,
      lastError: qqRuntime.lastError
    };
  }
  function activeDesktopTab() {
    return (lastActiveTabId ? tabs.get(lastActiveTabId) : void 0) ?? first;
  }
  function broadcastQQSettings() {
    for (const tab of tabs.values()) emit(currentQqSettings(), tab.id);
  }
  function setQQRuntimeState(runtimeState, lastError) {
    qqRuntime.runtimeState = runtimeState;
    qqRuntime.lastError = lastError;
    desktopQqRuntimeSnapshot.runtimeState = runtimeState;
    desktopQqRuntimeSnapshot.lastError = lastError;
    broadcastQQSettings();
  }
  function sendQQInfo(message) {
    const tab = activeDesktopTab();
    if (tab) {
      emit(
        {
          type: "status",
          id: Date.now(),
          ts: (/* @__PURE__ */ new Date()).toISOString(),
          turn: 0,
          text: message
        },
        tab.id
      );
    }
    void qqRuntime.channel?.sendResponse(message).catch((err) => {
      const active = activeDesktopTab();
      if (active) {
        emit({ type: "$error", message: `qq send failed: ${err.message}` }, active.id);
      }
    });
  }
  function parseIndexedChoice(text) {
    const rawIndex = text.match(/^(\d+)/)?.[1];
    return rawIndex ? Number.parseInt(rawIndex, 10) - 1 : -1;
  }
  function parseRunPermissionChoice(text) {
    const lower = text.toLowerCase();
    if (lower.includes("1") || lower.includes("run")) return "run_once";
    if (lower.includes("2") || lower.includes("always")) return "always_allow";
    return "deny";
  }
  function parsePlanChoice(text) {
    const lower = text.toLowerCase();
    if (lower.includes("1") || lower.includes("approve")) return "approve";
    if (lower.includes("2") || lower.includes("refine")) return "refine";
    return "cancel";
  }
  function parseCheckpointChoice(text) {
    const lower = text.toLowerCase();
    if (lower.includes("1") || lower.includes("continue")) return "continue";
    if (lower.includes("2") || lower.includes("revise")) return "revise";
    return "stop";
  }
  function parseRevisionChoice(text) {
    const lower = text.toLowerCase();
    if (lower.includes("1") || lower.includes("accept")) return "accept";
    if (lower.includes("2") || lower.includes("reject")) return "reject";
    return "cancel";
  }
  function stripFollowupPrefix(text) {
    return text.replace(
      /^(?:\d+\s*|approve\s*|refine\s*|cancel\s*|continue\s*|revise\s*|stop\s*|accept\s*|reject\s*|run\s*|always\s*|deny\s*)/iu,
      ""
    ).trim();
  }
  function handleQQPauseReply(tab, text) {
    const pending = takeQQPendingInteraction(qqRuntime.routing, tab.id);
    if (!pending) return false;
    const followup = stripFollowupPrefix(text);
    const interaction = pending;
    const gateId = pending.gateId;
    switch (interaction.kind) {
      case "run_command":
      case "run_background":
      case "path_access":
        pauseGate.resolve(gateId, parseRunPermissionChoice(text));
        return true;
      case "plan_proposed": {
        const payload = interaction.payload ?? {};
        const choice = parsePlanChoice(text);
        if (choice === "cancel") {
          pauseGate.cancel(gateId);
        } else {
          pauseGate.resolve(gateId, {
            type: choice === "approve" ? "approve" : "refine",
            feedback: followup,
            override: {
              plan: payload.plan ?? "",
              mode: choice === "approve" ? "approve" : "refine"
            }
          });
        }
        return true;
      }
      case "plan_checkpoint": {
        const payload = interaction.payload ?? {};
        const choice = parseCheckpointChoice(text);
        if (choice === "revise") {
          pauseGate.resolve(gateId, {
            type: "revise",
            feedback: followup,
            checkpoint: { stepId: payload.stepId ?? "", title: payload.title }
          });
        } else {
          pauseGate.resolve(gateId, { type: choice });
        }
        return true;
      }
      case "plan_revision":
        pauseGate.resolve(gateId, parseRevisionChoice(text));
        return true;
      case "choice": {
        const payload = interaction.payload ?? {};
        const options = payload.options ?? [];
        const pickedIndex = parseIndexedChoice(text);
        if (pickedIndex >= 0 && pickedIndex < options.length) {
          const selected = options[pickedIndex];
          if (selected) pauseGate.resolve(gateId, { type: "pick", optionId: selected.id });
          return true;
        }
        for (const option of options) {
          if (text.toLowerCase().includes(option.title.toLowerCase())) {
            pauseGate.resolve(gateId, { type: "pick", optionId: option.id });
            return true;
          }
        }
        pauseGate.resolve(
          gateId,
          payload.allowCustom ? { type: "text", text } : { type: "cancel" }
        );
        return true;
      }
      default:
        return false;
    }
  }
  function handleQQPauseRequest(tab, kind, payload) {
    if (!qqRuntime.channel || !shouldRouteQQForTab(qqRuntime.routing, tab.id)) return;
    let qqMessage = "";
    switch (kind) {
      case "run_command":
      case "run_background": {
        const p = payload;
        qqMessage = `Need confirmation

Command: \`${p.command}\`

Reply with:
1. Run once
2. Always allow
3. Deny`;
        break;
      }
      case "path_access": {
        const p = payload;
        const intentText = p.intent === "read" ? "Read" : "Write";
        qqMessage = `Need file access confirmation

Action: ${intentText}
Path: ${p.path}
Tool: ${p.toolName}

Reply with:
1. Run once
2. Always allow
3. Deny`;
        break;
      }
      case "plan_proposed": {
        const p = payload;
        qqMessage = `Plan confirmation

${p.plan}

Reply with:
1. Approve
2. Refine
3. Cancel`;
        break;
      }
      case "plan_checkpoint": {
        const p = payload;
        qqMessage = `Step complete (${tab.completedStepIds.size}/${tab.planTotalSteps})

${p.title ? `Step: ${p.title}
` : ""}Result: ${p.result}

Reply with:
1. Continue
2. Revise
3. Stop`;
        break;
      }
      case "plan_revision": {
        const p = payload;
        qqMessage = `Plan revision proposed

${p.reason}

Reply with:
1. Accept
2. Reject
3. Cancel`;
        break;
      }
      case "choice": {
        const p = payload;
        const optionsList = p.options.map((opt, idx) => `${idx + 1}. ${opt.title}`).join("\n");
        qqMessage = `Please choose

${p.question}

Options:
${optionsList}${p.allowCustom ? "\n\n(You can also reply with custom text.)" : ""}`;
        break;
      }
    }
    if (qqMessage) {
      void qqRuntime.channel.sendResponse(qqMessage).catch((err) => {
        emit({ type: "$error", message: `qq send failed: ${err.message}` }, tab.id);
      });
    }
  }
  async function startDesktopQQ(shouldPersistEnabled = true) {
    const current = loadQQConfig();
    if (!(current.appId && current.appSecret)) {
      throw new Error("QQ App ID and App Secret are required.");
    }
    if (qqRuntime.channel) {
      qqRuntime.channel.refreshAccessConfig();
      setQQRuntimeState("connected");
      return;
    }
    setQQRuntimeState("connecting");
    const channel = new QQChannel({
      onSubmitMessage: (text) => {
        const tab = activeDesktopTab();
        if (!tab) return;
        const trimmed = text.trim();
        if (!trimmed) return;
        emit(
          {
            type: "user.message",
            id: Date.now(),
            ts: (/* @__PURE__ */ new Date()).toISOString(),
            turn: 0,
            text: trimmed
          },
          tab.id
        );
        if (handleQQPauseReply(tab, trimmed)) return;
        if (tab.aborter) {
          void channel.sendResponse(
            "Session is busy. Wait for the current turn or reply to the pending prompt."
          ).catch(() => void 0);
          return;
        }
        void runTurn(tab, trimmed, true);
      },
      onError: (message) => {
        const tab = activeDesktopTab();
        setQQRuntimeState("failed", message);
        if (tab) emit({ type: "$error", message: `QQ: ${message}` }, tab.id);
      }
    });
    try {
      await channel.start();
      qqRuntime.channel = channel;
      if (shouldPersistEnabled) setDesktopQQEnabled(true);
      setQQRuntimeState("connected");
    } catch (err) {
      await channel.stop().catch(() => void 0);
      qqRuntime.channel = null;
      if (shouldPersistEnabled) setDesktopQQEnabled(false);
      setQQRuntimeState("failed", err.message);
      throw err;
    }
  }
  async function stopDesktopQQ(shouldDisable = true) {
    const channel = qqRuntime.channel;
    qqRuntime.channel = null;
    clearQQTurnRouting(qqRuntime.routing);
    if (channel) await channel.stop();
    if (shouldDisable) setDesktopQQEnabled(false);
    setQQRuntimeState("disconnected");
  }
  function createTabSkeleton(initialDir) {
    const dir = resolve(initialDir ?? opts.dir ?? loadWorkspaceDir() ?? process.cwd());
    pushRecentWorkspace(dir);
    const model = opts.model || loadModel() || DEFAULT_MODEL;
    const tab = {
      id: nextTabId(),
      rootDir: dir,
      currentSession: "",
      currentModel: model,
      budgetUsd: opts.budgetUsd,
      toolset: null,
      system: "",
      runtime: null,
      aborter: null,
      fileIndex: null,
      fileIndexBuilding: null,
      fileIndexBuiltAt: 0,
      symbolIndex: null,
      symbolBuilding: null,
      recentMentions: [],
      pendingGateIds: /* @__PURE__ */ new Set(),
      completedStepIds: /* @__PURE__ */ new Set(),
      planTotalSteps: 0,
      mcpRuntime: null,
      mcpStatuses: /* @__PURE__ */ new Map(),
      switching: false,
      hooks: loadHooks({ projectRoot: dir })
    };
    tab.currentSession = mintSessionFor(dir);
    tabs.set(tab.id, tab);
    return tab;
  }
  async function initTabToolset(tab) {
    const toolset = await buildCodeToolset({
      rootDir: tab.rootDir,
      onSkillInstalled: () => emitSkills(tab),
      onJobsChanged: () => emitJobs()
    });
    tab.toolset = toolset;
    tab.system = codeSystemPrompt(tab.rootDir, {
      hasSemanticSearch: toolset.semantic.enabled,
      modelId: tab.currentModel
    });
    if (loadApiKey()) {
      bridgeEndpointEnv();
      tab.runtime = buildRuntimeFor(tab);
      void bridgeTabMcp(tab);
    }
  }
  function bridgeTabMcp(tab) {
    if (!tab.runtime || !tab.toolset) return Promise.resolve();
    if (tab.mcpRuntime) {
      return tab.mcpRuntime.reloadFromConfig(tab.runtime.loop).then(() => emitMcpSpecs(tab)).catch((err) => {
        emit({ type: "$error", message: `mcp reload failed: ${err.message}` }, tab.id);
      });
    }
    const requested = (readConfig().mcp ?? []).length;
    if (requested === 0) return Promise.resolve();
    const runtime = createMcpRuntime({
      getTools: () => {
        if (!tab.toolset) throw new Error("toolset gone");
        return tab.toolset.tools;
      },
      getMcpPrefix: () => void 0,
      getRequestedCount: () => requested,
      getWorkspaceDir: () => tab.rootDir,
      progressSink: { current: null }
    });
    tab.mcpRuntime = runtime;
    runtime.setLifecycleSink((notice) => {
      if (notice.kind === "slow") return;
      const cfg = readConfig().mcp ?? [];
      const target = cfg.find((raw) => {
        try {
          return parseMcpSpec(raw).name === notice.name;
        } catch {
          return false;
        }
      });
      if (!target) return;
      if (notice.kind === "handshake") {
        tab.mcpStatuses.set(target, { kind: "handshake" });
      } else if (notice.kind === "connected") {
        tab.mcpStatuses.set(target, { kind: "connected", toolCount: notice.tools });
      } else if (notice.kind === "failed") {
        tab.mcpStatuses.set(target, { kind: "failed", reason: notice.reason });
      } else if (notice.kind === "disabled") {
        tab.mcpStatuses.set(target, { kind: "disabled" });
      }
      emitMcpSpecs(tab);
    });
    return runtime.reloadFromConfig(tab.runtime.loop).then(() => void 0).catch((err) => {
      emit({ type: "$error", message: `mcp bridge failed: ${err.message}` }, tab.id);
    });
  }
  function persistOpenTabs() {
    try {
      saveDesktopOpenTabs(
        Array.from(tabs.values()).map((t) => ({
          dir: t.rootDir,
          session: t.currentSession || void 0,
          active: t.id === lastActiveTabId
        }))
      );
    } catch {
    }
  }
  async function closeTab(tab) {
    abortTurn(tab);
    try {
      await tab.toolset?.jobs.shutdown();
    } catch {
    }
    if (tab.mcpRuntime) {
      try {
        await tab.mcpRuntime.closeAll();
      } catch {
      }
    }
    tabs.delete(tab.id);
    if (first && first.id === tab.id) {
      const next = tabs.values().next().value;
      if (next) first = next;
    }
    persistOpenTabs();
    emit({ type: "$tab_closed" }, tab.id);
  }
  async function runTurn(tab, text, fromQQ = false) {
    if (!tab.runtime) return;
    const rt = tab.runtime;
    tab.aborter = new AbortController();
    if (fromQQ) markQQTurnStarted(qqRuntime.routing, tab.id);
    let lastAssistantText = "";
    if (tab.currentSession) {
      const existing = loadSessionMeta(tab.currentSession).summary;
      if (!existing || !existing.trim()) {
        const summary = text.replace(/\s+/g, " ").trim().slice(0, 60);
        if (summary) {
          try {
            patchSessionMeta(tab.currentSession, { summary });
          } catch {
          }
        }
      }
    }
    if (tab.hooks.some((h) => h.event === "UserPromptSubmit")) {
      const report = await runHooks({
        hooks: tab.hooks,
        payload: { event: "UserPromptSubmit", cwd: tab.rootDir, prompt: text }
      });
      for (const o of report.outcomes) {
        if (o.decision === "pass") continue;
        emit({ type: "$error", message: formatHookOutcomeMessage(o) }, tab.id);
      }
      if (report.blocked) {
        tab.aborter = null;
        emit({ type: "$turn_complete" }, tab.id);
        if (fromQQ) markQQTurnFinished(qqRuntime.routing, tab.id);
        return;
      }
    }
    await tabContext.run(tab.id, async () => {
      try {
        let emittedTurnContext = false;
        for await (const ev of rt.loop.step(text)) {
          if (!emittedTurnContext) {
            emittedTurnContext = true;
            emitCtxBreakdown(tab);
          }
          if (ev.role === "assistant_final" && ev.content) {
            lastAssistantText = ev.content;
          }
          for (const kev of rt.eventizer.consume(ev, rt.ctx)) emit(kev, tab.id);
          if (ev.role === "assistant_final" || ev.role === "tool") {
            emitCtxBreakdown(tab);
          }
          if (ev.role === "tool" && (ev.toolName === "remember" || ev.toolName === "forget")) {
            emitMemory(tab);
          }
          if (tab.aborter?.signal.aborted) break;
        }
      } catch (err) {
        emit({ type: "$error", message: err.message }, tab.id);
      } finally {
        tab.aborter = null;
        if (!tab.switching) {
          if (fromQQ && lastAssistantText && qqRuntime.channel && shouldRouteQQForTab(qqRuntime.routing, tab.id)) {
            await qqRuntime.channel.sendResponse(lastAssistantText).catch((err) => {
              emit(
                { type: "$error", message: `qq send failed: ${err.message}` },
                tab.id
              );
            });
          }
          emit({ type: "$turn_complete" }, tab.id);
          if (tab.planTotalSteps > 0 && tab.completedStepIds.size >= tab.planTotalSteps) {
            tab.completedStepIds.clear();
            tab.planTotalSteps = 0;
            emit({ type: "$plan_cleared" }, tab.id);
          }
          emitSessions(tab);
          void emitBalance(tab);
          if (tab.hooks.some((h) => h.event === "Stop")) {
            const stopReport = await runHooks({
              hooks: tab.hooks,
              payload: {
                event: "Stop",
                cwd: tab.rootDir,
                lastAssistantText,
                turn: rt.loop.stats.summary().turns
              }
            });
            for (const o of stopReport.outcomes) {
              if (o.decision === "pass") continue;
              emit({ type: "$error", message: formatHookOutcomeMessage(o) }, tab.id);
            }
          }
        }
        if (fromQQ) markQQTurnFinished(qqRuntime.routing, tab.id);
        tab.switching = false;
      }
    });
  }
  async function switchWorkspace(tab, nextDir) {
    const target = resolve(nextDir);
    if (target === tab.rootDir) {
      emitSettings(tab);
      return;
    }
    if (!existsSync2(target) || !statSync2(target).isDirectory()) {
      emit({ type: "$error", message: `Workspace not found: ${target}` }, tab.id);
      emitSettings(tab);
      return;
    }
    abortTurn(tab);
    try {
      await tab.toolset?.jobs.shutdown();
    } catch {
    }
    tab.rootDir = target;
    saveWorkspaceDir(target);
    pushRecentWorkspace(target);
    tab.fileIndex = null;
    tab.fileIndexBuilding = null;
    tab.fileIndexBuiltAt = 0;
    tab.symbolIndex = null;
    tab.symbolBuilding = null;
    tab.recentMentions.length = 0;
    tab.hooks = loadHooks({ projectRoot: target });
    tab.currentSession = mintSessionFor(target);
    tab.toolset = await buildCodeToolset({
      rootDir: target,
      onSkillInstalled: () => emitSkills(tab),
      onJobsChanged: () => emitJobs()
    });
    tab.system = codeSystemPrompt(target, {
      hasSemanticSearch: tab.toolset.semantic.enabled,
      modelId: tab.currentModel
    });
    if (tab.runtime) tab.runtime = buildRuntimeFor(tab);
    emitSessions(tab);
    emitSettings(tab);
    emitSkills(tab);
    persistOpenTabs();
  }
  function forgetGate(id) {
    for (const t of tabs.values()) {
      if (t.pendingGateIds.delete(id)) return t;
    }
    return void 0;
  }
  function abortTurn(tab, opts2 = {}) {
    tab.aborter?.abort();
    tab.runtime?.loop.abort(opts2);
  }
  function tabSessionLabel(tab) {
    if (tab.currentSession) {
      try {
        const summary = loadSessionMeta(tab.currentSession).summary?.trim();
        if (summary) return summary;
      } catch {
      }
    }
    return tab.rootDir.split(/[\\/]/).filter(Boolean).pop() ?? tab.rootDir;
  }
  function emitJobs() {
    const items = [];
    for (const t of tabs.values()) {
      const reg = t.toolset?.jobs;
      if (!reg) continue;
      const label = tabSessionLabel(t);
      for (const j of reg.list()) {
        items.push({
          id: j.id,
          tabId: t.id,
          sessionLabel: label,
          command: j.command,
          pid: j.pid,
          running: j.running,
          exitCode: j.exitCode,
          startedAt: j.startedAt,
          outputTail: tailLines(j.output, 8),
          spawnError: j.spawnError
        });
      }
    }
    items.sort((a, b) => {
      if (a.running !== b.running) return a.running ? -1 : 1;
      return b.startedAt - a.startedAt;
    });
    emit({ type: "$jobs", items });
  }
  async function stopJob(jobId) {
    for (const t of tabs.values()) {
      const reg = t.toolset?.jobs;
      if (!reg) continue;
      const hit = reg.list().find((j) => j.id === jobId);
      if (!hit) continue;
      await reg.stop(jobId);
      return true;
    }
    return false;
  }
  async function stopAllJobs() {
    const ops = [];
    for (const t of tabs.values()) {
      const reg = t.toolset?.jobs;
      if (!reg) continue;
      for (const j of reg.list()) {
        if (j.running) ops.push(reg.stop(j.id));
      }
    }
    await Promise.allSettled(ops);
  }
  function cancelPendingGates(tab) {
    const hadActivePlan = tab.planTotalSteps > 0 || tab.completedStepIds.size > 0;
    const ids = [...tab.pendingGateIds];
    tab.pendingGateIds.clear();
    for (const id of ids) pauseGate.cancel(id);
    if (hadActivePlan) {
      tab.completedStepIds.clear();
      tab.planTotalSteps = 0;
      emit({ type: "$plan_cleared" }, tab.id);
    }
  }
  let shuttingDown = false;
  async function gracefulShutdown() {
    if (shuttingDown) return;
    shuttingDown = true;
    await stopDesktopQQ(false).catch(() => void 0);
    await Promise.allSettled(
      [...tabs.values()].map((t) => t.toolset?.jobs.shutdown(1500) ?? Promise.resolve())
    );
    process.exit(0);
  }
  process.on("SIGTERM", () => {
    void gracefulShutdown();
  });
  process.on("SIGINT", () => {
    void gracefulShutdown();
  });
  pauseGate.on((req) => {
    const tab = activeRunningTab();
    const tabId = tab?.id;
    if (tab) tab.pendingGateIds.add(req.id);
    const auto = autoResolveVerdict(req, loadEditMode());
    if (auto !== null) {
      if (req.kind === "plan_checkpoint") {
        const payload = req.payload;
        if (tab) tab.completedStepIds.add(payload.stepId);
        emit(
          {
            type: "$step_completed",
            stepId: payload.stepId,
            title: payload.title,
            result: payload.result,
            notes: payload.notes
          },
          tabId
        );
      }
      if (tab) tab.pendingGateIds.delete(req.id);
      pauseGate.resolve(req.id, auto);
      return;
    }
    if (req.kind === "run_command" || req.kind === "run_background") {
      const payload = req.payload;
      if (tab) setQQPendingInteraction(qqRuntime.routing, tab.id, req.id, req.kind, payload);
      emit(
        {
          type: "$confirm_required",
          id: req.id,
          kind: req.kind,
          command: payload.command ?? "",
          prompt: toApprovalPrompt({
            id: req.id,
            kind: req.kind,
            payload
          })
        },
        tabId
      );
      if (tab) handleQQPauseRequest(tab, req.kind, payload);
      return;
    }
    if (req.kind === "path_access") {
      const payload = req.payload;
      if (tab) setQQPendingInteraction(qqRuntime.routing, tab.id, req.id, req.kind, payload);
      emit(
        {
          type: "$path_access_required",
          id: req.id,
          path: payload.path,
          intent: payload.intent,
          toolName: payload.toolName,
          sandboxRoot: payload.sandboxRoot,
          allowPrefix: payload.allowPrefix,
          prompt: toApprovalPrompt({
            id: req.id,
            kind: req.kind,
            payload
          })
        },
        tabId
      );
      if (tab) handleQQPauseRequest(tab, req.kind, payload);
      return;
    }
    if (req.kind === "choice") {
      const payload = req.payload;
      if (tab) setQQPendingInteraction(qqRuntime.routing, tab.id, req.id, req.kind, payload);
      emit(
        {
          type: "$choice_required",
          id: req.id,
          question: payload.question,
          options: payload.options,
          allowCustom: payload.allowCustom
        },
        tabId
      );
      if (tab) handleQQPauseRequest(tab, req.kind, payload);
      return;
    }
    if (req.kind === "plan_proposed") {
      const payload = req.payload;
      if (tab) {
        tab.completedStepIds.clear();
        tab.planTotalSteps = payload.steps?.length ?? 0;
        setQQPendingInteraction(qqRuntime.routing, tab.id, req.id, req.kind, payload);
      }
      emit(
        {
          type: "$plan_required",
          id: req.id,
          plan: payload.plan,
          steps: payload.steps,
          summary: payload.summary
        },
        tabId
      );
      if (tab) handleQQPauseRequest(tab, req.kind, payload);
      return;
    }
    if (req.kind === "plan_checkpoint") {
      const payload = req.payload;
      if (tab) {
        tab.completedStepIds.add(payload.stepId);
        setQQPendingInteraction(qqRuntime.routing, tab.id, req.id, req.kind, payload);
      }
      emit(
        {
          type: "$step_completed",
          stepId: payload.stepId,
          title: payload.title,
          result: payload.result,
          notes: payload.notes
        },
        tabId
      );
      emit(
        {
          type: "$checkpoint_required",
          id: req.id,
          stepId: payload.stepId,
          title: payload.title,
          result: payload.result,
          notes: payload.notes,
          completed: tab?.completedStepIds.size ?? 0,
          total: tab?.planTotalSteps ?? 0
        },
        tabId
      );
      if (tab) handleQQPauseRequest(tab, req.kind, payload);
      return;
    }
    if (req.kind === "plan_revision") {
      const payload = req.payload;
      if (tab) setQQPendingInteraction(qqRuntime.routing, tab.id, req.id, req.kind, payload);
      emit(
        {
          type: "$revision_required",
          id: req.id,
          reason: payload.reason,
          remainingSteps: payload.remainingSteps,
          summary: payload.summary
        },
        tabId
      );
      if (tab) handleQQPauseRequest(tab, req.kind, payload);
      return;
    }
    const exhaustive = req.kind;
    process.stderr.write(
      `[desktop] no handler for pause kind "${String(exhaustive)}" \u2014 auto-cancelling gate id=${req.id}
`
    );
    if (tab) tab.pendingGateIds.delete(req.id);
    pauseGate.cancel(req.id);
  });
  function bootstrapTab(initialDir, restore) {
    const tab = createTabSkeleton(initialDir);
    let restoredMessages;
    if (restore?.session) {
      try {
        if (existsSync2(sessionPath(restore.session))) {
          const msgs = buildLoadedMessages(loadSessionMessages(restore.session));
          if (msgs.length > 0) {
            tab.currentSession = restore.session;
            restoredMessages = msgs;
          }
        }
      } catch {
      }
    }
    emit({ type: "$tab_opened", workspaceDir: tab.rootDir, active: restore?.active }, tab.id);
    emitSessions(tab);
    emitSettings(tab);
    emitMcpSpecs(tab);
    emitSkills(tab);
    emitMemory(tab);
    emitQQSettings(tab);
    if (restoredMessages) {
      const meta = loadSessionMeta(tab.currentSession);
      emit(
        {
          type: "$session_loaded",
          name: tab.currentSession,
          messages: restoredMessages,
          carryover: {
            totalCostUsd: meta.totalCostUsd ?? 0,
            cacheHitTokens: meta.cacheHitTokens ?? 0,
            cacheMissTokens: meta.cacheMissTokens ?? 0,
            totalCompletionTokens: meta.totalCompletionTokens ?? 0
          }
        },
        tab.id
      );
    }
    if (!loadApiKey()) emit({ type: "$needs_setup", reason: "no_api_key" }, tab.id);
    void emitBalance(tab);
    void initTabToolset(tab).then(() => {
      if (loadApiKey()) emit({ type: "$ready" }, tab.id);
      emitCtxBreakdown(tab);
    }).catch((err) => {
      emit({ type: "$error", message: `init failed: ${err.message}` }, tab.id);
    });
    return tab;
  }
  const savedTabs = loadDesktopOpenTabs().filter((t) => {
    try {
      return existsSync2(t.dir) && statSync2(t.dir).isDirectory();
    } catch {
      return false;
    }
  });
  const startupDir = opts.dir;
  const startupTab = startupDir ? savedTabs.find((t) => resolve(t.dir) === resolve(startupDir)) : savedTabs[0];
  first = bootstrapTab(opts.dir ?? savedTabs[0]?.dir, startupTab);
  const restored = [first];
  for (const t of savedTabs.slice(1)) restored.push(bootstrapTab(t.dir, t));
  const activeIdx = savedTabs.findIndex((t) => t.active);
  lastActiveTabId = ((activeIdx >= 0 ? restored[activeIdx] : first) ?? first).id;
  persistOpenTabs();
  const qqConfig = loadQQConfig();
  if (qqConfig.enabled && qqConfig.appId && qqConfig.appSecret) {
    void startDesktopQQ(false).catch(() => void 0);
  } else {
    broadcastQQSettings();
  }
  const rl = createInterface({ input: stdin });
  rl.on("line", (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let msg;
    try {
      msg = JSON.parse(trimmed);
    } catch {
      emit({ type: "$error", message: `bad json on stdin: ${trimmed.slice(0, 80)}` });
      return;
    }
    if (msg.cmd === "tab_open") {
      try {
        const opened = bootstrapTab(msg.workspaceDir, { active: true });
        lastActiveTabId = opened.id;
        persistOpenTabs();
      } catch (err) {
        emit({ type: "$error", message: `tab_open failed: ${err.message}` });
      }
      return;
    }
    if (msg.cmd === "tab_activate") {
      if (tabs.has(msg.tabId)) {
        lastActiveTabId = msg.tabId;
        persistOpenTabs();
      }
      return;
    }
    if (msg.cmd === "confirm_response") {
      forgetGate(msg.id);
      pauseGate.resolve(msg.id, msg.response);
      return;
    }
    if (msg.cmd === "choice_response") {
      forgetGate(msg.id);
      pauseGate.resolve(msg.id, msg.response);
      return;
    }
    if (msg.cmd === "plan_response") {
      const tab2 = forgetGate(msg.id);
      if (tab2 && msg.response.type === "cancel") {
        tab2.completedStepIds.clear();
        tab2.planTotalSteps = 0;
        emit({ type: "$plan_cleared" }, tab2.id);
      }
      pauseGate.resolve(msg.id, msg.response);
      return;
    }
    if (msg.cmd === "checkpoint_response") {
      const tab2 = forgetGate(msg.id);
      if (tab2 && msg.response.type === "stop") {
        tab2.completedStepIds.clear();
        tab2.planTotalSteps = 0;
        emit({ type: "$plan_cleared" }, tab2.id);
      }
      pauseGate.resolve(msg.id, msg.response);
      return;
    }
    if (msg.cmd === "revision_response") {
      forgetGate(msg.id);
      pauseGate.resolve(msg.id, msg.response);
      return;
    }
    if (msg.cmd === "setup_save_key") {
      const key = msg.key.trim();
      if (!isPlausibleKey(key)) {
        emit({
          type: "$error",
          message: "Key looks too short \u2014 paste the full token (16+ chars, no spaces)."
        });
        return;
      }
      try {
        saveApiKey(key);
        bridgeEndpointEnv();
        for (const tab2 of tabs.values()) {
          if (!tab2.toolset) {
            emitSettings(tab2);
            void emitBalance(tab2);
            continue;
          }
          tab2.runtime = buildRuntimeFor(tab2);
          emit({ type: "$ready" }, tab2.id);
          emitSettings(tab2);
          void emitBalance(tab2);
        }
      } catch (err) {
        emit({ type: "$error", message: `saveApiKey failed: ${err.message}` });
      }
      return;
    }
    if (msg.cmd === "desktop_resync") {
      const hasKey = !!loadApiKey();
      for (const t of tabs.values()) {
        emit(
          { type: "$tab_opened", workspaceDir: t.rootDir, active: t.id === lastActiveTabId },
          t.id
        );
        emitSessions(t);
        emitSettings(t);
        emitMcpSpecs(t);
        emitSkills(t);
        emitMemory(t);
        emitQQSettings(t);
        if (!hasKey) emit({ type: "$needs_setup", reason: "no_api_key" }, t.id);
        else if (t.toolset) emit({ type: "$ready" }, t.id);
        void emitBalance(t);
        if (t.currentSession) {
          try {
            const msgs = buildLoadedMessages(loadSessionMessages(t.currentSession));
            const meta = loadSessionMeta(t.currentSession);
            emit(
              {
                type: "$session_loaded",
                name: t.currentSession,
                messages: msgs,
                carryover: {
                  totalCostUsd: meta.totalCostUsd ?? 0,
                  cacheHitTokens: meta.cacheHitTokens ?? 0,
                  cacheMissTokens: meta.cacheMissTokens ?? 0,
                  totalCompletionTokens: meta.totalCompletionTokens ?? 0
                }
              },
              t.id
            );
          } catch {
          }
        }
        emitCtxBreakdown(t);
      }
      return;
    }
    if (msg.cmd === "jobs_list") {
      emitJobs();
      return;
    }
    if (msg.cmd === "jobs_stop") {
      void stopJob(msg.jobId).finally(() => emitJobs());
      return;
    }
    if (msg.cmd === "jobs_stop_all") {
      void stopAllJobs().finally(() => emitJobs());
      return;
    }
    const tab = msg.tabId ? tabs.get(msg.tabId) : first;
    if (!tab) {
      process.stderr.write(
        `rpc dispatch: unknown tabId=${msg.tabId} for cmd=${msg.cmd} \u2014 dropping
`
      );
      return;
    }
    if (msg.cmd === "abort") {
      abortTurn(tab, desktopUserAbortLoopOptions());
      cancelPendingGates(tab);
      return;
    }
    if (msg.cmd === "tab_close") {
      void closeTab(tab);
      return;
    }
    if (msg.cmd === "mcp_specs_get") {
      emitMcpSpecs(tab);
      return;
    }
    if (msg.cmd === "mcp_specs_add") {
      const spec = msg.spec.trim();
      if (!spec) {
        emit({ type: "$error", message: "mcp_specs_add: spec is empty" }, tab.id);
        return;
      }
      try {
        parseMcpSpec(spec);
      } catch (err) {
        emit({ type: "$error", message: `mcp_specs_add: ${err.message}` }, tab.id);
        return;
      }
      try {
        const cfg = readConfig();
        const list = cfg.mcp ?? [];
        if (!list.includes(spec)) {
          cfg.mcp = [...list, spec];
          writeConfig(cfg);
        }
        emitMcpSpecs(tab);
        void bridgeTabMcp(tab);
      } catch (err) {
        emit({ type: "$error", message: `mcp_specs_add: ${err.message}` }, tab.id);
      }
      return;
    }
    if (msg.cmd === "mcp_specs_remove") {
      try {
        const cfg = readConfig();
        const list = cfg.mcp ?? [];
        if (list.includes(msg.spec)) {
          cfg.mcp = list.filter((s) => s !== msg.spec);
          writeConfig(cfg);
        }
        tab.mcpStatuses.delete(msg.spec);
        emitMcpSpecs(tab);
        void bridgeTabMcp(tab);
      } catch (err) {
        emit({ type: "$error", message: `mcp_specs_remove: ${err.message}` }, tab.id);
      }
      return;
    }
    if (msg.cmd === "skills_get") {
      emitSkills(tab);
      return;
    }
    if (msg.cmd === "skill_run") {
      if (!tab.runtime) {
        emit(
          { type: "$error", message: "Not configured yet \u2014 paste your DeepSeek API key first." },
          tab.id
        );
        return;
      }
      try {
        const store = new SkillStore({
          projectRoot: tab.rootDir,
          customSkillPaths: loadResolvedSkillPaths(tab.rootDir)
        });
        const found = store.read(msg.name);
        if (!found) {
          emit({ type: "$error", message: `skill not found: ${msg.name}` }, tab.id);
          return;
        }
        const extra = msg.args?.trim() ?? "";
        const header = `# Skill: ${found.name}${found.description ? `
> ${found.description}` : ""}`;
        const argsLine = extra ? `

Arguments: ${extra}` : "";
        const payload = `${header}

${found.body}${argsLine}`;
        void runTurn(tab, payload);
      } catch (err) {
        emit({ type: "$error", message: `skill_run: ${err.message}` }, tab.id);
      }
      return;
    }
    if (msg.cmd === "session_list") {
      emitSessions(tab);
      return;
    }
    if (msg.cmd === "session_delete") {
      deleteSession(msg.name);
      emitSessions(tab);
      return;
    }
    if (msg.cmd === "session_rename") {
      try {
        const trimmed2 = normalizeSessionTitle(msg.title);
        patchSessionMeta(msg.name, { summary: trimmed2 || void 0 });
        emitSessions(tab);
      } catch (err) {
        emit(
          { type: "$error", message: `session_rename failed: ${err.message}` },
          tab.id
        );
      }
      return;
    }
    if (msg.cmd === "session_import") {
      try {
        const result = importExternalSession({
          source: msg.source,
          path: msg.path,
          name: msg.name,
          workspace: tab.rootDir
        });
        emitSessions(tab);
        loadSessionIntoTab(tab, result.name, {
          abortTurn,
          cancelPendingGates,
          persistOpenTabs
        });
      } catch (err) {
        emit(
          { type: "$error", message: `session_import failed: ${err.message}` },
          tab.id
        );
      }
      return;
    }
    if (msg.cmd === "session_import_scan") {
      try {
        emit({ type: "$session_import_sources", apps: discoverExternalSessionApps() }, tab.id);
      } catch (err) {
        emit(
          { type: "$error", message: `session_import_scan failed: ${err.message}` },
          tab.id
        );
      }
      return;
    }
    if (msg.cmd === "session_import_bulk") {
      try {
        const result = importExternalSessions({
          sources: msg.sources,
          workspace: tab.rootDir
        });
        emitSessions(tab);
        emit(
          {
            type: "$session_import_result",
            imported: result.imported,
            skipped: result.skipped,
            failed: result.failed
          },
          tab.id
        );
        if (result.latestName) {
          loadSessionIntoTab(tab, result.latestName, {
            abortTurn,
            cancelPendingGates,
            persistOpenTabs
          });
        }
      } catch (err) {
        emit(
          { type: "$error", message: `session_import_bulk failed: ${err.message}` },
          tab.id
        );
      }
      return;
    }
    if (msg.cmd === "session_load") {
      try {
        loadSessionIntoTab(tab, msg.name, {
          abortTurn,
          cancelPendingGates,
          persistOpenTabs
        });
      } catch (err) {
        process.stderr.write(`session_load: "${msg.name}" threw \u2014 ${err.message}
`);
        emit({ type: "$error", message: `session_load failed: ${err.message}` }, tab.id);
      }
      return;
    }
    if (msg.cmd === "memory_read") {
      try {
        const detail = readMemoryEntryDetail({ path: msg.path }, tab.rootDir);
        emit({ type: "$memory_detail", detail }, tab.id);
      } catch (err) {
        emit({ type: "$error", message: `memory_read failed: ${err.message}` }, tab.id);
      }
      return;
    }
    if (msg.cmd === "new_chat") {
      if (tab.aborter) tab.switching = true;
      abortTurn(tab);
      cancelPendingGates(tab);
      tab.currentSession = mintSessionFor(tab.rootDir);
      persistOpenTabs();
      if (tab.runtime) tab.runtime = buildRuntimeFor(tab);
      emitSessions(tab);
      return;
    }
    if (msg.cmd === "settings_get") {
      emitSettings(tab);
      return;
    }
    if (msg.cmd === "qq_status_get") {
      emitQQSettings(tab);
      return;
    }
    if (msg.cmd === "settings_save") {
      try {
        if (msg.reasoningEffort !== void 0 && isReasoningEffort(msg.reasoningEffort)) {
          saveReasoningEffort(msg.reasoningEffort);
          tab.runtime?.loop.configure({ reasoningEffort: msg.reasoningEffort });
        }
        if (msg.editMode !== void 0) {
          saveEditMode(msg.editMode);
          if (tab.toolset) applyPlanMode(tab.toolset.tools, msg.editMode);
        }
        if (msg.budgetUsd !== void 0) {
          tab.budgetUsd = msg.budgetUsd ?? void 0;
          tab.runtime?.loop.setBudget(msg.budgetUsd);
        }
        if (msg.baseUrl !== void 0) saveBaseUrl(msg.baseUrl);
        if (msg.workspaceDir !== void 0) {
          void switchWorkspace(tab, msg.workspaceDir);
          return;
        }
        if (msg.editor !== void 0) saveEditor(msg.editor);
        if (msg.showSystemEvents !== void 0) saveShowSystemEvents(msg.showSystemEvents);
        if (msg.webSearchEngine !== void 0 || msg.webSearchEndpoint !== void 0 || msg.metasoApiKey !== void 0 || msg.tavilyApiKey !== void 0 || msg.perplexityApiKey !== void 0 || msg.exaApiKey !== void 0 || msg.ollamaApiKey !== void 0 || msg.braveApiKey !== void 0) {
          const cfg = readConfig();
          if (msg.webSearchEngine !== void 0) cfg.webSearchEngine = msg.webSearchEngine;
          if (msg.webSearchEndpoint !== void 0) {
            cfg.webSearchEndpoint = msg.webSearchEndpoint?.trim() || void 0;
          }
          if (msg.metasoApiKey !== void 0) {
            cfg.metasoApiKey = msg.metasoApiKey?.trim() || void 0;
          }
          if (msg.tavilyApiKey !== void 0) {
            cfg.tavilyApiKey = msg.tavilyApiKey?.trim() || void 0;
          }
          if (msg.perplexityApiKey !== void 0) {
            cfg.perplexityApiKey = msg.perplexityApiKey?.trim() || void 0;
          }
          if (msg.exaApiKey !== void 0) {
            cfg.exaApiKey = msg.exaApiKey?.trim() || void 0;
          }
          if (msg.ollamaApiKey !== void 0) {
            cfg.ollamaApiKey = msg.ollamaApiKey?.trim() || void 0;
          }
          if (msg.braveApiKey !== void 0) {
            cfg.braveApiKey = msg.braveApiKey?.trim() || void 0;
          }
          writeConfig(cfg);
        }
        if (msg.subagentModels !== void 0) {
          saveSubagentModels(msg.subagentModels);
          emitSkills(tab);
        }
        if (msg.model !== void 0) {
          const next = msg.model.trim();
          if (next) {
            tab.currentModel = next;
            saveModel(next);
            if (tab.toolset) {
              tab.system = codeSystemPrompt(tab.rootDir, {
                hasSemanticSearch: tab.toolset.semantic.enabled,
                modelId: tab.currentModel
              });
              if (tab.runtime) tab.runtime = buildRuntimeFor(tab);
            }
          }
        }
        emitSettings(tab);
      } catch (err) {
        emit(
          { type: "$error", message: `settings_save failed: ${err.message}` },
          tab.id
        );
      }
      return;
    }
    if (msg.cmd === "qq_config_save") {
      try {
        saveDesktopQQSettings(
          {
            appId: msg.appId,
            appSecret: msg.appSecret,
            sandbox: msg.sandbox
          },
          void 0
        );
        emitQQSettings(tab);
      } catch (err) {
        emit(
          { type: "$error", message: `qq_config_save failed: ${err.message}` },
          tab.id
        );
      }
      return;
    }
    if (msg.cmd === "qq_connect") {
      try {
        const current = loadQQConfig();
        emit(
          {
            type: "status",
            id: Date.now(),
            ts: (/* @__PURE__ */ new Date()).toISOString(),
            turn: 0,
            text: `QQ connecting (${current.sandbox ? "sandbox" : "production"})`
          },
          tab.id
        );
        void startDesktopQQ(true).then(
          () => {
            emit(
              {
                type: "status",
                id: Date.now(),
                ts: (/* @__PURE__ */ new Date()).toISOString(),
                turn: 0,
                text: `QQ connected (${current.sandbox ? "sandbox" : "production"})`
              },
              tab.id
            );
            emitQQSettings(tab);
          },
          (err) => {
            emit(
              { type: "$error", message: `qq_connect failed: ${err.message}` },
              tab.id
            );
            emitQQSettings(tab);
          }
        );
      } catch (err) {
        emit({ type: "$error", message: `qq_connect failed: ${err.message}` }, tab.id);
        emitQQSettings(tab);
      }
      return;
    }
    if (msg.cmd === "qq_disconnect") {
      try {
        void stopDesktopQQ(true).then(
          () => {
            emit(
              {
                type: "status",
                id: Date.now(),
                ts: (/* @__PURE__ */ new Date()).toISOString(),
                turn: 0,
                text: "QQ disabled"
              },
              tab.id
            );
            emitQQSettings(tab);
          },
          (err) => {
            emit(
              { type: "$error", message: `qq_disconnect failed: ${err.message}` },
              tab.id
            );
          }
        );
      } catch (err) {
        emit(
          { type: "$error", message: `qq_disconnect failed: ${err.message}` },
          tab.id
        );
      }
      return;
    }
    if (msg.cmd === "mention_query") {
      const nonce = msg.nonce;
      const query = msg.query;
      const parsed = parseAtQuery(query);
      const treeWalk = parsed.trailingSlash || query.length === 0;
      if (treeWalk) {
        void listDirectory(tab.rootDir, parsed.dir).then((entries) => {
          const results = entries.map((e) => e.isDir ? `${e.path}/` : e.path);
          emit({ type: "$mention_results", nonce, query, results }, tab.id);
        }).catch((err) => {
          emit(
            { type: "$error", message: `mention_query (dir) failed: ${err.message}` },
            tab.id
          );
          emit({ type: "$mention_results", nonce, query, results: [] }, tab.id);
        });
        return;
      }
      const wantSymbols = query.length >= 2 && !query.includes("/");
      void (async () => {
        try {
          const files = await getFileIndexFor(tab);
          const fileResults = rankPickerCandidates(files, query, {
            limit: wantSymbols ? 19 : 25,
            recentlyUsed: tab.recentMentions
          });
          let symResults = [];
          if (wantSymbols) {
            const syms = await getSymbolIndexFor(tab);
            symResults = rankSymbols(syms, query, 6);
          }
          emit(
            { type: "$mention_results", nonce, query, results: [...symResults, ...fileResults] },
            tab.id
          );
        } catch (err) {
          emit(
            { type: "$error", message: `mention_query failed: ${err.message}` },
            tab.id
          );
          emit({ type: "$mention_results", nonce, query, results: [] }, tab.id);
        }
      })();
      return;
    }
    if (msg.cmd === "mention_picked") {
      pushMentionRecent(tab, msg.path);
      return;
    }
    if (msg.cmd === "mention_preview") {
      const nonce = msg.nonce;
      const rel = msg.path;
      const abs = isAbsolute(rel) ? rel : join2(tab.rootDir, rel);
      const safeAbs = resolve(abs);
      const safeRoot = resolve(tab.rootDir);
      if (!safeAbs.startsWith(safeRoot)) {
        emit({ type: "$mention_preview", nonce, path: rel, head: "", totalLines: 0 }, tab.id);
        return;
      }
      void readFile(safeAbs, "utf8").then((text) => {
        const lines = text.split(/\r?\n/);
        if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
        const head = lines.slice(0, 12).join("\n");
        emit(
          { type: "$mention_preview", nonce, path: rel, head, totalLines: lines.length },
          tab.id
        );
      }).catch(() => {
        emit({ type: "$mention_preview", nonce, path: rel, head: "", totalLines: 0 }, tab.id);
      });
      return;
    }
    if (msg.cmd === "compact_history") {
      if (!tab.runtime) return;
      void tab.runtime.loop.compactHistory().then(() => emitCtxBreakdown(tab)).catch((err) => {
        emit({ type: "$error", message: `/compact failed: ${err.message}` }, tab.id);
      });
      return;
    }
    if (msg.cmd === "retry") {
      if (!tab.runtime) return;
      const prev = tab.runtime.loop.retryLastUser();
      if (prev) {
        emit({ type: "$retry_result", text: prev }, tab.id);
      }
      return;
    }
    if (msg.cmd === "btw") {
      if (!tab.runtime) return;
      const question = msg.text.trim();
      if (!question) return;
      void (async () => {
        try {
          const reply = await tab.runtime.loop.client.chat({
            model: tab.currentModel,
            messages: [
              {
                role: "system",
                content: "You are answering a side question that is unrelated to the current coding conversation. Answer concisely (1-3 sentences) in plain prose. Do not call tools, do not ask clarifying questions, and do not reference any prior turns."
              },
              { role: "user", content: question }
            ]
          });
          const answer = (typeof reply.content === "string" ? reply.content.trim() : "") || "(no answer)";
          emit({ type: "$btw_result", question, answer }, tab.id);
        } catch (err) {
          emit({ type: "$error", message: `/btw failed: ${err.message}` }, tab.id);
        }
      })();
      return;
    }
    if (msg.cmd === "user_input") {
      if (!tab.runtime) {
        emit(
          { type: "$error", message: "Not configured yet \u2014 paste your DeepSeek API key first." },
          tab.id
        );
        return;
      }
      void runTurn(tab, msg.text);
    }
  });
  await new Promise((resolve2) => {
    rl.on("close", () => {
      void gracefulShutdown();
      resolve2();
    });
  });
}
export {
  buildLoadedMessages,
  desktopCommand,
  desktopUserAbortLoopOptions,
  installDesktopCrashGuards,
  normalizeSessionTitle,
  writeAllSync
};
//# sourceMappingURL=desktop-AUBW2SLL.js.map