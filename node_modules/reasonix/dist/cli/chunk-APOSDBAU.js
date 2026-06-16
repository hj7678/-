#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  aggregateUsage,
  bucketCacheHitRatio,
  bucketSavingsFraction,
  defaultUsageLogPath,
  formatLogSize,
  readUsageLog
} from "./chunk-FK7NXDRP.js";
import {
  t
} from "./chunk-U7G72DHQ.js";

// src/cli/commands/stats.ts
import { existsSync, readFileSync } from "fs";
function statsCommand(opts) {
  if (opts.transcript) {
    transcriptSummary(opts.transcript);
    return;
  }
  dashboard(opts);
}
function transcriptSummary(path) {
  if (!existsSync(path)) {
    console.error(`no such transcript: ${path}`);
    process.exit(1);
  }
  const lines = readFileSync(path, "utf8").split(/\r?\n/).filter(Boolean);
  let assistantTurns = 0;
  let toolCalls = 0;
  let lastTurn = 0;
  for (const line of lines) {
    try {
      const rec = JSON.parse(line);
      if (rec.role === "assistant_final") assistantTurns++;
      if (rec.role === "tool") toolCalls++;
      if (typeof rec.turn === "number") lastTurn = Math.max(lastTurn, rec.turn);
    } catch {
    }
  }
  console.log(`transcript:       ${path}`);
  console.log(`assistant turns:  ${assistantTurns}`);
  console.log(`tool invocations: ${toolCalls}`);
  console.log(`last turn index:  ${lastTurn}`);
}
function dashboard(opts) {
  const path = opts.logPath ?? defaultUsageLogPath();
  const records = readUsageLog(path);
  if (records.length === 0) {
    console.log("no usage data yet.");
    console.log("");
    console.log(`  ${path}`);
    console.log("");
    console.log(t("stats.usageHint"));
    console.log(t("stats.usageDetail"));
    return;
  }
  const agg = aggregateUsage(records, { now: opts.now });
  console.log(renderDashboard(agg, path));
}
function renderDashboard(agg, logPath) {
  const lines = [];
  const size = formatLogSize(logPath);
  lines.push(`Reasonix usage \u2014 ${logPath}${size ? ` (${size})` : ""}`);
  lines.push("");
  lines.push(header());
  lines.push(divider());
  for (const b of agg.buckets) {
    lines.push(bucketRow(b));
  }
  lines.push("");
  if (agg.byModel.length > 0) {
    const totalTurns = agg.buckets[agg.buckets.length - 1]?.turns ?? 0;
    const top = agg.byModel[0];
    if (top && totalTurns > 0) {
      const pct = (top.turns / totalTurns * 100).toFixed(0);
      lines.push(`most used model:   ${top.model} (${pct}% of turns)`);
    }
  }
  if (agg.bySession.length > 0) {
    const top = agg.bySession[0];
    if (top) lines.push(`top session:       ${top.session} (${top.turns} turns)`);
  }
  if (agg.firstSeen) {
    lines.push(`tracked since:     ${new Date(agg.firstSeen).toISOString().slice(0, 10)}`);
  }
  if (agg.subagents) {
    lines.push("");
    lines.push(renderSubagentSection(agg.subagents));
  }
  return lines.join("\n");
}
function renderSubagentSection(sub) {
  const lines = [];
  const seconds = (sub.totalDurationMs / 1e3).toFixed(1);
  lines.push(
    `subagent activity: ${sub.total} run(s) \xB7 $${sub.costUsd.toFixed(6)} \xB7 ${seconds}s total`
  );
  const top = sub.bySkill.slice(0, 5);
  for (const s of top) {
    const sec = (s.durationMs / 1e3).toFixed(1);
    lines.push(
      `  ${pad(s.skillName, 18)} ${pad(`${s.count}`, 4, "right")}  $${s.costUsd.toFixed(6)}  ${sec}s`
    );
  }
  if (sub.bySkill.length > top.length) {
    lines.push(`  (+${sub.bySkill.length - top.length} more)`);
  }
  return lines.join("\n");
}
function header() {
  return [
    pad("", 10),
    pad("turns", 8, "right"),
    pad("cache hit", 10, "right"),
    pad("cost (USD)", 14, "right"),
    pad("cache saved", 14, "right"),
    pad("vs Claude", 14, "right"),
    pad("saved", 10, "right")
  ].join("  ");
}
function divider() {
  return "-".repeat(86);
}
function bucketRow(b) {
  const hit = bucketCacheHitRatio(b);
  const savings = bucketSavingsFraction(b);
  return [
    pad(b.label, 10),
    pad(b.turns.toString(), 8, "right"),
    pad(b.turns > 0 ? `${(hit * 100).toFixed(1)}%` : "\u2014", 10, "right"),
    pad(b.turns > 0 ? `$${b.costUsd.toFixed(6)}` : "\u2014", 14, "right"),
    pad(
      b.turns > 0 && b.cacheSavingsUsd > 0 ? `$${b.cacheSavingsUsd.toFixed(4)}` : "\u2014",
      14,
      "right"
    ),
    pad(b.turns > 0 ? `$${b.claudeEquivUsd.toFixed(4)}` : "\u2014", 14, "right"),
    pad(b.turns > 0 && savings > 0 ? `${(savings * 100).toFixed(1)}%` : "\u2014", 10, "right")
  ].join("  ");
}
function pad(s, width, align = "left") {
  if (s.length >= width) return s;
  const fill = " ".repeat(width - s.length);
  return align === "right" ? `${fill}${s}` : `${s}${fill}`;
}

export {
  statsCommand,
  renderDashboard
};
//# sourceMappingURL=chunk-APOSDBAU.js.map