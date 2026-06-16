#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  RecordView
} from "./chunk-7GUPD2RU.js";
import {
  Bar,
  ChromeRule
} from "./chunk-M4LM5SLT.js";
import {
  computeCumulativeStats,
  groupRecordsByTurn,
  replayFromFile
} from "./chunk-R7JMQMLD.js";
import "./chunk-V4AXMN4X.js";
import {
  COLOR,
  GRADIENT
} from "./chunk-BHSAOFHR.js";
import {
  Box_default,
  Static,
  Text,
  renderSync,
  require_react,
  stringWidth,
  useStdout,
  use_app_default,
  use_input_default
} from "./chunk-U25OJR4Y.js";
import "./chunk-QSKDP3OS.js";
import "./chunk-25T6CVUP.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import {
  formatBalance,
  formatCost
} from "./chunk-GCNBIWK7.js";
import {
  __toESM
} from "./chunk-TUK7OWJA.js";

// src/cli/commands/replay.ts
var import_react3 = __toESM(require_react(), 1);

// src/cli/ui/ReplayApp.tsx
var import_react2 = __toESM(require_react(), 1);

// src/cli/ui/StatsPanel.tsx
import { basename } from "path";
var import_react = __toESM(require_react(), 1);
var COLD_START_TURNS = 3;
function StatsPanel({
  summary,
  planMode,
  editMode,
  balance,
  updateAvailable,
  budgetUsd,
  rootDir,
  sessionName
}) {
  const coldStart = summary.turns <= COLD_START_TURNS;
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(
    ChromeRow,
    {
      editMode,
      planMode,
      summary,
      coldStart,
      rootDir,
      sessionName: sessionName ?? null,
      updateAvailable,
      balance: balance ?? null
    }
  ), /* @__PURE__ */ import_react.default.createElement(ChromeRule, null), budgetUsd !== null && budgetUsd !== void 0 ? /* @__PURE__ */ import_react.default.createElement(BudgetRow, { spent: summary.totalCostUsd, cap: budgetUsd }) : null);
}
function ChromeRow({
  editMode,
  planMode,
  summary,
  coldStart,
  rootDir,
  sessionName,
  updateAvailable,
  balance
}) {
  const modePill = pickModePill(planMode, editMode);
  const projectName = rootDir ? basename(rootDir) : null;
  const cachePct = (summary.cacheHitRatio * 100).toFixed(1);
  const cacheColor = summary.cacheHitRatio >= 0.7 ? COLOR.ok : summary.cacheHitRatio >= 0.4 ? COLOR.warn : COLOR.err;
  const balanceLabel = balance ? `[${formatBalance(balance.total, balance.currency, { label: true })}]` : "";
  const costLabel = `[${formatCost(summary.totalCostUsd, balance?.currency)}]`;
  const cacheLabel = "[c \u25B0\u25B0\u25B0\u25B0\u25B0\u25B0 100%]";
  const updateLabel = updateAvailable ? `\u2191 ${updateAvailable}` : "";
  const { stdout } = useStdout();
  const cols = (stdout?.columns ?? 80) - 2;
  const SEP_DOT = stringWidth("  \xB7  ");
  const SEP_ARROW = stringWidth("  \u203A  ");
  const GAP = 2;
  const fixedLeft = stringWidth("\u25C8 reasonix") + (projectName ? SEP_DOT + stringWidth(projectName) : 0);
  const modeW = modePill ? GAP + stringWidth(`[${modePill.label}]`) : 0;
  const fixedRight = modeW + stringWidth(costLabel);
  let budget = cols - fixedLeft - fixedRight;
  const balW = balance ? GAP + stringWidth(balanceLabel) : 0;
  const cacheW = GAP + stringWidth(cacheLabel);
  const sessionW = sessionName ? SEP_ARROW + stringWidth(sessionName) : 0;
  const updateW = updateLabel ? GAP + stringWidth(updateLabel) : 0;
  const showBalance = balW > 0 && budget >= balW;
  if (showBalance) budget -= balW;
  const showCache = budget >= cacheW;
  if (showCache) budget -= cacheW;
  const showSession = sessionW > 0 && budget >= sessionW;
  if (showSession) budget -= sessionW;
  const showUpdate = updateW > 0 && budget >= updateW;
  if (showUpdate) budget -= updateW;
  return /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: GRADIENT[0] }, "\u25C8 "), /* @__PURE__ */ import_react.default.createElement(Text, { color: COLOR.brand, bold: true }, "reasonix"), projectName ? /* @__PURE__ */ import_react.default.createElement(import_react.default.Fragment, null, /* @__PURE__ */ import_react.default.createElement(Text, { color: COLOR.info, dim: true }, "  \xB7  "), /* @__PURE__ */ import_react.default.createElement(Text, null, projectName), showSession && sessionName ? /* @__PURE__ */ import_react.default.createElement(import_react.default.Fragment, null, /* @__PURE__ */ import_react.default.createElement(Text, { color: COLOR.info, dim: true }, "  \u203A  "), /* @__PURE__ */ import_react.default.createElement(Text, { color: COLOR.info }, sessionName)) : null) : null, /* @__PURE__ */ import_react.default.createElement(Box_default, { flexGrow: 1 }), showUpdate ? /* @__PURE__ */ import_react.default.createElement(import_react.default.Fragment, null, /* @__PURE__ */ import_react.default.createElement(Text, { color: COLOR.warn, bold: true }, updateLabel), /* @__PURE__ */ import_react.default.createElement(Text, null, "  ")) : null, modePill ? /* @__PURE__ */ import_react.default.createElement(import_react.default.Fragment, null, /* @__PURE__ */ import_react.default.createElement(Text, { color: modePill.color, bold: true }, `[${modePill.label}]`), /* @__PURE__ */ import_react.default.createElement(Text, null, "  ")) : null, /* @__PURE__ */ import_react.default.createElement(
    Text,
    {
      color: summary.turns === 0 || coldStart ? COLOR.info : sessionCostColor(summary.totalCostUsd),
      bold: summary.turns > 0 && !coldStart,
      dim: summary.turns === 0 || coldStart
    },
    costLabel
  ), showBalance && balance ? /* @__PURE__ */ import_react.default.createElement(import_react.default.Fragment, null, /* @__PURE__ */ import_react.default.createElement(Text, null, "  "), /* @__PURE__ */ import_react.default.createElement(Text, { color: balance.total < 1 ? COLOR.err : balance.total < 5 ? COLOR.warn : COLOR.ok }, balanceLabel)) : null, showCache ? /* @__PURE__ */ import_react.default.createElement(import_react.default.Fragment, null, /* @__PURE__ */ import_react.default.createElement(Text, null, "  "), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "["), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "c "), /* @__PURE__ */ import_react.default.createElement(
    Bar,
    {
      ratio: summary.cacheHitRatio,
      color: coldStart ? COLOR.info : cacheColor,
      cells: 6,
      dim: coldStart
    }
  ), /* @__PURE__ */ import_react.default.createElement(Text, null, " "), /* @__PURE__ */ import_react.default.createElement(Text, { color: coldStart ? void 0 : cacheColor, dim: coldStart }, coldStart && summary.turns === 0 ? "\u2014" : `${cachePct}%`), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "]")) : null);
}
function pickModePill(planMode, editMode) {
  if (planMode) return { label: t("statsPanel.modePlan"), color: COLOR.err };
  if (editMode === "yolo") return { label: t("statsPanel.modeYolo"), color: COLOR.err };
  if (editMode === "auto") return { label: t("statsPanel.modeAuto"), color: COLOR.primary };
  if (editMode === "review") return { label: t("statsPanel.modeReview"), color: COLOR.info };
  return null;
}
function BudgetRow({ spent, cap }) {
  const pct = Math.max(0, spent / cap * 100);
  const color = pct >= 100 ? "#f87171" : pct >= 80 ? "#fbbf24" : "#94a3b8";
  return /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("statsPanel.budget")), /* @__PURE__ */ import_react.default.createElement(Text, { color }, `$${spent.toFixed(4)} / $${cap.toFixed(2)}`, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, `  (${pct.toFixed(0)}%)`)));
}
function sessionCostColor(cost) {
  if (cost <= 0) return void 0;
  if (cost >= 5) return COLOR.err;
  if (cost >= 0.5) return COLOR.warn;
  return COLOR.ok;
}

