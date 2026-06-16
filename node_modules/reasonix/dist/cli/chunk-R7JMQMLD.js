#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  claudeEquivalentCost,
  costUsd,
  inputCostUsd,
  outputCostUsd
} from "./chunk-V4AXMN4X.js";
import {
  Usage
} from "./chunk-QSKDP3OS.js";

// src/transcript/log.ts
import { createWriteStream, readFileSync } from "fs";
function recordFromLoopEvent(ev, extra) {
  const rec = {
    ts: (/* @__PURE__ */ new Date()).toISOString(),
    turn: ev.turn,
    role: ev.role,
    content: ev.content
  };
  if (ev.toolName !== void 0) rec.tool = ev.toolName;
  if (ev.toolArgs !== void 0) rec.args = ev.toolArgs;
  if (ev.error !== void 0) rec.error = ev.error;
  if (ev.errorDetail !== void 0) rec.errorDetail = ev.errorDetail;
  if (ev.stats) {
    rec.usage = {
      prompt_tokens: ev.stats.usage.promptTokens,
      completion_tokens: ev.stats.usage.completionTokens,
      total_tokens: ev.stats.usage.totalTokens,
      prompt_cache_hit_tokens: ev.stats.usage.promptCacheHitTokens,
      prompt_cache_miss_tokens: ev.stats.usage.promptCacheMissTokens
    };
    rec.cost = ev.stats.cost;
    rec.model = ev.stats.model;
    rec.prefixHash = extra.prefixHash;
  } else if (ev.role === "assistant_final") {
    rec.model = extra.model;
    rec.prefixHash = extra.prefixHash;
  }
  return rec;
}
function writeRecord(stream, record) {
  stream.write(`${JSON.stringify(record)}
`);
}
function writeMeta(stream, meta) {
  const line = { role: "_meta", meta };
  stream.write(`${JSON.stringify(line)}
`);
}
function openTranscriptFile(path, meta) {
  const stream = createWriteStream(path, { flags: "a" });
  writeMeta(stream, meta);
  return stream;
}
function readTranscript(path) {
  const raw = readFileSync(path, "utf8");
  return parseTranscript(raw);
}
function parseTranscript(raw) {
  const out = { meta: null, records: [] };
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let obj;
    try {
      obj = JSON.parse(trimmed);
    } catch {
      continue;
    }
    if (!obj || typeof obj !== "object") continue;
    const rec = obj;
    if (rec.role === "_meta" && rec.meta && typeof rec.meta === "object") {
      out.meta = rec.meta;
      continue;
    }
    if (typeof rec.ts === "string" && typeof rec.turn === "number" && typeof rec.role === "string" && typeof rec.content === "string") {
      out.records.push(rec);
    }
  }
  return out;
}

// src/transcript/replay.ts
function groupRecordsByTurn(records) {
  const byTurn = /* @__PURE__ */ new Map();
  for (const rec of records) {
    const list = byTurn.get(rec.turn);
    if (list) list.push(rec);
    else byTurn.set(rec.turn, [rec]);
  }
  return [...byTurn.entries()].sort(([a], [b]) => a - b).map(([turn, records2]) => ({ turn, records: records2 }));
}
function computeCumulativeStats(pages, upToIdx) {
  if (upToIdx < 0) return computeReplayStats([]);
  const flat = [];
  for (let i = 0; i <= upToIdx && i < pages.length; i++) {
    const records = pages[i]?.records;
    if (records) flat.push(...records);
  }
  return computeReplayStats(flat);
}
function replayFromFile(path) {
  const parsed = readTranscript(path);
  return { parsed, stats: computeReplayStats(parsed.records) };
}
function computeReplayStats(records) {
  const turns = [];
  const models = /* @__PURE__ */ new Set();
  const prefixHashes = /* @__PURE__ */ new Set();
  let userTurns = 0;
  let toolCalls = 0;
  for (const rec of records) {
    if (rec.role === "user") userTurns++;
    else if (rec.role === "tool") toolCalls++;
    else if (rec.role === "assistant_final") {
      if (rec.model) models.add(rec.model);
      if (rec.prefixHash) prefixHashes.add(rec.prefixHash);
      if (rec.usage && rec.model) {
        const u = new Usage(
          rec.usage.prompt_tokens ?? 0,
          rec.usage.completion_tokens ?? 0,
          rec.usage.total_tokens ?? 0,
          rec.usage.prompt_cache_hit_tokens ?? 0,
          rec.usage.prompt_cache_miss_tokens ?? 0
        );
        turns.push({
          turn: rec.turn,
          model: rec.model,
          usage: u,
          // `rec.cost` wins when present — honors whatever the writer computed
          // even if pricing tables have since changed. Only recompute when
          // the transcript didn't record it (old format).
          cost: rec.cost ?? costUsd(rec.model, u),
          cacheHitRatio: u.cacheHitRatio
        });
      }
    }
  }
  return {
    perTurn: turns,
    models: [...models],
    prefixHashes: [...prefixHashes],
    userTurns,
    toolCalls,
    ...summarizeTurns(turns)
  };
}
function summarizeTurns(turns) {
  const totalCost = turns.reduce((s, t) => s + t.cost, 0);
  const totalInput = turns.reduce((s, t) => s + inputCostUsd(t.model, t.usage), 0);
  const totalOutput = turns.reduce((s, t) => s + outputCostUsd(t.model, t.usage), 0);
  const totalClaude = turns.reduce((s, t) => s + claudeEquivalentCost(t.usage), 0);
  let hit = 0;
  let miss = 0;
  for (const t of turns) {
    hit += t.usage.promptCacheHitTokens;
    miss += t.usage.promptCacheMissTokens;
  }
  const cacheHitRatio = hit + miss > 0 ? hit / (hit + miss) : 0;
  const savingsVsClaude = totalClaude > 0 ? 1 - totalCost / totalClaude : 0;
  const lastTurn = turns[turns.length - 1];
  return {
    turns: turns.length,
    totalCostUsd: round(totalCost, 6),
    totalInputCostUsd: round(totalInput, 6),
    totalOutputCostUsd: round(totalOutput, 6),
    claudeEquivalentUsd: round(totalClaude, 6),
    savingsVsClaudePct: round(savingsVsClaude * 100, 2),
    cacheHitRatio: round(cacheHitRatio, 4),
    lastPromptTokens: lastTurn?.usage.promptTokens ?? 0,
    lastTurnCostUsd: round(lastTurn?.cost ?? 0, 6)
  };
}
function round(n, digits) {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}

export {
  recordFromLoopEvent,
  writeRecord,
  openTranscriptFile,
  readTranscript,
  groupRecordsByTurn,
  computeCumulativeStats,
  replayFromFile,
  computeReplayStats
};
//# sourceMappingURL=chunk-R7JMQMLD.js.map