#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  Box_default,
  Text,
  require_react
} from "./chunk-U25OJR4Y.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import {
  __toESM
} from "./chunk-TUK7OWJA.js";

// src/cli/ui/RecordView.tsx
var import_react = __toESM(require_react(), 1);
function RecordView({ rec, compact = false }) {
  const toolArgsMax = compact ? 120 : 200;
  const toolContentMax = compact ? 200 : 400;
  if (rec.role === "user") {
    const content = rec.content.includes("\n") ? rec.content.split("\n").join("\n      ") : rec.content;
    return /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:cyan" }, t("recordView.userPrefix")), /* @__PURE__ */ import_react.default.createElement(Text, null, content));
  }
  if (rec.role === "assistant_final") {
    return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:green" }, t("recordView.assistant")), rec.cost !== void 0 ? /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "  $", rec.cost.toFixed(6)) : null, rec.usage ? /* @__PURE__ */ import_react.default.createElement(CacheBadge, { usage: rec.usage }) : null), rec.content ? /* @__PURE__ */ import_react.default.createElement(Text, null, rec.content) : /* @__PURE__ */ import_react.default.createElement(Text, { dim: true, italic: true }, t("recordView.toolCallOnly")));
  }
  if (rec.role === "tool") {
    return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:yellow" }, t("recordView.toolPrefix"), rec.tool ?? "?", ">"), rec.args ? /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("recordView.argsLabel"), truncate(rec.args, toolArgsMax)) : null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("recordView.resultArrow"), truncate(rec.content, toolContentMax)));
  }
  if (rec.role === "error") {
    return /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:red", bold: true }, t("recordView.error")), /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:red" }, rec.error ?? rec.content));
  }
  if (rec.role === "done" || rec.role === "assistant_delta") {
    return null;
  }
  return /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "[", rec.role, "] ", rec.content));
}
function CacheBadge({ usage }) {
  const hit = usage.prompt_cache_hit_tokens ?? 0;
  const miss = usage.prompt_cache_miss_tokens ?? 0;
  const total = hit + miss;
  if (total === 0) return null;
  const pct = hit / total * 100;
  const color = pct >= 70 ? "ansi:green" : pct >= 40 ? "ansi:yellow" : "ansi:red";
  return /* @__PURE__ */ import_react.default.createElement(Text, null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("recordView.cache")), /* @__PURE__ */ import_react.default.createElement(Text, { color }, pct.toFixed(1), "%"));
}
function truncate(s, max) {
  return s.length <= max ? s : `${s.slice(0, max)}${t("recordView.truncateExtra", { extra: s.length - max })}`;
}

export {
  RecordView
};
//# sourceMappingURL=chunk-7GUPD2RU.js.map