// src/cli/ui/ReplayApp.tsx
function ReplayApp({ meta, pages }) {
  const { exit } = use_app_default();
  const maxIdx = Math.max(0, pages.length - 1);
  const [idx, setIdx] = (0, import_react2.useState)(maxIdx);
  use_input_default((input, key) => {
    if (input === "q" || key.ctrl && input === "c") {
      exit();
      return;
    }
    if (input === "j" || key.downArrow || input === " " || key.return) {
      setIdx((i) => Math.min(maxIdx, i + 1));
    } else if (input === "k" || key.upArrow) {
      setIdx((i) => Math.max(0, i - 1));
    } else if (input === "g") {
      setIdx(0);
    } else if (input === "G") {
      setIdx(maxIdx);
    } else if (input === "h" || key.leftArrow) {
      setIdx(0);
    } else if (input === "l" || key.rightArrow) {
      setIdx(maxIdx);
    }
  });
  const cumStats = (0, import_react2.useMemo)(() => computeCumulativeStats(pages, idx), [pages, idx]);
  const summary = {
    turns: cumStats.turns,
    totalCostUsd: cumStats.totalCostUsd,
    totalInputCostUsd: cumStats.totalInputCostUsd,
    totalOutputCostUsd: cumStats.totalOutputCostUsd,
    claudeEquivalentUsd: cumStats.claudeEquivalentUsd,
    savingsVsClaudePct: cumStats.savingsVsClaudePct,
    cacheHitRatio: cumStats.cacheHitRatio,
    // Replay is read-only — no live last-turn prompt tokens to show.
    lastPromptTokens: 0,
    lastTurnCostUsd: 0
  };
  const prefixHash = cumStats.prefixHashes.length === 1 ? cumStats.prefixHashes[0].slice(0, 16) : cumStats.prefixHashes.length === 0 ? t("replayApp.untracked") : t("replayApp.churned", { count: cumStats.prefixHashes.length });
  const currentPage = pages[idx];
  const progressLabel = pages.length === 0 ? t("replayApp.emptyTranscript") : t("replayApp.turnProgress", { current: idx + 1, total: pages.length });
  return /* @__PURE__ */ import_react2.default.createElement(Box_default, { flexDirection: "column" }, /* @__PURE__ */ import_react2.default.createElement(StatsPanel, { summary }), /* @__PURE__ */ import_react2.default.createElement(Box_default, { flexDirection: "column", marginTop: 1, paddingX: 1 }, /* @__PURE__ */ import_react2.default.createElement(Box_default, { justifyContent: "space-between" }, /* @__PURE__ */ import_react2.default.createElement(Text, { color: "ansi:cyan", bold: true }, progressLabel), meta ? /* @__PURE__ */ import_react2.default.createElement(Text, { dim: true }, meta.source, meta.task ? ` \xB7 ${meta.task}` : "", meta.mode ? ` \xB7 ${meta.mode}` : "") : null), currentPage ? /* @__PURE__ */ import_react2.default.createElement(Static, { items: currentPage.records.map((rec, i) => ({ key: `${idx}-${i}`, rec })) }, ({ key, rec }) => /* @__PURE__ */ import_react2.default.createElement(RecordView, { key, rec })) : /* @__PURE__ */ import_react2.default.createElement(Text, { dim: true, italic: true }, t("replayApp.noRecords"))), /* @__PURE__ */ import_react2.default.createElement(Box_default, { marginTop: 1, paddingX: 1, borderStyle: "single", borderColor: "ansi:blackBright" }, /* @__PURE__ */ import_react2.default.createElement(Text, { dim: true }, /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "j"), "/", /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "\u2193"), "/", /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "space"), " next \xB7 ", /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "k"), "/", /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "\u2191"), " prev \xB7 ", /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "g"), " first \xB7 ", /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "G"), " last \xB7", " ", /* @__PURE__ */ import_react2.default.createElement(Text, { bold: true }, "q"), " quit")));
}

