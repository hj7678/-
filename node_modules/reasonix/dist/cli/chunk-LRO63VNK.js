#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  t
} from "./chunk-U7G72DHQ.js";

// src/cli/ui/mcp-lifecycle.ts
var STATE = {
  handshake: { glyph: "\u21BB", label: () => t("mcpLifecycle.handshake") },
  connected: { glyph: "\u2713", label: () => t("mcpLifecycle.connected") },
  failed: { glyph: "\u2716", label: () => t("mcpLifecycle.failed") },
  disabled: { glyph: "\u25CB", label: () => t("mcpLifecycle.disabled") },
  reconnect: { glyph: "\u21BB", label: () => t("mcpLifecycle.reconnect") },
  "tools-ready": { glyph: "\u26A1", label: () => t("mcpLifecycle.toolsReady") },
  warn: { glyph: "\u26A0", label: () => t("mcpLifecycle.warnLabel") }
};
var NAME_COL = 22;
var STATE_COL = 15;
function formatMcpLifecycleEvent(ev) {
  const { glyph, label } = STATE[ev.state];
  const namePart = `MCP \xB7 ${ev.name}`;
  const namePad = " ".repeat(Math.max(1, NAME_COL - namePart.length));
  const stateField = `${glyph} ${label()}`.padEnd(STATE_COL);
  return `\u2318 ${namePart}${namePad}${stateField}${describeDetail(ev)}`;
}
function describeDetail(ev) {
  if (ev.state === "handshake") return t("mcpLifecycle.initDetail");
  if (ev.state === "failed") return ev.reason;
  if (ev.state === "disabled") return t("mcpLifecycle.disabledDetail", { name: ev.name });
  if (ev.state === "reconnect") return t("mcpLifecycle.reconnectDetail");
  if (ev.state === "tools-ready") return `${ev.tools} tools \xB7 ${ev.ms}ms`;
  if (ev.state === "warn") return ev.reason;
  const parts = [`${ev.tools} tools`];
  if (ev.resources && ev.resources > 0) parts.push(`${ev.resources} resources`);
  if (ev.prompts && ev.prompts > 0) parts.push(`${ev.prompts} prompts`);
  parts.push(`${ev.ms}ms`);
  return parts.join(" \xB7 ");
}

// src/cli/ui/mcp-toast.ts
function formatMcpSlowToast(tst) {
  const seconds = (tst.p95Ms / 1e3).toFixed(1);
  return t("mcpHealth.slowToast", { name: tst.name, seconds, sampleSize: tst.sampleSize });
}

export {
  formatMcpLifecycleEvent,
  formatMcpSlowToast
};
//# sourceMappingURL=chunk-LRO63VNK.js.map