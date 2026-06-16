#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  RecordView
} from "./chunk-7GUPD2RU.js";
import {
  diffTranscripts,
  findNextDivergence,
  findPrevDivergence,
  renderMarkdown,
  renderSummaryTable
} from "./chunk-J26XOB2T.js";
import {
  readTranscript
} from "./chunk-R7JMQMLD.js";
import "./chunk-V4AXMN4X.js";
import {
  Box_default,
  Static,
  Text,
  renderSync,
  require_react,
  use_app_default,
  use_input_default
} from "./chunk-U25OJR4Y.js";
import "./chunk-QSKDP3OS.js";
import "./chunk-25T6CVUP.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import "./chunk-GCNBIWK7.js";
import {
  __toESM
} from "./chunk-TUK7OWJA.js";

// src/cli/commands/diff.ts
import { writeFileSync } from "fs";
import { basename } from "path";
var import_react2 = __toESM(require_react(), 1);

// src/cli/ui/DiffApp.tsx
var import_react = __toESM(require_react(), 1);
function DiffApp({ report }) {
  const { exit } = use_app_default();
  const maxIdx = Math.max(0, report.pairs.length - 1);
  const initialIdx = report.firstDivergenceTurn ? report.pairs.findIndex((p) => p.turn === report.firstDivergenceTurn) : 0;
  const [idx, setIdx] = (0, import_react.useState)(Math.max(0, initialIdx));
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
    } else if (input === "n") {
      const next = findNextDivergence(report.pairs, idx);
      if (next !== -1) setIdx(next);
    } else if (input === "N" || input === "p") {
      const prev = findPrevDivergence(report.pairs, idx);
      if (prev !== -1) setIdx(prev);
    }
  });
  const pair = report.pairs[idx];
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column" }, /* @__PURE__ */ import_react.default.createElement(DiffHeader, { report }), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, paddingX: 1, justifyContent: "space-between" }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:cyan", bold: true }, t("diffApp.turnLabel", {
    turn: pair?.turn ?? "?",
    current: idx + 1,
    total: report.pairs.length
  })), /* @__PURE__ */ import_react.default.createElement(Text, null, pair ? /* @__PURE__ */ import_react.default.createElement(KindBadge, { kind: pair.kind }) : null)), /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "row", marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Pane, { label: report.a.label, headerColor: "ansi:blue", records: paneRecords(pair, "a") }), /* @__PURE__ */ import_react.default.createElement(Pane, { label: report.b.label, headerColor: "ansi:magenta", records: paneRecords(pair, "b") })), pair?.divergenceNote ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:yellow" }, "\u2605 "), /* @__PURE__ */ import_react.default.createElement(Text, null, pair.divergenceNote)) : null, /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, paddingX: 1, borderStyle: "single", borderColor: "ansi:blackBright" }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "j"), "/", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "\\u2193"), " next \\u00b7 ", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "k"), "/", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "\\u2191"), " prev \\u00b7 ", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "n"), " next-diverge \\u00b7", " ", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "N"), "/", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "p"), " prev-diverge \\u00b7 ", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "g"), "/", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "G"), " first/last \\u00b7 ", /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, "q"), " quit")));
}
function DiffHeader({ report }) {
  const a = report.a;
  const b = report.b;
  const cacheDelta = b.stats.cacheHitRatio - a.stats.cacheHitRatio;
  const costDelta = a.stats.totalCostUsd > 0 ? (b.stats.totalCostUsd - a.stats.totalCostUsd) / a.stats.totalCostUsd * 100 : 0;
  const aStable = a.stats.prefixHashes.length <= 1;
  const bStable = b.stats.prefixHashes.length <= 1;
  let prefixLine = null;
  if (aStable !== bStable) {
    const stableLabel = aStable ? report.a.label : report.b.label;
    const churnLabel = aStable ? report.b.label : report.a.label;
    const churnCount = aStable ? b.stats.prefixHashes.length : a.stats.prefixHashes.length;
    prefixLine = `${stableLabel} stayed byte-stable; ${churnLabel} churned ${churnCount} distinct prefixes.`;
  } else if (a.stats.prefixHashes[0] && a.stats.prefixHashes[0] === b.stats.prefixHashes[0]) {
    prefixLine = `shared prefix hash ${a.stats.prefixHashes[0].slice(0, 12)}\u2026 \u2014 cache delta attributable to log stability, not prompt change.`;
  }
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", borderStyle: "round", borderColor: "ansi:cyan", paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Box_default, { justifyContent: "space-between" }, /* @__PURE__ */ import_react.default.createElement(Text, null, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:cyan", bold: true }, t("diffApp.title")), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, " \\u00b7 A="), /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:blue" }, a.label), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, " vs B="), /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:magenta" }, b.label)), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("diffApp.turnsAligned", { count: report.pairs.length }))), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, gap: 3 }, /* @__PURE__ */ import_react.default.createElement(Text, null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "cache "), /* @__PURE__ */ import_react.default.createElement(Text, null, (a.stats.cacheHitRatio * 100).toFixed(1), "%"), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, " \u2192 "), /* @__PURE__ */ import_react.default.createElement(Text, null, (b.stats.cacheHitRatio * 100).toFixed(1), "%"), /* @__PURE__ */ import_react.default.createElement(Text, { color: cacheDelta >= 0 ? "ansi:green" : "ansi:red", bold: true }, "  ", cacheDelta >= 0 ? "+" : "", (cacheDelta * 100).toFixed(1), "pp")), /* @__PURE__ */ import_react.default.createElement(Text, null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "cost "), /* @__PURE__ */ import_react.default.createElement(Text, null, "$", a.stats.totalCostUsd.toFixed(6)), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, " \u2192 "), /* @__PURE__ */ import_react.default.createElement(Text, null, "$", b.stats.totalCostUsd.toFixed(6)), /* @__PURE__ */ import_react.default.createElement(Text, { color: costDelta <= 0 ? "ansi:green" : "ansi:red", bold: true }, "  ", costDelta >= 0 ? "+" : "", costDelta.toFixed(1), "%")), /* @__PURE__ */ import_react.default.createElement(Text, null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "model calls "), /* @__PURE__ */ import_react.default.createElement(Text, null, a.stats.turns, " \u2192 ", b.stats.turns))), prefixLine ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true, italic: true }, prefixLine)) : null);
}
function Pane({
  label,
  headerColor,
  records
}) {
  return /* @__PURE__ */ import_react.default.createElement(
    Box_default,
    {
      flexDirection: "column",
      flexGrow: 1,
      paddingX: 1,
      borderStyle: "single",
      borderColor: headerColor
    },
    /* @__PURE__ */ import_react.default.createElement(Text, { color: headerColor, bold: true }, label),
    records.length === 0 ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true, italic: true }, t("diffApp.paneEmpty"))) : /* @__PURE__ */ import_react.default.createElement(Static, { items: records.map((rec, i) => ({ key: `${label}-${i}`, rec })) }, ({ key, rec }) => /* @__PURE__ */ import_react.default.createElement(RecordView, { key, rec, compact: true }))
  );
}
function KindBadge({ kind }) {
  if (kind === "match") {
    return /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:green" }, t("diffApp.kindMatch"));
  }
  if (kind === "diverge") {
    return /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:yellow" }, t("diffApp.kindDiverge"));
  }
  if (kind === "only_in_a") {
    return /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:blue" }, t("diffApp.kindOnlyInA"));
  }
  return /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:magenta" }, t("diffApp.kindOnlyInB"));
}
function paneRecords(pair, side) {
  if (!pair) return [];
  const tools = side === "a" ? pair.aTools : pair.bTools;
  const assistant = side === "a" ? pair.aAssistant : pair.bAssistant;
  const out = [...tools];
  if (assistant) out.push(assistant);
  return out;
}

// src/cli/commands/diff.ts
async function diffCommand(opts) {
  const aParsed = readTranscript(opts.a);
  const bParsed = readTranscript(opts.b);
  const report = diffTranscripts(
    { label: opts.labelA ?? basename(opts.a), parsed: aParsed },
    { label: opts.labelB ?? basename(opts.b), parsed: bParsed }
  );
  const wantMarkdown = !!opts.mdPath;
  const wantPrint = opts.print || !process.stdout.isTTY;
  const wantTui = opts.tui || !wantPrint && !wantMarkdown;
  if (wantMarkdown) {
    console.log(renderSummaryTable(report));
    const md = renderMarkdown(report);
    writeFileSync(opts.mdPath, md, "utf8");
    console.log(`
markdown report written to ${opts.mdPath}`);
    return;
  }
  if (wantTui) {
    const { waitUntilExit } = renderSync(import_react2.default.createElement(DiffApp, { report }), {
      exitOnCtrlC: true,
      patchConsole: false
    });
    await waitUntilExit();
    return;
  }
  console.log(renderSummaryTable(report));
}
export {
  diffCommand
};
//# sourceMappingURL=diff-LASK2CN5.js.map