// src/cli/commands/replay.ts
async function replayCommand(opts) {
  const wantPrint = opts.print || !process.stdout.isTTY || opts.head !== void 0 || opts.tail !== void 0;
  if (wantPrint) {
    printReplay(opts);
    return;
  }
  const { parsed } = replayFromFile(opts.path);
  const pages = groupRecordsByTurn(parsed.records);
  const { waitUntilExit } = renderSync(import_react3.default.createElement(ReplayApp, { meta: parsed.meta, pages }), {
    exitOnCtrlC: true,
    patchConsole: false
  });
  await waitUntilExit();
}
function printReplay(opts) {
  const { parsed, stats } = replayFromFile(opts.path);
  if (parsed.meta) {
    const m = parsed.meta;
    const bits = [`source=${m.source}`];
    if (m.model) bits.push(`model=${m.model}`);
    if (m.task) bits.push(`task=${m.task}`);
    if (m.mode) bits.push(`mode=${m.mode}`);
    if (m.repeat !== void 0) bits.push(`repeat=${m.repeat}`);
    bits.push(`started=${m.startedAt}`);
    console.log(`[meta] ${bits.join(" ")}`);
    console.log("");
  }
  const records = sliceRecords(parsed.records, opts);
  for (const rec of records) {
    renderRecord(rec);
  }
  console.log("");
  console.log("\u2500\u2500 summary \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500");
  console.log(`model calls:         ${stats.turns}`);
  console.log(`user turns:          ${stats.userTurns}`);
  console.log(`tool calls:          ${stats.toolCalls}`);
  console.log(`cache hit:           ${(stats.cacheHitRatio * 100).toFixed(1)}%`);
  console.log(`cost:                $${stats.totalCostUsd.toFixed(6)}`);
  console.log(`claude equivalent:   $${stats.claudeEquivalentUsd.toFixed(6)}`);
  console.log(`savings vs claude:   ${stats.savingsVsClaudePct.toFixed(1)}%`);
  console.log(`models:              ${stats.models.join(", ") || "\u2014"}`);
  console.log(`prefix hashes:       ${stats.prefixHashes.length} distinct`);
  if (stats.prefixHashes.length === 1) {
    console.log(`  (byte-stable prefix: ${stats.prefixHashes[0]?.slice(0, 16)}\u2026)`);
  } else if (stats.prefixHashes.length > 1) {
    console.log("  (prefix churned \u2014 cache-hostile session)");
  }
}
function sliceRecords(records, opts) {
  if (opts.head !== void 0 && opts.head > 0) return records.slice(0, opts.head);
  if (opts.tail !== void 0 && opts.tail > 0) return records.slice(-opts.tail);
  return records;
}
function renderRecord(rec) {
  const turn = `[t${rec.turn}]`;
  if (rec.role === "user") {
    console.log(`${turn} USER: ${oneLine(rec.content)}`);
  } else if (rec.role === "assistant_final") {
    const cost = rec.cost !== void 0 ? ` $${rec.cost.toFixed(6)}` : "";
    const cache = rec.usage && (rec.usage.prompt_cache_hit_tokens !== void 0 || rec.usage.prompt_cache_miss_tokens !== void 0) ? (() => {
      const hit = rec.usage.prompt_cache_hit_tokens ?? 0;
      const miss = rec.usage.prompt_cache_miss_tokens ?? 0;
      const total = hit + miss;
      return total > 0 ? ` cache=${(hit / total * 100).toFixed(1)}%` : "";
    })() : "";
    console.log(`${turn} AGENT:${cost}${cache} ${oneLine(rec.content)}`);
  } else if (rec.role === "tool") {
    const args = rec.args ? ` args=${oneLine(rec.args, 80)}` : "";
    console.log(`${turn} TOOL ${rec.tool ?? "?"}:${args} \u2192 ${oneLine(rec.content, 120)}`);
  } else if (rec.role === "error") {
    console.log(`${turn} ERROR: ${rec.error ?? rec.content}`);
  } else if (rec.role === "done") {
  } else {
    console.log(`${turn} ${rec.role}: ${oneLine(rec.content)}`);
  }
}
function oneLine(s, max = 200) {
  const collapsed = s.replace(/\s+/g, " ").trim();
  return collapsed.length > max ? `${collapsed.slice(0, max)}\u2026` : collapsed;
}
export {
  replayCommand
};
//# sourceMappingURL=replay-2GXFWL6O.js.map