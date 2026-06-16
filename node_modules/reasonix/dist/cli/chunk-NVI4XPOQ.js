#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  t
} from "./chunk-U7G72DHQ.js";
import {
  projectHooksTrusted
} from "./chunk-GCNBIWK7.js";

// src/hooks.ts
import { spawn } from "child_process";
import { existsSync, readFileSync } from "fs";
import { homedir } from "os";
import { join } from "path";
var HOOK_EVENTS = [
  "PreToolUse",
  "PostToolUse",
  "UserPromptSubmit",
  "Stop"
];
var BLOCKING_EVENTS = /* @__PURE__ */ new Set(["PreToolUse", "UserPromptSubmit"]);
var DEFAULT_TIMEOUTS_MS = {
  PreToolUse: 5e3,
  UserPromptSubmit: 5e3,
  PostToolUse: 3e4,
  Stop: 3e4
};
var HOOK_SETTINGS_FILENAME = "settings.json";
var HOOK_SETTINGS_DIRNAME = ".reasonix";
function globalSettingsPath(homeDirOverride) {
  return join(homeDirOverride ?? homedir(), HOOK_SETTINGS_DIRNAME, HOOK_SETTINGS_FILENAME);
}
function projectSettingsPath(projectRoot) {
  return join(projectRoot, HOOK_SETTINGS_DIRNAME, HOOK_SETTINGS_FILENAME);
}
function readSettingsFile(path) {
  if (!existsSync(path)) return null;
  try {
    const raw = readFileSync(path, "utf8");
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed;
  } catch {
  }
  return null;
}
function loadHooks(opts = {}) {
  const out = [];
  if (opts.projectRoot && (opts.trustProjectHooks === true || projectHooksTrusted(opts.projectRoot, opts.configPath))) {
    const projPath = projectSettingsPath(opts.projectRoot);
    const settings2 = readSettingsFile(projPath);
    if (settings2) appendResolved(out, settings2, "project", projPath);
  }
  const globalPath = globalSettingsPath(opts.homeDir);
  const settings = readSettingsFile(globalPath);
  if (settings) appendResolved(out, settings, "global", globalPath);
  return out;
}
function appendResolved(out, settings, scope, source) {
  if (!settings.hooks) return;
  for (const event of HOOK_EVENTS) {
    const list = settings.hooks[event];
    if (!Array.isArray(list)) continue;
    for (const cfg of list) {
      if (!cfg || typeof cfg.command !== "string" || cfg.command.trim() === "") continue;
      out.push({ ...cfg, event, scope, source });
    }
  }
}
function matchesTool(hook, toolName) {
  if (hook.event !== "PreToolUse" && hook.event !== "PostToolUse") return true;
  const m = hook.match;
  if (!m || m === "*") return true;
  try {
    const re = new RegExp(`^(?:${m})$`);
    return re.test(toolName);
  } catch {
    return false;
  }
}
var HOOK_OUTPUT_CAP_BYTES = 256 * 1024;
function defaultSpawner(input) {
  return new Promise((resolve) => {
    const child = spawn(input.command, {
      cwd: input.cwd,
      shell: true,
      stdio: ["pipe", "pipe", "pipe"]
    });
    const stdoutChunks = [];
    const stderrChunks = [];
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let truncated = false;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      setTimeout(() => {
        try {
          child.kill("SIGKILL");
        } catch {
        }
      }, 500);
    }, input.timeoutMs);
    const onChunk = (kind, chunk) => {
      const target = kind === "stdout" ? stdoutChunks : stderrChunks;
      const seen = kind === "stdout" ? stdoutBytes : stderrBytes;
      if (seen >= HOOK_OUTPUT_CAP_BYTES) {
        truncated = true;
        return;
      }
      const remaining = HOOK_OUTPUT_CAP_BYTES - seen;
      if (chunk.length > remaining) {
        target.push(chunk.subarray(0, remaining));
        if (kind === "stdout") stdoutBytes = HOOK_OUTPUT_CAP_BYTES;
        else stderrBytes = HOOK_OUTPUT_CAP_BYTES;
        truncated = true;
      } else {
        target.push(chunk);
        if (kind === "stdout") stdoutBytes += chunk.length;
        else stderrBytes += chunk.length;
      }
    };
    child.stdout.on("data", (chunk) => onChunk("stdout", chunk));
    child.stderr.on("data", (chunk) => onChunk("stderr", chunk));
    child.once("error", (err) => {
      clearTimeout(timer);
      resolve({
        exitCode: null,
        stdout: Buffer.concat(stdoutChunks).toString("utf8"),
        stderr: Buffer.concat(stderrChunks).toString("utf8"),
        timedOut: false,
        spawnError: err,
        truncated: truncated || void 0
      });
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      resolve({
        exitCode: code,
        stdout: Buffer.concat(stdoutChunks).toString("utf8").trim(),
        stderr: Buffer.concat(stderrChunks).toString("utf8").trim(),
        timedOut,
        truncated: truncated || void 0
      });
    });
    try {
      child.stdin.write(input.stdin);
      child.stdin.end();
    } catch {
    }
  });
}
function formatHookOutcomeMessage(outcome) {
  if (outcome.decision === "pass") return "";
  const detail = (outcome.stderr || outcome.stdout || "").trim();
  const tag = `${outcome.hook.scope}/${outcome.hook.event}`;
  const cmd = outcome.hook.command.length > 60 ? `${outcome.hook.command.slice(0, 60)}\u2026` : outcome.hook.command;
  const truncTag = outcome.truncated ? t("hooks.truncated") : "";
  const decision = t(`hooks.decision${capitalize(outcome.decision)}`);
  return detail ? t("hooks.headWithDetail", { tag, cmd, decision, truncTag, detail }) : t("hooks.head", { tag, cmd, decision, truncTag });
}
function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
function decideOutcome(event, raw) {
  if (raw.spawnError) return "error";
  if (raw.timedOut) return BLOCKING_EVENTS.has(event) ? "block" : "warn";
  if (raw.exitCode === 0) return "pass";
  if (raw.exitCode === 2 && BLOCKING_EVENTS.has(event)) return "block";
  return "warn";
}
async function runHooks(opts) {
  const spawner = opts.spawner ?? defaultSpawner;
  const event = opts.payload.event;
  const toolName = opts.payload.toolName ?? "";
  const matching = opts.hooks.filter((h) => h.event === event && matchesTool(h, toolName));
  const outcomes = [];
  let blocked = false;
  const stdin = `${JSON.stringify(opts.payload)}
`;
  for (const hook of matching) {
    const start = Date.now();
    const timeoutMs = hook.timeout ?? DEFAULT_TIMEOUTS_MS[event];
    const cwd = hook.cwd ?? opts.payload.cwd;
    const raw = await spawner({ command: hook.command, cwd, stdin, timeoutMs });
    const decision = decideOutcome(event, raw);
    outcomes.push({
      hook,
      decision,
      exitCode: raw.exitCode,
      stdout: raw.stdout,
      stderr: raw.stderr || (raw.spawnError ? raw.spawnError.message : "") || (raw.timedOut ? `hook timed out after ${timeoutMs}ms` : ""),
      durationMs: Date.now() - start,
      truncated: raw.truncated
    });
    if (decision === "block") {
      blocked = true;
      break;
    }
  }
  return { event, outcomes, blocked };
}

export {
  HOOK_EVENTS,
  globalSettingsPath,
  projectSettingsPath,
  loadHooks,
  formatHookOutcomeMessage,
  runHooks
};
//# sourceMappingURL=chunk-NVI4XPOQ.js.map