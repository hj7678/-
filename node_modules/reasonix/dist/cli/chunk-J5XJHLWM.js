#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }

// src/adapters/event-source-jsonl.ts
import { existsSync, readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
var DAY_MS = 864e5;
function recentEventFiles(dir, now, cap = 8, staleDays = 30) {
  if (!existsSync(dir)) return [];
  let names;
  try {
    names = readdirSync(dir);
  } catch {
    return [];
  }
  const cutoff = now - staleDays * DAY_MS;
  const candidates = [];
  for (const name of names) {
    if (!name.endsWith(".events.jsonl")) continue;
    const path = join(dir, name);
    let mtime;
    try {
      mtime = statSync(path).mtimeMs;
    } catch {
      continue;
    }
    if (mtime < cutoff) continue;
    candidates.push({ path, mtime });
  }
  candidates.sort((a, b) => b.mtime - a.mtime);
  return candidates.slice(0, cap).map((c) => c.path);
}
function readEventLogFile(path) {
  if (!existsSync(path)) return [];
  const raw = readFileSync(path, "utf8");
  const out = [];
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const ev = JSON.parse(trimmed);
      if (ev && typeof ev === "object" && typeof ev.type === "string") {
        out.push(ev);
      }
    } catch {
    }
  }
  return out;
}

export {
  recentEventFiles,
  readEventLogFile
};
//# sourceMappingURL=chunk-J5XJHLWM.js.map