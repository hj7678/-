#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import "./chunk-DFHI2MRB.js";
import "./chunk-4SBXAHR6.js";
import "./chunk-J26XOB2T.js";
import "./chunk-R7JMQMLD.js";
import "./chunk-4V4TKQMB.js";
import "./chunk-FK7NXDRP.js";
import "./chunk-V4AXMN4X.js";
import "./chunk-XHP6NYOT.js";
import "./chunk-J4MYMBJ7.js";
import "./chunk-BOWSNGQC.js";
import "./chunk-QSKDP3OS.js";
import "./chunk-25T6CVUP.js";
import "./chunk-NVI4XPOQ.js";
import "./chunk-6UNHNVJR.js";
import {
  listSessions,
  loadSessionMessages,
  sessionPath
} from "./chunk-P5SUHDUQ.js";
import "./chunk-XXC2BYTV.js";
import "./chunk-2UQP6H6T.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/cli/commands/sessions.ts
function sessionsCommand(opts) {
  if (opts.name) {
    inspectSession(opts.name, !!opts.verbose);
  } else {
    listAll();
  }
}
function listAll() {
  const items = listSessions();
  if (items.length === 0) {
    console.log(t("sessions.emptyHint"));
    return;
  }
  console.log(t("sessions.listHeader"));
  console.log("");
  console.log(`  ${"name".padEnd(22)} ${"msgs".padStart(6)}  ${"size".padStart(8)}  modified`);
  console.log(`  ${"\u2500".repeat(60)}`);
  for (const s of items) {
    const sizeKb = `${(s.size / 1024).toFixed(1)} KB`;
    const when = s.mtime.toISOString().replace("T", " ").slice(0, 16);
    console.log(
      `  ${s.name.padEnd(22)} ${String(s.messageCount).padStart(6)}  ${sizeKb.padStart(8)}  ${when}`
    );
    const details = sessionDetails(s);
    if (details.length > 0) console.log(`      ${details.join(" \xB7 ")}`);
  }
  console.log("");
  console.log(t("sessions.inspectHint"));
  console.log(t("sessions.resumeHint"));
}
function inspectSession(name, verbose) {
  const path = sessionPath(name);
  const messages = loadSessionMessages(name);
  if (messages.length === 0) {
    console.error(t("sessions.noSession", { name }));
    console.error(t("sessions.lookedAt", { path }));
    process.exit(1);
  }
  console.log(`[session] ${name}   ${messages.length} messages   ${path}`);
  console.log("");
  let turnIndex = 0;
  for (const msg of messages) {
    renderMessage(msg, turnIndex, verbose);
    if (msg.role === "user") turnIndex++;
  }
}
function renderMessage(msg, turnIdx, verbose) {
  const turn = turnIdx > 0 ? `[t${turnIdx}]` : "[start]";
  const content = typeof msg.content === "string" ? msg.content : "";
  const flat = oneLine(content);
  if (msg.role === "user") {
    console.log(`${turn} USER: ${flat}`);
  } else if (msg.role === "assistant") {
    console.log(`${turn} AGENT: ${flat || "(tool call only)"}`);
    if (verbose && msg.tool_calls?.length) {
      for (const tc of msg.tool_calls) {
        console.log(
          `         \u2192 call ${tc.function?.name} ${truncate(tc.function?.arguments ?? "", 80)}`
        );
      }
    }
  } else if (msg.role === "tool") {
    console.log(`${turn} TOOL ${msg.name ?? "?"}: ${truncate(flat, 160)}`);
  } else if (msg.role === "system") {
    if (verbose) console.log(`${turn} SYSTEM: ${truncate(flat, 160)}`);
  }
}
function oneLine(s, max = 200) {
  const collapsed = s.replace(/\s+/g, " ").trim();
  return collapsed.length > max ? `${collapsed.slice(0, max)}\u2026` : collapsed;
}
function sessionDetails(s) {
  const details = [];
  if (s.meta.summary) details.push(`summary: ${oneLine(s.meta.summary, 88)}`);
  if (s.meta.workspace) details.push(`workspace: ${workspaceLabel(s.meta.workspace)}`);
  if (s.meta.branch) details.push(`branch: ${truncate(s.meta.branch, 40)}`);
  return details;
}
function workspaceLabel(workspace) {
  const trimmed = workspace.replace(/[\\/]+$/, "");
  const label = trimmed.split(/[\\/]+/).at(-1) ?? trimmed;
  return truncate(label || workspace, 40);
}
function truncate(s, max) {
  return s.length <= max ? s : `${s.slice(0, max)}\u2026`;
}
export {
  sessionsCommand
};
//# sourceMappingURL=sessions-YBPRGIAF.js.map