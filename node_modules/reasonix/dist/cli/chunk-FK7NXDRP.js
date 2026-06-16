#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  cacheSavingsUsd,
  claudeEquivalentCost,
  costUsd
} from "./chunk-V4AXMN4X.js";

// src/telemetry/usage.ts
import {
  appendFileSync,
  closeSync,
  existsSync,
  fstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync
} from "fs";
import { homedir } from "os";
import { dirname, join } from "path";
function defaultUsageLogPath(homeDirOverride) {
  return join(homeDirOverride ?? homedir(), ".reasonix", "usage.jsonl");
}
var USAGE_COMPACTION_THRESHOLD_BYTES = 5 * 1024 * 1024;
var USAGE_RETENTION_DAYS = 365;
function compactUsageLogIfLarge(path, now) {
  let raw;
  try {
    const fd = openSync(path, "r");
    try {
      const stat = fstatSync(fd);
      if (stat.size < USAGE_COMPACTION_THRESHOLD_BYTES) return;
      const buf = Buffer.alloc(stat.size);
      let read = 0;
      while (read < stat.size) {
        const n = readSync(fd, buf, read, stat.size - read, read);
        if (n <= 0) break;
        read += n;
      }
      raw = buf.toString("utf8", 0, read);
    } finally {
      closeSync(fd);
    }
  } catch {
    return;
  }
  const cutoff = now - USAGE_RETENTION_DAYS * 24 * 60 * 60 * 1e3;
  const lines = raw.split(/\r?\n/);
  const kept = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const rec = JSON.parse(line);
      if (isValidRecord(rec) && rec.ts >= cutoff) kept.push(line);
    } catch {
    }
  }
  if (kept.length === lines.filter((l) => l.trim()).length) return;
  const tmp = `${path}.compacting`;
  try {
    writeFileSync(tmp, kept.length > 0 ? `${kept.join("\n")}
` : "", "utf8");
    renameSync(tmp, path);
  } catch {
    try {
      unlinkSync(tmp);
    } catch {
    }
  }
}
function appendUsage(input) {
  const record = {
    ts: input.now ?? Date.now(),
    session: input.session,
    model: input.model,
    promptTokens: input.usage.promptTokens,
    completionTokens: input.usage.completionTokens,
    cacheHitTokens: input.usage.promptCacheHitTokens,
    cacheMissTokens: input.usage.promptCacheMissTokens,
    costUsd: costUsd(input.model, input.usage),
    claudeEquivUsd: claudeEquivalentCost(input.usage)
  };
  if (input.kind === "subagent") record.kind = "subagent";
  if (input.subagent) record.subagent = input.subagent;
  const path = input.path ?? defaultUsageLogPath();
  try {
    mkdirSync(dirname(path), { recursive: true });
    appendFileSync(path, `${JSON.stringify(record)}
`, "utf8");
    compactUsageLogIfLarge(path, record.ts);
  } catch {
  }
  return record;
}
function readUsageLog(path = defaultUsageLogPath()) {
  if (!existsSync(path)) return [];
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    return [];
  }
  const out = [];
  for (const line of raw.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      const rec = JSON.parse(line);
      if (isValidRecord(rec)) out.push(rec);
    } catch {
    }
  }
  return out;
}
function isValidRecord(rec) {
  if (!rec || typeof rec !== "object") return false;
  const r = rec;
  return typeof r.ts === "number" && typeof r.model === "string" && typeof r.promptTokens === "number" && typeof r.completionTokens === "number" && typeof r.cacheHitTokens === "number" && typeof r.cacheMissTokens === "number" && typeof r.costUsd === "number" && typeof r.claudeEquivUsd === "number";
}
function bucketCacheHitRatio(b) {
  const denom = b.cacheHitTokens + b.cacheMissTokens;
  return denom > 0 ? b.cacheHitTokens / denom : 0;
}
function bucketSavingsFraction(b) {
  return b.claudeEquivUsd > 0 ? 1 - b.costUsd / b.claudeEquivUsd : 0;
}
function emptyBucket(label, since) {
  return {
    label,
    since,
    turns: 0,
    promptTokens: 0,
    completionTokens: 0,
    cacheHitTokens: 0,
    cacheMissTokens: 0,
    costUsd: 0,
    claudeEquivUsd: 0,
    cacheSavingsUsd: 0
  };
}
function addToBucket(b, r) {
  b.turns += 1;
  b.promptTokens += r.promptTokens;
  b.completionTokens += r.completionTokens;
  b.cacheHitTokens += r.cacheHitTokens;
  b.cacheMissTokens += r.cacheMissTokens;
  b.costUsd += r.costUsd;
  b.claudeEquivUsd += r.claudeEquivUsd;
  b.cacheSavingsUsd += cacheSavingsUsd(r.model, r.cacheHitTokens);
}
function aggregateUsage(records, opts = {}) {
  const now = opts.now ?? Date.now();
  const day = 24 * 60 * 60 * 1e3;
  const today = emptyBucket("today", now - day);
  const week = emptyBucket("week", now - 7 * day);
  const month = emptyBucket("month", now - 30 * day);
  const all = emptyBucket("all-time", 0);
  const modelCounts = /* @__PURE__ */ new Map();
  const sessionCounts = /* @__PURE__ */ new Map();
  let firstSeen = null;
  let lastSeen = null;
  const skillCounts = /* @__PURE__ */ new Map();
  let subagentTotal = 0;
  let subagentCost = 0;
  let subagentDuration = 0;
  for (const r of records) {
    addToBucket(all, r);
    if (r.ts >= today.since) addToBucket(today, r);
    if (r.ts >= week.since) addToBucket(week, r);
    if (r.ts >= month.since) addToBucket(month, r);
    modelCounts.set(r.model, (modelCounts.get(r.model) ?? 0) + 1);
    const sessKey = r.session ?? "(ephemeral)";
    sessionCounts.set(sessKey, (sessionCounts.get(sessKey) ?? 0) + 1);
    if (firstSeen === null || r.ts < firstSeen) firstSeen = r.ts;
    if (lastSeen === null || r.ts > lastSeen) lastSeen = r.ts;
    if (r.kind === "subagent") {
      subagentTotal += 1;
      subagentCost += r.costUsd;
      const dur = r.subagent?.durationMs ?? 0;
      subagentDuration += dur;
      const key = r.subagent?.skillName?.trim() || "(adhoc)";
      const prev = skillCounts.get(key) ?? { count: 0, costUsd: 0, durationMs: 0 };
      prev.count += 1;
      prev.costUsd += r.costUsd;
      prev.durationMs += dur;
      skillCounts.set(key, prev);
    }
  }
  const byModel = Array.from(modelCounts.entries()).map(([model, turns]) => ({ model, turns })).sort((a, b) => b.turns - a.turns);
  const bySession = Array.from(sessionCounts.entries()).map(([session, turns]) => ({ session, turns })).sort((a, b) => b.turns - a.turns);
  const subagents = subagentTotal > 0 ? {
    total: subagentTotal,
    costUsd: subagentCost,
    totalDurationMs: subagentDuration,
    bySkill: Array.from(skillCounts.entries()).map(([skillName, v]) => ({ skillName, ...v })).sort((a, b) => b.count - a.count)
  } : void 0;
  return {
    buckets: [today, week, month, all],
    byModel,
    bySession,
    firstSeen,
    lastSeen,
    subagents
  };
}
function formatLogSize(path = defaultUsageLogPath()) {
  if (!existsSync(path)) return "";
  try {
    const s = statSync(path);
    const bytes = s.size;
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  } catch {
    return "";
  }
}

export {
  defaultUsageLogPath,
  appendUsage,
  readUsageLog,
  bucketCacheHitRatio,
  bucketSavingsFraction,
  aggregateUsage,
  formatLogSize
};
//# sourceMappingURL=chunk-FK7NXDRP.js.map