#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  sanitizeName,
  sessionsDir
} from "./chunk-P5SUHDUQ.js";

// src/code/checkpoints.ts
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "fs";
import { homedir } from "os";
import { dirname, join, relative, resolve, sep } from "path";
function sanitizeRoot(rootDir) {
  return resolve(rootDir).replace(/[\\/:]+/g, "_").replace(/^_+/, "");
}
function storeRoot(rootDir) {
  return join(homedir(), ".reasonix", "sessions", sanitizeRoot(rootDir), "checkpoints");
}
function indexPath(rootDir) {
  return join(storeRoot(rootDir), "index.json");
}
function snapshotPath(rootDir, id) {
  return join(storeRoot(rootDir), `${id}.json`);
}
function listCheckpoints(rootDir) {
  const path = indexPath(rootDir);
  if (!existsSync(path)) return [];
  try {
    const raw = readFileSync(path, "utf8");
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m) => typeof m === "object" && m !== null && typeof m.id === "string" && typeof m.name === "string" && typeof m.createdAt === "number" && typeof m.source === "string" && typeof m.fileCount === "number" && typeof m.bytes === "number"
    );
  } catch {
    return [];
  }
}
function writeIndex(rootDir, items) {
  const path = indexPath(rootDir);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(items, null, 2), "utf8");
}
function loadCheckpoint(rootDir, id) {
  const path = snapshotPath(rootDir, id);
  if (!existsSync(path)) return null;
  try {
    const raw = readFileSync(path, "utf8");
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && Array.isArray(parsed.files)) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}
function createCheckpoint(opts) {
  const absRoot = resolve(opts.rootDir);
  const id = `cp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  const files = [];
  let bytes = 0;
  const seen = /* @__PURE__ */ new Set();
  for (const p of opts.paths) {
    if (seen.has(p)) continue;
    seen.add(p);
    const abs = resolve(absRoot, p);
    if (abs !== absRoot && !abs.startsWith(`${absRoot}${sep}`)) continue;
    const rel = relative(absRoot, abs).split(sep).join("/");
    if (existsSync(abs)) {
      try {
        const content = readFileSync(abs, "utf8");
        files.push({ path: rel, content });
        bytes += content.length;
      } catch {
        files.push({ path: rel, content: null });
      }
    } else {
      files.push({ path: rel, content: null });
    }
  }
  const checkpoint = {
    id,
    name: opts.name,
    rootDir: absRoot,
    createdAt: Date.now(),
    source: opts.source ?? "manual",
    files,
    bytes
  };
  const cpPath = snapshotPath(absRoot, id);
  mkdirSync(dirname(cpPath), { recursive: true });
  writeFileSync(cpPath, JSON.stringify(checkpoint), "utf8");
  const meta = {
    id,
    name: opts.name,
    createdAt: checkpoint.createdAt,
    source: checkpoint.source,
    fileCount: files.length,
    bytes
  };
  const items = listCheckpoints(absRoot);
  items.push(meta);
  writeIndex(absRoot, items);
  return meta;
}
function findCheckpoint(rootDir, idOrName) {
  const items = listCheckpoints(rootDir);
  const byId = items.find((m) => m.id === idOrName);
  if (byId) return byId;
  const byName = [...items].reverse().find((m) => m.name === idOrName);
  return byName ?? null;
}
function restoreCheckpoint(rootDir, id) {
  const cp = loadCheckpoint(rootDir, id);
  const absRoot = resolve(rootDir);
  const result = { restored: [], removed: [], skipped: [] };
  if (!cp) {
    result.skipped.push({ path: "(checkpoint)", reason: `not found: ${id}` });
    return result;
  }
  for (const f of cp.files) {
    const abs = resolve(absRoot, f.path);
    if (abs !== absRoot && !abs.startsWith(`${absRoot}${sep}`)) {
      result.skipped.push({ path: f.path, reason: "path escapes rootDir" });
      continue;
    }
    try {
      if (f.content === null) {
        if (existsSync(abs)) {
          rmSync(abs);
          result.removed.push(f.path);
        }
      } else {
        mkdirSync(dirname(abs), { recursive: true });
        writeFileSync(abs, f.content, "utf8");
        result.restored.push(f.path);
      }
    } catch (err) {
      result.skipped.push({ path: f.path, reason: err.message });
    }
  }
  return result;
}
function deleteCheckpoint(rootDir, id) {
  const cpPath = snapshotPath(rootDir, id);
  let removed = false;
  if (existsSync(cpPath)) {
    try {
      rmSync(cpPath);
      removed = true;
    } catch {
      return false;
    }
  }
  const items = listCheckpoints(rootDir);
  const next = items.filter((m) => m.id !== id);
  if (next.length !== items.length) {
    writeIndex(rootDir, next);
    removed = true;
  }
  return removed;
}
function fmtAgo(ms) {
  const now = Date.now();
  const diff = Math.max(0, now - ms);
  const s = Math.floor(diff / 1e3);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

// src/code/plan-store.ts
import {
  existsSync as existsSync2,
  mkdirSync as mkdirSync2,
  readFileSync as readFileSync2,
  readdirSync as readdirSync2,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync as writeFileSync2
} from "fs";
import { dirname as dirname2, join as join2 } from "path";
function planStatePath(sessionName) {
  return join2(sessionsDir(), `${sanitizeName(sessionName)}.plan.json`);
}
function loadPlanState(sessionName) {
  const path = planStatePath(sessionName);
  if (!existsSync2(path)) return null;
  try {
    const raw = readFileSync2(path, "utf8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.version !== 1 && parsed.version !== 2) return null;
    if (!Array.isArray(parsed.steps)) return null;
    if (!Array.isArray(parsed.completedStepIds)) return null;
    if (typeof parsed.updatedAt !== "string") return null;
    const steps = [];
    for (const s of parsed.steps) {
      if (!s || typeof s !== "object") continue;
      const e = s;
      if (typeof e.id !== "string" || !e.id) continue;
      if (typeof e.title !== "string" || !e.title) continue;
      if (typeof e.action !== "string" || !e.action) continue;
      const step = { id: e.id, title: e.title, action: e.action };
      if (e.risk === "low" || e.risk === "med" || e.risk === "high") step.risk = e.risk;
      const targets = stringList(e.targets);
      if (targets) step.targets = targets;
      if (typeof e.acceptance === "string" && e.acceptance.trim()) {
        step.acceptance = e.acceptance.trim();
      }
      const verification = stringList(e.verification);
      if (verification) step.verification = verification;
      steps.push(step);
    }
    if (steps.length === 0) return null;
    const completedStepIds = parsed.completedStepIds.filter(
      (id) => typeof id === "string" && id.length > 0
    );
    const stepCompletions = sanitizeStepCompletions(parsed.stepCompletions);
    const out = {
      version: parsed.version,
      steps,
      completedStepIds,
      updatedAt: parsed.updatedAt
    };
    if (stepCompletions) out.stepCompletions = stepCompletions;
    if (typeof parsed.body === "string" && parsed.body) out.body = parsed.body;
    if (typeof parsed.summary === "string" && parsed.summary) out.summary = parsed.summary;
    return out;
  } catch {
    return null;
  }
}
function savePlanState(sessionName, steps, completedStepIds, extras) {
  const path = planStatePath(sessionName);
  try {
    mkdirSync2(dirname2(path), { recursive: true });
    const state = {
      version: 2,
      steps,
      completedStepIds: [...completedStepIds],
      updatedAt: (/* @__PURE__ */ new Date()).toISOString()
    };
    const stepCompletions = normalizeStepCompletionsForWrite(extras?.stepCompletions);
    if (stepCompletions) state.stepCompletions = stepCompletions;
    if (extras?.body) state.body = extras.body;
    if (extras?.summary) state.summary = extras.summary;
    writeFileSync2(path, `${JSON.stringify(state, null, 2)}
`, "utf8");
  } catch (err) {
    process.stderr.write(
      `\u25B8 plan-store: failed to save plan for "${sessionName}": ${err.message}
`
    );
  }
}
function clearPlanState(sessionName) {
  const path = planStatePath(sessionName);
  try {
    if (existsSync2(path)) unlinkSync(path);
  } catch {
  }
}
function archivePlanState(sessionName) {
  const active = planStatePath(sessionName);
  if (!existsSync2(active)) return null;
  const stamp = (/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-");
  const suffix = Math.random().toString(36).slice(2, 6);
  const archive = join2(
    sessionsDir(),
    `${sanitizeName(sessionName)}.plan.${stamp}-${suffix}.done.json`
  );
  try {
    renameSync(active, archive);
    return archive;
  } catch (err) {
    process.stderr.write(
      `\u25B8 plan-store: failed to archive plan for "${sessionName}": ${err.message}
`
    );
    return null;
  }
}
function listPlanArchives(sessionName) {
  const dir = sessionsDir();
  if (!existsSync2(dir)) return [];
  const prefix = `${sanitizeName(sessionName)}.plan.`;
  const suffix = ".done.json";
  let entries;
  try {
    entries = readdirSync2(dir);
  } catch {
    return [];
  }
  const summaries = [];
  for (const name of entries) {
    if (!name.startsWith(prefix) || !name.endsWith(suffix)) continue;
    const full = join2(dir, name);
    try {
      const raw = readFileSync2(full, "utf8");
      const parsed = JSON.parse(raw);
      if (parsed.version !== 1 && parsed.version !== 2) continue;
      if (!Array.isArray(parsed.steps) || parsed.steps.length === 0) continue;
      const steps = parsed.steps.filter(
        (s) => !!s && typeof s === "object" && typeof s.id === "string" && typeof s.title === "string" && typeof s.action === "string"
      );
      if (steps.length === 0) continue;
      const completedStepIds = Array.isArray(parsed.completedStepIds) ? parsed.completedStepIds.filter((id) => typeof id === "string" && !!id) : [];
      let completedAt = typeof parsed.updatedAt === "string" ? parsed.updatedAt : "";
      if (!completedAt || Number.isNaN(Date.parse(completedAt))) {
        try {
          completedAt = statSync(full).mtime.toISOString();
        } catch {
          completedAt = (/* @__PURE__ */ new Date(0)).toISOString();
        }
      }
      const entry = { path: full, completedAt, steps, completedStepIds };
      const stepCompletions = sanitizeStepCompletions(parsed.stepCompletions);
      if (stepCompletions) entry.stepCompletions = stepCompletions;
      if (typeof parsed.body === "string" && parsed.body) entry.body = parsed.body;
      if (typeof parsed.summary === "string" && parsed.summary) entry.summary = parsed.summary;
      summaries.push(entry);
    } catch {
    }
  }
  summaries.sort((a, b) => b.completedAt.localeCompare(a.completedAt));
  return summaries;
}
function isPlanComplete(state) {
  return state.completedStepIds.length >= state.steps.length;
}
function listAllPlanArchives() {
  const dir = sessionsDir();
  if (!existsSync2(dir)) return [];
  let entries;
  try {
    entries = readdirSync2(dir);
  } catch {
    return [];
  }
  const out = [];
  const suffix = ".done.json";
  const planMarker = ".plan.";
  for (const name of entries) {
    if (!name.endsWith(suffix)) continue;
    const planIdx = name.indexOf(planMarker);
    if (planIdx < 0) continue;
    const sessionName = name.slice(0, planIdx);
    if (!sessionName) continue;
    const full = join2(dir, name);
    try {
      const raw = readFileSync2(full, "utf8");
      const parsed = JSON.parse(raw);
      if (parsed.version !== 1 && parsed.version !== 2) continue;
      if (!Array.isArray(parsed.steps) || parsed.steps.length === 0) continue;
      const steps = parsed.steps.filter(
        (s) => !!s && typeof s === "object" && typeof s.id === "string" && typeof s.title === "string" && typeof s.action === "string"
      );
      if (steps.length === 0) continue;
      const completedStepIds = Array.isArray(parsed.completedStepIds) ? parsed.completedStepIds.filter((id) => typeof id === "string" && !!id) : [];
      let completedAt = typeof parsed.updatedAt === "string" ? parsed.updatedAt : "";
      if (!completedAt || Number.isNaN(Date.parse(completedAt))) {
        try {
          completedAt = statSync(full).mtime.toISOString();
        } catch {
          completedAt = (/* @__PURE__ */ new Date(0)).toISOString();
        }
      }
      const entry = {
        sessionName,
        path: full,
        completedAt,
        steps,
        completedStepIds
      };
      const stepCompletions = sanitizeStepCompletions(parsed.stepCompletions);
      if (stepCompletions) entry.stepCompletions = stepCompletions;
      if (typeof parsed.body === "string" && parsed.body) entry.body = parsed.body;
      if (typeof parsed.summary === "string" && parsed.summary) entry.summary = parsed.summary;
      out.push(entry);
    } catch {
    }
  }
  out.sort((a, b) => b.completedAt.localeCompare(a.completedAt));
  return out;
}
function stringList(raw) {
  if (!Array.isArray(raw)) return void 0;
  const out = raw.map((entry) => typeof entry === "string" ? entry.trim() : "").filter((entry) => entry.length > 0);
  return out.length > 0 ? out : void 0;
}
function normalizeStepCompletionsForWrite(raw) {
  if (!raw) return void 0;
  const entries = raw instanceof Map ? [...raw.entries()] : Object.entries(raw);
  const out = {};
  for (const [key, value] of entries) {
    const completion = sanitizeStepCompletion(value, key);
    if (completion) out[completion.stepId] = completion;
  }
  return Object.keys(out).length > 0 ? out : void 0;
}
function sanitizeStepCompletions(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return void 0;
  const out = {};
  for (const [key, value] of Object.entries(raw)) {
    const completion = sanitizeStepCompletion(value, key);
    if (completion) out[completion.stepId] = completion;
  }
  return Object.keys(out).length > 0 ? out : void 0;
}
function sanitizeStepCompletion(raw, fallbackStepId) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return void 0;
  const entry = raw;
  const stepId = typeof entry.stepId === "string" && entry.stepId.trim() ? entry.stepId.trim() : fallbackStepId?.trim();
  const result = typeof entry.result === "string" ? entry.result.trim() : "";
  if (!stepId || !result) return void 0;
  const completion = { kind: "step_completed", stepId, result };
  if (typeof entry.title === "string" && entry.title.trim()) completion.title = entry.title.trim();
  if (typeof entry.notes === "string" && entry.notes.trim()) completion.notes = entry.notes.trim();
  const evidence = sanitizeEvidenceList(entry.evidence);
  if (evidence) completion.evidence = evidence;
  return completion;
}
function sanitizeEvidenceList(raw) {
  if (!Array.isArray(raw)) return void 0;
  const out = [];
  for (const item of raw) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const entry = item;
    const kind = entry.kind;
    if (kind !== "verification" && kind !== "diff" && kind !== "checkpoint" && kind !== "manual") {
      continue;
    }
    const summary = typeof entry.summary === "string" ? entry.summary.trim() : "";
    if (!summary) continue;
    const evidence = { kind, summary };
    if (typeof entry.command === "string" && entry.command.trim()) {
      evidence.command = entry.command.trim();
    }
    const paths = stringList(entry.paths);
    if (paths) evidence.paths = paths;
    out.push(evidence);
  }
  return out.length > 0 ? out : void 0;
}
function relativeTime(updatedAt, now = Date.now()) {
  const t = Date.parse(updatedAt);
  if (Number.isNaN(t)) return updatedAt;
  const diffMs = Math.max(0, now - t);
  const sec = Math.floor(diffMs / 1e3);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return updatedAt.slice(0, 10);
}

// src/cli/ui/slash/commands.ts
var SLASH_GROUP_ORDER = [
  "setup",
  "info",
  "chat",
  "extend",
  "session",
  "code",
  "jobs",
  "advanced"
];
var SLASH_GROUP_RANK = new Map(
  SLASH_GROUP_ORDER.map((group, index) => [group, index])
);
function orderSlashCommandsByGroup(commands) {
  return commands.map((command, index) => ({ command, index })).sort((a, b) => {
    const groupDiff = SLASH_GROUP_RANK.get(a.command.group) - SLASH_GROUP_RANK.get(b.command.group);
    if (groupDiff !== 0) return groupDiff;
    return a.index - b.index;
  }).map((entry) => entry.command);
}
var SLASH_COMMANDS = [
  { cmd: "help", group: "chat", summary: "show the full command reference", aliases: ["?"] },
  {
    cmd: "new",
    group: "chat",
    summary: "start a fresh conversation (clear context + scrollback)",
    aliases: ["reset", "clear"]
  },
  { cmd: "retry", group: "chat", summary: "truncate & resend your last message (fresh sample)" },
  {
    cmd: "compact",
    group: "chat",
    summary: "fold older turns into a summary message (cache-safe). Auto-fires at 50% ctx; this is the manual trigger."
  },
  {
    cmd: "stop",
    group: "chat",
    summary: "abort the current model turn (typed alternative to Esc)"
  },
  {
    cmd: "btw",
    group: "chat",
    argsHint: "<question>",
    summary: "ask a quick side question \u2014 answered from a blank slate, never added to the conversation context"
  },
  {
    cmd: "model",
    group: "setup",
    argsHint: "<id>",
    summary: "switch DeepSeek model id. Bare opens picker.",
    argCompleter: "models"
  },
  {
    cmd: "effort",
    group: "setup",
    argsHint: "<low|medium|high|max>",
    summary: "reasoning_effort cap \u2014 high is the safe default (vLLM/Azure compatible); max is a DeepSeek extension.",
    argCompleter: ["low", "medium", "high", "max"]
  },
  {
    cmd: "language",
    group: "setup",
    argsHint: "<EN|zh-CN|de|ru>",
    summary: "switch the runtime language",
    argCompleter: ["EN", "zh-CN", "de", "ru"],
    aliases: ["lang"]
  },
  {
    cmd: "theme",
    group: "setup",
    argsHint: "[auto|dark|light|midnight|deep-blue|high-contrast]",
    summary: "show or persist the terminal theme preference. Bare opens picker.",
    argCompleter: ["auto", "dark", "light", "midnight", "deep-blue", "high-contrast"]
  },
  { cmd: "status", group: "info", summary: "current model, flags, context, session" },
  {
    cmd: "cost",
    group: "info",
    argsHint: "[text]",
    summary: "bare \u2192 last turn's spend (Usage card); with text \u2192 estimate cost of sending it next (worst-case + likely-cache)"
  },
  {
    cmd: "context",
    group: "info",
    summary: "show context-window breakdown (system / tools / log / input)"
  },
  {
    cmd: "stats",
    group: "info",
    summary: "cross-session cost dashboard (today / week / month / all-time \xB7 cache hit \xB7 vs Claude)"
  },
  {
    cmd: "doctor",
    group: "info",
    summary: "health check (api / config / api-reach / index / hooks / project)"
  },
  {
    cmd: "keys",
    group: "info",
    summary: "keyboard + mouse + copy/paste reference"
  },
  {
    cmd: "feedback",
    group: "info",
    summary: "open a GitHub issue with diagnostic info copied to clipboard"
  },
  {
    cmd: "about",
    group: "info",
    summary: "project info \u2014 version, website, repo, license"
  },
  { cmd: "sessions", group: "session", summary: "list saved sessions (current marked with \u25B8)" },
  {
    cmd: "title",
    group: "session",
    summary: "ask the model to rename this session from the conversation",
    aliases: ["retitle"]
  },
  { cmd: "mcp", group: "extend", summary: "list MCP servers + tools attached to this session" },
  {
    cmd: "resource",
    group: "extend",
    argsHint: "[uri]",
    summary: "browse + read MCP resources (no arg \u2192 list URIs; <uri> \u2192 fetch contents)",
    argCompleter: "mcp-resources"
  },
  {
    cmd: "prompt",
    group: "extend",
    argsHint: "[name]",
    summary: "browse + fetch MCP prompts (no arg \u2192 list names; <name> \u2192 render prompt)",
    argCompleter: "mcp-prompts"
  },
  {
    cmd: "memory",
    group: "extend",
    argsHint: "[list|show <name>|forget <name>|clear <scope> confirm]",
    summary: "show / manage pinned memory (REASONIX.md + ~/.reasonix/memory)"
  },
  {
    cmd: "skill",
    group: "extend",
    argsHint: "[list|paths|paths add <path>|paths remove <path|N>|show <name>|new <name>|<name> [args]]",
    summary: "list / run / scaffold skills (project + custom + global + builtin)",
    argCompleter: "skills"
  },
  {
    cmd: "qq",
    group: "extend",
    argsHint: "<connect|status|disconnect>",
    summary: "connect, inspect, or disconnect the QQ channel",
    argCompleter: ["connect", "status", "disconnect"]
  },
  {
    cmd: "init",
    group: "code",
    argsHint: "[force]",
    summary: "scan the project and synthesize a baseline REASONIX.md (model writes; review with /apply). `force` overwrites an existing file.",
    contextual: "code",
    argCompleter: ["force"]
  },
  {
    cmd: "apply",
    group: "code",
    argsHint: "[N|N,M|N-M]",
    summary: "commit pending edit blocks to disk (no arg \u2192 all; `1`, `1,3`, or `1-4` \u2192 that subset, rest stay pending)",
    contextual: "code"
  },
  {
    cmd: "discard",
    group: "code",
    argsHint: "[N|N,M|N-M]",
    summary: "drop pending edit blocks without writing (no arg \u2192 all; indices \u2192 that subset)",
    contextual: "code"
  },
  {
    cmd: "walk",
    group: "code",
    summary: "step through pending edits one block at a time (git-add-p style: y/n per block, a apply rest, A flip AUTO)",
    contextual: "code"
  },
  {
    cmd: "undo",
    group: "code",
    summary: "roll back the last applied edit batch",
    contextual: "code"
  },
  {
    cmd: "history",
    group: "code",
    summary: "list every edit batch this session (ids for /show, undone markers)",
    contextual: "code"
  },
  {
    cmd: "show",
    group: "code",
    argsHint: "[id]",
    summary: "dump a stored edit diff (omit id for newest non-undone)",
    contextual: "code"
  },
  {
    cmd: "commit",
    group: "code",
    argsHint: '"msg"',
    summary: "git add -A && git commit -m ...",
    contextual: "code"
  },
  {
    cmd: "mode",
    group: "code",
    argsHint: "[review|auto|yolo|plan]",
    summary: "edit-gate: review (queue) \xB7 auto (apply+undo) \xB7 yolo (apply+auto-shell) \xB7 plan (read-only). Shift+Tab cycles.",
    contextual: "code",
    argCompleter: ["review", "auto", "yolo", "plan"]
  },
  {
    cmd: "plan",
    group: "code",
    argsHint: "[on|off|strict]",
    summary: "toggle read-only plan mode / strict lifecycle rails",
    contextual: "code",
    argCompleter: ["on", "off", "strict"]
  },
  {
    cmd: "checkpoint",
    group: "code",
    argsHint: "[name|list|forget <id>]",
    summary: "snapshot every file the session has touched (Cursor-style internal store, not git). /checkpoint alone lists.",
    contextual: "code",
    argCompleter: ["list", "forget"]
  },
  {
    cmd: "restore",
    group: "code",
    argsHint: "<name|id>",
    summary: "roll back files to a named checkpoint (see /checkpoint list)",
    contextual: "code"
  },
  {
    cmd: "cwd",
    group: "code",
    argsHint: "[path]",
    summary: "switch the workspace root mid-session \u2014 re-points fs / shell / memory tools, reloads project hooks, refreshes the at-mention walker",
    contextual: "code",
    aliases: ["sandbox"],
    argCompleter: "path"
  },
  {
    cmd: "jobs",
    group: "jobs",
    summary: "list background jobs started by run_background",
    contextual: "code"
  },
  {
    cmd: "kill",
    group: "jobs",
    argsHint: "<id>",
    summary: "stop a background job by id (SIGTERM \u2192 SIGKILL after grace)",
    contextual: "code"
  },
  {
    cmd: "logs",
    group: "jobs",
    argsHint: "<id> [lines]",
    summary: "tail a background job's output (default last 80 lines)",
    contextual: "code"
  },
  {
    cmd: "budget",
    group: "advanced",
    argsHint: "[usd|off]",
    summary: "session USD cap \u2014 warns at 80%, refuses next turn at 100%. Off by default. /budget alone shows status",
    argCompleter: ["off", "1", "5", "10", "20", "50"]
  },
  {
    cmd: "search-engine",
    group: "advanced",
    argsHint: "<bing|searxng|metaso|tavily|perplexity|exa|brave|ollama> [<key>]",
    summary: "switch web search backend \u2014 bing (default, works from CN without proxy), searxng (self-hosted), metaso (free 100/d), tavily (free 1000/mo), perplexity (AI-native), exa (AI-native), brave (independent index, free 2000/mo), or ollama (Ollama cloud web search). Provider with no key prompts inline config.",
    argCompleter: ["bing", "searxng", "metaso", "tavily", "perplexity", "exa", "brave", "ollama"],
    aliases: ["se"]
  },
  {
    cmd: "hooks",
    group: "advanced",
    argsHint: "[reload]",
    summary: "list active hooks (settings.json under .reasonix/) \xB7 reload re-reads from disk"
  },
  {
    cmd: "permissions",
    group: "advanced",
    argsHint: "[list|add <prefix>|remove <prefix|N>|clear confirm]",
    summary: "show / edit shell allowlist (builtin read-only \xB7 per-project: ~/.reasonix/config.json)",
    argCompleter: ["list", "add", "remove", "clear"]
  },
  {
    cmd: "dashboard",
    group: "advanced",
    argsHint: "[stop]",
    summary: "launch the embedded web dashboard (127.0.0.1, token-gated)",
    argCompleter: ["stop"]
  },
  {
    cmd: "loop",
    group: "advanced",
    argsHint: "<5s..6h> <prompt>  \xB7  stop  \xB7  (no args = status)",
    summary: "auto-resubmit <prompt> every <interval> until you type something / Esc / /loop stop"
  },
  {
    cmd: "plans",
    group: "advanced",
    summary: "list this session's active + archived plans, newest first"
  },
  {
    cmd: "replay",
    group: "advanced",
    summary: "load an archived plan as a read-only Time Travel snapshot (default: newest)",
    argsHint: "[N]"
  },
  {
    cmd: "update",
    group: "advanced",
    summary: "show current vs latest version + the shell command to upgrade"
  },
  { cmd: "exit", group: "advanced", summary: "quit the TUI", aliases: ["quit", "q"] }
];
function suggestSlashCommands(prefix, codeMode = false, counts) {
  const p = prefix.toLowerCase();
  const matches = SLASH_COMMANDS.filter((c) => {
    if (p === "") return c.group !== "advanced";
    if (c.contextual === "code" && !codeMode) return false;
    if (c.cmd.startsWith(p)) return true;
    return c.aliases?.some((a) => a.startsWith(p)) ?? false;
  });
  if (p === "") return orderSlashCommandsByGroup(matches);
  if (!counts) return matches;
  const indexOf = new Map(matches.map((s, i) => [s.cmd, i]));
  return [...matches].sort((a, b) => {
    const diff = (counts[b.cmd] ?? 0) - (counts[a.cmd] ?? 0);
    if (diff !== 0) return diff;
    return (indexOf.get(a.cmd) ?? 0) - (indexOf.get(b.cmd) ?? 0);
  });
}
function countAdvancedCommands(codeMode) {
  return SLASH_COMMANDS.filter(
    (c) => c.group === "advanced" && (c.contextual !== "code" || codeMode)
  ).length;
}
var ALIAS_TO_CMD = (() => {
  const m = {};
  for (const spec of SLASH_COMMANDS) {
    if (!spec.aliases) continue;
    for (const a of spec.aliases) m[a] = spec.cmd;
  }
  return m;
})();
function resolveSlashAlias(name) {
  return ALIAS_TO_CMD[name] ?? name;
}
function detectSlashArgContext(input, codeMode = false) {
  const m = /^\/(\S+) ([\s\S]*)$/.exec(input);
  if (!m) return null;
  const cmdName = resolveSlashAlias(m[1].toLowerCase());
  const tail = m[2] ?? "";
  const spec = SLASH_COMMANDS.find(
    (s) => s.cmd === cmdName && (s.contextual !== "code" || codeMode)
  );
  if (!spec) return null;
  const hasInternalSpace = /\s/.test(tail);
  const partialOffset = input.length - tail.length;
  if (hasInternalSpace) {
    return { spec, partial: tail, partialOffset, kind: "hint" };
  }
  return {
    spec,
    partial: tail,
    partialOffset,
    kind: spec.argCompleter ? "picker" : "hint"
  };
}
function parseSlash(text) {
  if (!text.startsWith("/")) return null;
  if (text.startsWith("//")) return null;
  const parts = text.slice(1).trim().split(/\s+/);
  const cmd = parts[0]?.toLowerCase() ?? "";
  if (!cmd) return null;
  return { cmd, args: parts.slice(1) };
}

export {
  listCheckpoints,
  loadCheckpoint,
  createCheckpoint,
  findCheckpoint,
  restoreCheckpoint,
  deleteCheckpoint,
  fmtAgo,
  loadPlanState,
  savePlanState,
  clearPlanState,
  archivePlanState,
  listPlanArchives,
  isPlanComplete,
  listAllPlanArchives,
  relativeTime,
  SLASH_GROUP_ORDER,
  orderSlashCommandsByGroup,
  SLASH_COMMANDS,
  suggestSlashCommands,
  countAdvancedCommands,
  resolveSlashAlias,
  detectSlashArgContext,
  parseSlash
};
//# sourceMappingURL=chunk-4EHRIP5U.js.map