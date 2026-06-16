#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  computeReplayStats
} from "./chunk-R7JMQMLD.js";

// src/transcript/diff.ts
function findNextDivergence(pairs, fromIdx) {
  for (let i = fromIdx + 1; i < pairs.length; i++) {
    if (pairs[i].kind !== "match") return i;
  }
  return -1;
}
function findPrevDivergence(pairs, fromIdx) {
  const start = Math.min(fromIdx - 1, pairs.length - 1);
  for (let i = start; i >= 0; i--) {
    if (pairs[i].kind !== "match") return i;
  }
  return -1;
}
function diffTranscripts(a, b) {
  const aSide = {
    label: a.label,
    meta: a.parsed.meta,
    records: a.parsed.records,
    stats: computeReplayStats(a.parsed.records)
  };
  const bSide = {
    label: b.label,
    meta: b.parsed.meta,
    records: b.parsed.records,
    stats: computeReplayStats(b.parsed.records)
  };
  const aByTurn = groupByTurn(a.parsed.records);
  const bByTurn = groupByTurn(b.parsed.records);
  const turns = [.../* @__PURE__ */ new Set([...aByTurn.keys(), ...bByTurn.keys()])].sort((x, y) => x - y);
  const pairs = [];
  let firstDivergenceTurn = null;
  for (const turn of turns) {
    const aGroup = aByTurn.get(turn) ?? { assistant: void 0, tools: [] };
    const bGroup = bByTurn.get(turn) ?? { assistant: void 0, tools: [] };
    const aAssistant = aGroup.assistant;
    const bAssistant = bGroup.assistant;
    const aTools = aGroup.tools;
    const bTools = bGroup.tools;
    let kind;
    let divergenceNote;
    if (!aAssistant && bAssistant) kind = "only_in_b";
    else if (aAssistant && !bAssistant) kind = "only_in_a";
    else if (!aAssistant && !bAssistant)
      kind = "diverge";
    else {
      divergenceNote = classifyDivergence(aAssistant, bAssistant, aTools, bTools);
      kind = divergenceNote ? "diverge" : "match";
    }
    if (kind !== "match" && firstDivergenceTurn === null) firstDivergenceTurn = turn;
    pairs.push({ turn, aAssistant, bAssistant, aTools, bTools, kind, divergenceNote });
  }
  return { a: aSide, b: bSide, pairs, firstDivergenceTurn };
}
function classifyDivergence(a, b, aTools, bTools) {
  const aNames = aTools.map((t) => t.tool ?? "").sort();
  const bNames = bTools.map((t) => t.tool ?? "").sort();
  if (aNames.join(",") !== bNames.join(",")) {
    return `tool calls differ: A=[${aNames.join(",") || "\u2014"}] B=[${bNames.join(",") || "\u2014"}]`;
  }
  for (let i = 0; i < aTools.length; i++) {
    const at = aTools[i];
    const bt = bTools[i];
    if (at.tool !== bt.tool) continue;
    if ((at.args ?? "") !== (bt.args ?? "")) {
      return `"${at.tool}" args differ`;
    }
  }
  const simRatio = similarity(a.content, b.content);
  if (simRatio < 0.75) return `text similarity ${(simRatio * 100).toFixed(0)}%`;
  return void 0;
}
function similarity(a, b) {
  if (a === b) return 1;
  if (!a && !b) return 1;
  if (!a || !b) return 0;
  const maxLen = Math.max(a.length, b.length);
  if (maxLen > 2e3) return tokenOverlap(a, b);
  const dist = levenshtein(a, b);
  return 1 - dist / maxLen;
}
function tokenOverlap(a, b) {
  const ta = new Set(a.toLowerCase().split(/\s+/).filter(Boolean));
  const tb = new Set(b.toLowerCase().split(/\s+/).filter(Boolean));
  if (ta.size === 0 && tb.size === 0) return 1;
  let shared = 0;
  for (const t of ta) if (tb.has(t)) shared++;
  return 2 * shared / (ta.size + tb.size);
}
function levenshtein(a, b) {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = new Array(n + 1);
  let curr = new Array(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n];
}
function groupByTurn(records) {
  const out = /* @__PURE__ */ new Map();
  for (const rec of records) {
    if (rec.role === "user") continue;
    const g = out.get(rec.turn) ?? { tools: [] };
    if (rec.role === "assistant_final") g.assistant = rec;
    else if (rec.role === "tool") g.tools.push(rec);
    out.set(rec.turn, g);
  }
  return out;
}
function renderSummaryTable(report, _opts = {}) {
  const a = report.a;
  const b = report.b;
  const lines = [];
  lines.push("Comparing:");
  lines.push(`  A  ${a.label}`);
  lines.push(`  B  ${b.label}`);
  lines.push("");
  lines.push(row(["", "A", "B", "\u0394"], [20, 14, 14, 14]));
  lines.push(
    row(["\u2500".repeat(20), "\u2500".repeat(14), "\u2500".repeat(14), "\u2500".repeat(14)], [20, 14, 14, 14])
  );
  lines.push(statRow("model calls", a.stats.turns, b.stats.turns));
  lines.push(statRow("user turns", a.stats.userTurns, b.stats.userTurns));
  lines.push(statRow("tool calls", a.stats.toolCalls, b.stats.toolCalls));
  lines.push(
    row(
      [
        "cache hit",
        `${pct(a.stats.cacheHitRatio)}`,
        `${pct(b.stats.cacheHitRatio)}`,
        signPct(b.stats.cacheHitRatio - a.stats.cacheHitRatio)
      ],
      [20, 14, 14, 14]
    )
  );
  lines.push(
    row(
      [
        "cost (USD)",
        `$${a.stats.totalCostUsd.toFixed(6)}`,
        `$${b.stats.totalCostUsd.toFixed(6)}`,
        costDelta(a.stats.totalCostUsd, b.stats.totalCostUsd)
      ],
      [20, 14, 14, 14]
    )
  );
  lines.push(statRow("prefix hashes", a.stats.prefixHashes.length, b.stats.prefixHashes.length));
  lines.push("");
  const aPrefixStable = a.stats.prefixHashes.length <= 1;
  const bPrefixStable = b.stats.prefixHashes.length <= 1;
  if (aPrefixStable !== bPrefixStable) {
    const stable = aPrefixStable ? "A" : "B";
    const churn = aPrefixStable ? "B" : "A";
    const churnCount = aPrefixStable ? b.stats.prefixHashes.length : a.stats.prefixHashes.length;
    lines.push(
      `prefix stability: ${stable} stayed byte-stable across ${Math.max(
        a.stats.turns,
        b.stats.turns
      )} turns; ${churn} churned ${churnCount} distinct prefixes.`
    );
    lines.push("");
  } else if (a.stats.prefixHashes[0] && a.stats.prefixHashes[0] === b.stats.prefixHashes[0]) {
    lines.push(
      `prefix: A and B share the same prefix hash (${a.stats.prefixHashes[0].slice(0, 12)}\u2026) \u2014 cache delta is attributable to log stability, not prompt change.`
    );
    lines.push("");
  }
  if (report.firstDivergenceTurn !== null) {
    const p = report.pairs.find((p2) => p2.turn === report.firstDivergenceTurn);
    lines.push(
      `first divergence: turn ${report.firstDivergenceTurn} \u2014 ${p?.divergenceNote ?? "?"}`
    );
    if (p?.aAssistant) lines.push(`  A \u2192 ${truncate(p.aAssistant.content, 100)}`);
    if (p?.bAssistant) lines.push(`  B \u2192 ${truncate(p.bAssistant.content, 100)}`);
  } else {
    lines.push("no material divergence detected (texts within similarity threshold).");
  }
  return lines.join("\n");
}
function renderMarkdown(report) {
  const a = report.a;
  const b = report.b;
  const out = [];
  out.push(`# Transcript diff: ${a.label} vs ${b.label}`);
  out.push("");
  if (a.meta || b.meta) {
    out.push("## Meta");
    out.push("");
    out.push(`| | ${a.label} | ${b.label} |`);
    out.push("|---|---|---|");
    out.push(`| source | ${a.meta?.source ?? "\u2014"} | ${b.meta?.source ?? "\u2014"} |`);
    out.push(`| model | ${a.meta?.model ?? "\u2014"} | ${b.meta?.model ?? "\u2014"} |`);
    out.push(`| task | ${a.meta?.task ?? "\u2014"} | ${b.meta?.task ?? "\u2014"} |`);
    out.push(`| startedAt | ${a.meta?.startedAt ?? "\u2014"} | ${b.meta?.startedAt ?? "\u2014"} |`);
    out.push("");
  }
  out.push("## Summary");
  out.push("");
  out.push(`| metric | ${a.label} | ${b.label} | delta |`);
  out.push("|---|---:|---:|---:|");
  out.push(
    `| model calls | ${a.stats.turns} | ${b.stats.turns} | ${signed(b.stats.turns - a.stats.turns)} |`
  );
  out.push(
    `| user turns | ${a.stats.userTurns} | ${b.stats.userTurns} | ${signed(b.stats.userTurns - a.stats.userTurns)} |`
  );
  out.push(
    `| tool calls | ${a.stats.toolCalls} | ${b.stats.toolCalls} | ${signed(b.stats.toolCalls - a.stats.toolCalls)} |`
  );
  out.push(
    `| cache hit | ${pct(a.stats.cacheHitRatio)} | ${pct(b.stats.cacheHitRatio)} | **${signPct(b.stats.cacheHitRatio - a.stats.cacheHitRatio)}** |`
  );
  out.push(
    `| cost (USD) | $${a.stats.totalCostUsd.toFixed(6)} | $${b.stats.totalCostUsd.toFixed(6)} | ${costDelta(a.stats.totalCostUsd, b.stats.totalCostUsd)} |`
  );
  out.push(
    `| prefix hashes | ${a.stats.prefixHashes.length} | ${b.stats.prefixHashes.length} | \u2014 |`
  );
  out.push("");
  out.push("## Turn-by-turn");
  out.push("");
  out.push(`| turn | kind | ${a.label} tool calls | ${b.label} tool calls | note |`);
  out.push("|---:|:---:|---|---|---|");
  for (const p of report.pairs) {
    const aTools = p.aTools.map((t) => t.tool).filter(Boolean).join(", ") || "\u2014";
    const bTools = p.bTools.map((t) => t.tool).filter(Boolean).join(", ") || "\u2014";
    out.push(`| ${p.turn} | ${p.kind} | ${aTools} | ${bTools} | ${p.divergenceNote ?? ""} |`);
  }
  out.push("");
  if (report.firstDivergenceTurn !== null) {
    const p = report.pairs.find((x) => x.turn === report.firstDivergenceTurn);
    out.push(`## First divergence (turn ${report.firstDivergenceTurn})`);
    out.push("");
    out.push(p?.divergenceNote ?? "");
    out.push("");
    if (p?.aAssistant) {
      out.push(`**${a.label}:**`);
      out.push("");
      out.push("```");
      out.push(p.aAssistant.content);
      out.push("```");
      out.push("");
    }
    if (p?.bAssistant) {
      out.push(`**${b.label}:**`);
      out.push("");
      out.push("```");
      out.push(p.bAssistant.content);
      out.push("```");
      out.push("");
    }
  }
  return out.join("\n");
}
function row(cols, widths) {
  return cols.map((c, i) => padRight(c, widths[i] ?? c.length)).join(" ");
}
function statRow(label, av, bv) {
  return row([label, `${av}`, `${bv}`, signed(bv - av)], [20, 14, 14, 14]);
}
function padRight(s, w) {
  return s.length >= w ? s : s + " ".repeat(w - s.length);
}
function signed(n) {
  if (n === 0) return "0";
  return `${n > 0 ? "+" : ""}${n}`;
}
function signPct(diff) {
  if (diff === 0) return "0pp";
  const s = (diff * 100).toFixed(1);
  return `${diff > 0 ? "+" : ""}${s}pp`;
}
function pct(x) {
  return `${(x * 100).toFixed(1)}%`;
}
function costDelta(a, b) {
  if (a === 0 && b === 0) return "\u2014";
  if (a === 0) return "new";
  const pctChange = (b - a) / a * 100;
  return `${pctChange > 0 ? "+" : ""}${pctChange.toFixed(1)}%`;
}
function truncate(s, n) {
  return s.length > n ? `${s.slice(0, n)}\u2026` : s;
}

export {
  findNextDivergence,
  findPrevDivergence,
  diffTranscripts,
  renderSummaryTable,
  renderMarkdown
};
//# sourceMappingURL=chunk-J26XOB2T.js.map