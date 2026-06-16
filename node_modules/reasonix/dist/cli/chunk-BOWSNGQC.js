#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  LruCache
} from "./chunk-6UNHNVJR.js";

// src/tokenizer.ts
import { existsSync, readFileSync } from "fs";
import { createRequire } from "module";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { gunzipSync } from "zlib";
function buildByteToChar() {
  const result = new Array(256);
  const bs = [];
  for (let b = 33; b <= 126; b++) bs.push(b);
  for (let b = 161; b <= 172; b++) bs.push(b);
  for (let b = 174; b <= 255; b++) bs.push(b);
  const cs = bs.slice();
  let n = 0;
  for (let b = 0; b < 256; b++) {
    if (!bs.includes(b)) {
      bs.push(b);
      cs.push(256 + n);
      n++;
    }
  }
  for (let i = 0; i < bs.length; i++) {
    result[bs[i]] = String.fromCodePoint(cs[i]);
  }
  return result;
}
var cached = null;
function resolveDataPath() {
  if (process.env.REASONIX_TOKENIZER_PATH) return process.env.REASONIX_TOKENIZER_PATH;
  const candidates = [];
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    candidates.push(join(here, "..", "data", "deepseek-tokenizer.json.gz"));
    candidates.push(join(here, "..", "..", "data", "deepseek-tokenizer.json.gz"));
  } catch {
  }
  try {
    const req = createRequire(import.meta.url);
    candidates.push(
      join(dirname(req.resolve("reasonix/package.json")), "data", "deepseek-tokenizer.json.gz")
    );
  } catch {
  }
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return candidates[0] ?? join(process.cwd(), "data", "deepseek-tokenizer.json.gz");
}
function loadTokenizer() {
  if (cached) return cached;
  const buf = readFileSync(resolveDataPath());
  const json = gunzipSync(buf).toString("utf8");
  const data = JSON.parse(json);
  const mergeRank = /* @__PURE__ */ new Map();
  for (let i = 0; i < data.model.merges.length; i++) {
    mergeRank.set(data.model.merges[i], i);
  }
  const splitRegexes = [];
  for (const p of data.pre_tokenizer.pretokenizers) {
    if (p.type === "Split") {
      splitRegexes.push(new RegExp(p.pattern.Regex, "gu"));
    }
  }
  const addedMap = /* @__PURE__ */ new Map();
  const addedContents = [];
  for (const t of data.added_tokens) {
    if (!t.special) {
      addedMap.set(t.content, t.id);
      addedContents.push(t.content);
    }
  }
  addedContents.sort((a, b) => b.length - a.length);
  const addedPattern = addedContents.length ? new RegExp(addedContents.map(escapeRegex).join("|"), "g") : null;
  cached = {
    vocab: data.model.vocab,
    mergeRank,
    splitRegexes,
    byteToChar: buildByteToChar(),
    addedPattern,
    addedMap
  };
  return cached;
}
function warmupTokenizer() {
  loadTokenizer();
}
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function applySplit(chunks, re) {
  const out = [];
  for (const chunk of chunks) {
    if (!chunk) continue;
    re.lastIndex = 0;
    let last = 0;
    for (const m of chunk.matchAll(re)) {
      const idx = m.index ?? 0;
      if (idx > last) out.push(chunk.slice(last, idx));
      if (m[0].length > 0) out.push(m[0]);
      last = idx + m[0].length;
    }
    if (last < chunk.length) out.push(chunk.slice(last));
  }
  return out;
}
function byteLevelEncode(s, byteToChar) {
  const bytes = new TextEncoder().encode(s);
  let out = "";
  for (let i = 0; i < bytes.length; i++) out += byteToChar[bytes[i]];
  return out;
}
var bpeCache = new LruCache(8192);
function bpeEncode(piece, mergeRank) {
  if (piece.length <= 1) return piece ? [piece] : [];
  const cached2 = bpeCache.get(piece);
  if (cached2 !== void 0) return cached2;
  const word = Array.from(piece);
  while (word.length > 1) {
    let bestIdx = -1;
    let bestRank = Number.POSITIVE_INFINITY;
    for (let i = 0; i < word.length - 1; i++) {
      const pair = `${word[i]} ${word[i + 1]}`;
      const rank = mergeRank.get(pair);
      if (rank !== void 0 && rank < bestRank) {
        bestRank = rank;
        bestIdx = i;
        if (rank === 0) break;
      }
    }
    if (bestIdx < 0) break;
    word.splice(bestIdx, 2, word[bestIdx] + word[bestIdx + 1]);
  }
  bpeCache.set(piece, word);
  return word;
}
function encode(text) {
  if (!text) return [];
  const t = loadTokenizer();
  const ids = [];
  const process2 = (segment) => {
    if (!segment) return;
    let chunks = [segment];
    for (const re of t.splitRegexes) chunks = applySplit(chunks, re);
    for (const chunk of chunks) {
      if (!chunk) continue;
      const byteLevel = byteLevelEncode(chunk, t.byteToChar);
      const pieces = bpeEncode(byteLevel, t.mergeRank);
      for (const p of pieces) {
        const id = t.vocab[p];
        if (id !== void 0) ids.push(id);
      }
    }
  };
  if (t.addedPattern) {
    t.addedPattern.lastIndex = 0;
    let last = 0;
    for (const m of text.matchAll(t.addedPattern)) {
      const idx = m.index ?? 0;
      if (idx > last) process2(text.slice(last, idx));
      const id = t.addedMap.get(m[0]);
      if (id !== void 0) ids.push(id);
      last = idx + m[0].length;
    }
    if (last < text.length) process2(text.slice(last));
  } else {
    process2(text);
  }
  return ids;
}
function countTokens(text) {
  return encode(text).length;
}
var DEFAULT_BOUNDED_TOKENIZE_CHARS = 2 * 1024;
function countTokensBounded(text, maxChars = DEFAULT_BOUNDED_TOKENIZE_CHARS) {
  if (text.length === 0) return 0;
  const cap = Math.floor(maxChars);
  if (cap > 0 && text.length <= cap) return countTokens(text);
  if (cap <= 0) return Math.max(1, Math.ceil(text.length * 0.3));
  const headChars = Math.ceil(cap / 2);
  const tailChars = Math.floor(cap / 2);
  const head = text.slice(0, headChars);
  const tail = tailChars > 0 ? text.slice(-tailChars) : "";
  const sampleChars = head.length + tail.length;
  const sampleTokens = countTokens(head) + countTokens(tail);
  const ratio = sampleChars > 0 ? sampleTokens / sampleChars : 0.3;
  return Math.max(1, Math.ceil(text.length * ratio));
}
var THINK_START = "<think>";
var THINK_END = "</think>";
var DSML = "\uFF5CDSML\uFF5C";
var TC_BEGIN = `<${DSML}tool_calls>`;
var TC_END = `</${DSML}tool_calls>`;
var INVOKE_BEGIN = `<${DSML}invoke name="`;
var INVOKE_END = `</${DSML}invoke>`;
var PARAM_TEMPLATE = `<${DSML}parameter name="{key}" string="{is_str}">{value}</${DSML}parameter>`;
var toolsTemplateCache = /* @__PURE__ */ new WeakMap();
function renderTools(tools) {
  const cached2 = toolsTemplateCache.get(tools);
  if (cached2 !== void 0) return cached2;
  const schemas = tools.map((t) => {
    const fn = t.function ?? t;
    return JSON.stringify(fn);
  }).join("\n");
  const rendered = `## Tools

You have access to a set of tools to help answer the user's question. You can invoke tools by writing a "<${DSML}tool_calls>" block like the following:

<${DSML}tool_calls>
<${DSML}invoke name="$TOOL_NAME">
<${DSML}parameter name="$PARAMETER_NAME" string="true|false">$PARAMETER_VALUE</${DSML}parameter>
...
</${DSML}invoke>
<${DSML}invoke name="$TOOL_NAME2">
...
</${DSML}invoke>
</${DSML}tool_calls>

String parameters should be specified as is and set \`string="true"\`. For all other types (numbers, booleans, arrays, objects), pass the value in JSON format and set \`string="false"\`.

If thinking_mode is enabled (triggered by ${THINK_START}), you MUST output your complete reasoning inside ${THINK_START}...${THINK_END} BEFORE any tool calls or final response.

Otherwise, output directly after ${THINK_END} with tool calls or final response.

### Available Tool Schemas

${schemas}

You MUST strictly follow the above defined tool name and parameter schemas to invoke tool calls.`;
  toolsTemplateCache.set(tools, rendered);
  return rendered;
}
var PER_MESSAGE_TEMPLATE_TOKENS = 6;
var contentTokenCache = new LruCache(4096);
function cachedBoundedTokens(s) {
  if (s.length === 0) return 0;
  const cached2 = contentTokenCache.get(s);
  if (cached2 !== void 0) return cached2;
  const n = countTokensBounded(s);
  contentTokenCache.set(s, n);
  return n;
}
function tokensForMessage(m, dropThisReasoning) {
  let n = 0;
  if (typeof m.content === "string" && m.content.length > 0) {
    n += cachedBoundedTokens(m.content);
  }
  if (m.role === "assistant") {
    if (!dropThisReasoning && typeof m.reasoning_content === "string" && m.reasoning_content.length > 0) {
      n += cachedBoundedTokens(m.reasoning_content);
    }
    const tcs = m.tool_calls;
    if (Array.isArray(tcs) && tcs.length > 0) {
      n += cachedBoundedTokens(JSON.stringify(tcs));
    }
  }
  return n;
}
function estimateConversationTokens(messages, drop_thinking = false) {
  if (messages.length === 0) return 0;
  let lastUserOrDev = -1;
  if (drop_thinking) {
    for (let i = messages.length - 1; i >= 0; i--) {
      const r = messages[i].role;
      if (r === "user" || r === "developer") {
        lastUserOrDev = i;
        break;
      }
    }
  }
  let total = 2;
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (drop_thinking && i < lastUserOrDev && m.role === "developer") continue;
    total += PER_MESSAGE_TEMPLATE_TOKENS;
    const dropReasoning = drop_thinking && i < lastUserOrDev && m.role === "assistant";
    total += tokensForMessage(m, dropReasoning);
  }
  return total;
}
function estimateRequestTokens(messages, toolSpecs, drop_thinking = false) {
  let total = estimateConversationTokens(messages, drop_thinking);
  if (toolSpecs && toolSpecs.length > 0) {
    total += countTokensBounded(renderTools(toolSpecs));
  }
  return total;
}

export {
  resolveDataPath,
  warmupTokenizer,
  countTokens,
  countTokensBounded,
  estimateRequestTokens
};
//# sourceMappingURL=chunk-BOWSNGQC.js.map