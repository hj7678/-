#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  Text,
  require_react,
  useStdout
} from "./chunk-U25OJR4Y.js";
import {
  __toESM
} from "./chunk-TUK7OWJA.js";

// src/cli/ui/primitives.tsx
var import_react = __toESM(require_react(), 1);
function ChromeRule() {
  const { stdout } = useStdout();
  const cols = stdout?.columns ?? 80;
  const w = Math.max(20, cols - 2);
  return /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "\u2500".repeat(w));
}
function formatTokens(n) {
  if (n < 1e3) return String(n);
  const k = n / 1e3;
  return k >= 100 ? `${k.toFixed(0)}K` : `${k.toFixed(1)}K`;
}
function Bar({
  ratio,
  color,
  cells = 14,
  dim
}) {
  const filled = Math.max(0, Math.min(cells, Math.round(ratio * cells)));
  return /* @__PURE__ */ import_react.default.createElement(Text, null, /* @__PURE__ */ import_react.default.createElement(Text, { color, dim }, "\u25B0".repeat(filled)), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "\u25B1".repeat(cells - filled)));
}

export {
  ChromeRule,
  formatTokens,
  Bar
};
//# sourceMappingURL=chunk-M4LM5SLT.js.map