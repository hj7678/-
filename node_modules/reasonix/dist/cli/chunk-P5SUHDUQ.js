#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  atomicWriteSync
} from "./chunk-GCNBIWK7.js";

// src/memory/session.ts
import { execFileSync } from "child_process";
import {
  appendFileSync,
  chmodSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync
} from "fs";
import { homedir } from "os";
import { dirname, join, posix as posixPath, win32 as win32Path } from "path";
var SESSION_SIDECAR_EXTS = [
  ".events.jsonl",
  ".meta.json",
  ".pending.json",
  ".plan.json",
  ".jsonl.bak"
];
function detectGitBranch(cwd) {
  try {
    const out = execFileSync("git", ["branch", "--show-current"], {
      cwd,
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 800,
      encoding: "utf8"
    }).trim();
    return out || void 0;
  } catch {
    return void 0;
  }
}
function sessionsDir() {
  return join(homedir(), ".reasonix", "sessions");
}
function sessionPath(name) {
  return join(sessionsDir(), `${sanitizeName(name)}.jsonl`);
}
function sanitizeName(name) {
  const cleaned = name.replace(/[^\w\-\u4e00-\u9fa5]/g, "_").slice(0, 64);
  return cleaned || "default";
}
function timestampSuffix() {
  return (/* @__PURE__ */ new Date()).toISOString().replace(/[^\d]/g, "").slice(0, 12);
}
function freshSessionName(currentName) {
  const base = currentName ? currentName.replace(/-\d{12,14}$/, "") : "default";
  const stamp = (/* @__PURE__ */ new Date()).toISOString().replace(/[^\d]/g, "").slice(0, 14);
  return `${base || "default"}-${stamp}`;
}
function findSessionsByPrefix(prefix) {
  const dir = sessionsDir();
  if (!existsSync(dir)) return [];
  try {
    const files = readdirSync(dir).filter((f) => f.endsWith(".jsonl") && !f.endsWith(".events.jsonl") && f.startsWith(prefix)).sort().reverse();
    return files.map((f) => f.replace(/\.jsonl$/, ""));
  } catch {
    return [];
  }
}
function resolveSession(sessionName, forceNew, forceResume) {
  let resolved = sessionName;
  let preview;
  if (sessionName && forceNew) {
    resolved = `${sessionName}-${timestampSuffix()}`;
  } else if (sessionName && !forceResume) {
    let sessionToCheck = sessionName;
    const prefixed = findSessionsByPrefix(`${sessionName}-`);
    if (prefixed.length > 0) {
      sessionToCheck = prefixed[0];
    }
    const prior = loadSessionMessages(sessionToCheck);
    if (prior.length > 0) {
      resolved = sessionToCheck;
      const p = sessionPath(sessionToCheck);
      const mtime = existsSync(p) ? statSync(p).mtime : /* @__PURE__ */ new Date();
      preview = { messageCount: prior.length, lastActive: mtime };
    }
  } else if (sessionName && forceResume) {
    const prefixed = findSessionsByPrefix(`${sessionName}-`);
    if (prefixed.length > 0) {
      resolved = prefixed[0];
    }
  }
  return { resolved, preview };
}
function loadSessionMessages(name) {
  const path = sessionPath(name);
  if (!existsSync(path)) return [];
  const live = readSessionMessages(path);
  if (live && (live.messages.length > 0 || !live.hadContent)) return live.messages;
  const backup = readSessionMessages(sessionBackupPath(path));
  return backup?.messages ?? live?.messages ?? [];
}
function readSessionMessages(path) {
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    return null;
  }
  const out = [];
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const msg = JSON.parse(trimmed);
      if (msg && typeof msg === "object" && "role" in msg) out.push(msg);
    } catch {
    }
  }
  return { messages: out, hadContent: raw.trim().length > 0 };
}
function appendSessionMessage(name, message) {
  const path = sessionPath(name);
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${JSON.stringify(message)}
`, "utf8");
  try {
    chmodSync(path, 384);
  } catch {
  }
}
function listSessions(opts) {
  const dir = sessionsDir();
  if (!existsSync(dir)) return [];
  const want = opts?.workspaceFilter ? normalizeWorkspace(opts.workspaceFilter) : null;
  const legacyPrefix = want && opts?.includeLegacyWorkspaceMatches ? legacySessionPrefixForWorkspace(opts.workspaceFilter) : null;
  try {
    const files = readdirSync(dir).filter(
      (f) => f.endsWith(".jsonl") && !f.endsWith(".events.jsonl")
    );
    return files.flatMap((file) => {
      const path = join(dir, file);
      const name = file.replace(/\.jsonl$/, "");
      const meta = loadSessionMeta(name);
      let workspaceStatus;
      if (want !== null) {
        if (typeof meta.workspace === "string") {
          if (normalizeWorkspace(meta.workspace) !== want) return [];
          workspaceStatus = "matched";
        } else if (legacyPrefix && name.startsWith(legacyPrefix)) {
          workspaceStatus = "legacy_missing_meta";
        } else {
          return [];
        }
      }
      const stat = statSync(path);
      const messageCount = countLines(path);
      return [
        { name, path, size: stat.size, messageCount, mtime: stat.mtime, meta, workspaceStatus }
      ];
    }).sort((a, b) => b.mtime.getTime() - a.mtime.getTime());
  } catch {
    return [];
  }
}
function normalizeWorkspace(p, platform = process.platform) {
  if (typeof p !== "string" || p.length === 0) return "";
  if (platform === "win32") {
    const resolved = win32Path.resolve(p);
    return resolved.replace(/\\/g, "/").replace(/^([A-Z]):/i, (_, d) => `${d.toLowerCase()}:`);
  }
  return posixPath.resolve(p);
}
function listSessionsForWorkspace(workspace) {
  return listSessions({ workspaceFilter: workspace, includeLegacyWorkspaceMatches: true });
}
function legacySessionPrefixForWorkspace(workspace) {
  const normalized = normalizeWorkspace(workspace);
  const base = process.platform === "win32" ? win32Path.basename(normalized) : posixPath.basename(normalized);
  return `${sanitizeName(`code-${base}`)}-`;
}
function patchSessionWorkspaceIfMissing(name, workspace) {
  const meta = loadSessionMeta(name);
  if (typeof meta.workspace === "string") return false;
  const prefix = legacySessionPrefixForWorkspace(workspace);
  if (!sanitizeName(name).startsWith(prefix)) return false;
  patchSessionMeta(name, { workspace });
  return true;
}
function metaPath(name) {
  return join(sessionsDir(), `${sanitizeName(name)}.meta.json`);
}
function loadSessionMeta(name) {
  const p = metaPath(name);
  if (!existsSync(p)) return {};
  try {
    const raw = JSON.parse(readFileSync(p, "utf8"));
    return raw && typeof raw === "object" ? raw : {};
  } catch {
    return {};
  }
}
function patchSessionMeta(name, patch) {
  const cur = loadSessionMeta(name);
  const next = { ...cur, ...patch };
  const p = metaPath(name);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(next), "utf8");
  try {
    chmodSync(p, 384);
  } catch {
  }
  return next;
}
function renameSession(oldName, newName) {
  const safeOld = sanitizeName(oldName);
  const safeNew = sanitizeName(newName);
  if (safeOld === safeNew) return false;
  const oldJsonl = sessionPath(oldName);
  const newJsonl = sessionPath(newName);
  if (!existsSync(oldJsonl) || existsSync(newJsonl)) return false;
  renameSync(oldJsonl, newJsonl);
  for (const ext of SESSION_SIDECAR_EXTS) {
    const oldP = oldJsonl.replace(/\.jsonl$/, ext);
    const newP = newJsonl.replace(/\.jsonl$/, ext);
    if (existsSync(oldP)) {
      try {
        renameSync(oldP, newP);
      } catch {
      }
    }
  }
  return true;
}
function pruneStaleSessions(daysOld = 90) {
  const cutoff = Date.now() - daysOld * 24 * 60 * 60 * 1e3;
  const deleted = [];
  for (const s of listSessions()) {
    if (s.mtime.getTime() < cutoff) {
      if (deleteSession(s.name)) deleted.push(s.name);
    }
  }
  return deleted;
}
function deleteSession(name) {
  const path = sessionPath(name);
  try {
    unlinkSync(path);
    for (const ext of SESSION_SIDECAR_EXTS) {
      const sidecar = path.replace(/\.jsonl$/, ext);
      try {
        unlinkSync(sidecar);
      } catch {
      }
    }
    return true;
  } catch {
    return false;
  }
}
function rewriteSession(name, messages) {
  const path = sessionPath(name);
  mkdirSync(dirname(path), { recursive: true });
  const body = messages.map((m) => JSON.stringify(m)).join("\n");
  const tmp = `${path}.${process.pid}.${Date.now()}.${Math.random().toString(36).slice(2)}.tmp`;
  if (existsSync(path) && statSync(path).size > 0) {
    const backup = sessionBackupPath(path);
    copyFileSync(path, backup);
    chmodPrivate(backup);
  }
  atomicWriteSync(path, body ? `${body}
` : "", tmp);
}
function archiveSession(name) {
  const path = sessionPath(name);
  if (!existsSync(path)) return null;
  try {
    if (statSync(path).size === 0) return null;
  } catch {
    return null;
  }
  for (let attempt = 0; attempt < 5; attempt++) {
    const target = `${name}__archive_${timestampSuffix()}${attempt > 0 ? `_${attempt}` : ""}`;
    if (renameSession(name, target)) return target;
  }
  return null;
}
function countLines(path) {
  try {
    const buf = readFileSync(path);
    let count = 0;
    for (let i = 0; i < buf.length; i++) {
      if (buf[i] === 10) count++;
    }
    if (buf.length > 0 && buf[buf.length - 1] !== 10) count++;
    return count;
  } catch {
    return 0;
  }
}
function sessionBackupPath(path) {
  return `${path}.bak`;
}
function chmodPrivate(path) {
  try {
    chmodSync(path, 384);
  } catch {
  }
}

export {
  detectGitBranch,
  sessionsDir,
  sessionPath,
  sanitizeName,
  timestampSuffix,
  freshSessionName,
  resolveSession,
  loadSessionMessages,
  appendSessionMessage,
  listSessions,
  normalizeWorkspace,
  listSessionsForWorkspace,
  patchSessionWorkspaceIfMissing,
  loadSessionMeta,
  patchSessionMeta,
  renameSession,
  pruneStaleSessions,
  deleteSession,
  rewriteSession,
  archiveSession
};
//# sourceMappingURL=chunk-P5SUHDUQ.js.map