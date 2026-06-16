#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  ignoredByLayers,
  loadGitignoreAt
} from "./chunk-6UNHNVJR.js";
import {
  compileFilters,
  defaultIndexConfig,
  resolveSemanticEmbeddingConfig
} from "./chunk-GCNBIWK7.js";

// src/index/semantic/builder.ts
import { promises as fs3 } from "fs";
import path3 from "path";

// src/index/semantic/chunker.ts
import { promises as fs } from "fs";
import path from "path";
var DEFAULT_MAX_CHUNK_CHARS = 4e3;
function chunkText(text, filePath, windowLines, overlap, maxChunkChars = DEFAULT_MAX_CHUNK_CHARS) {
  const lines = text.split(/\r?\n/);
  if (lines.length === 0 || lines.length === 1 && lines[0] === "") return [];
  const stride = Math.max(1, windowLines - overlap);
  const chunks = [];
  for (let start = 0; start < lines.length; start += stride) {
    const end = Math.min(lines.length, start + windowLines);
    const slice = lines.slice(start, end).join("\n").trim();
    if (slice.length === 0) {
      if (end >= lines.length) break;
      continue;
    }
    const window = {
      path: filePath,
      startLine: start + 1,
      endLine: end,
      text: slice
    };
    for (const sub of safeSplit(window, maxChunkChars)) chunks.push(sub);
    if (end >= lines.length) break;
  }
  return chunks;
}
function safeSplit(chunk, maxChars) {
  if (chunk.text.length <= maxChars) return [chunk];
  const lines = chunk.text.split("\n");
  const out = [];
  let bufLines = [];
  let bufStart = chunk.startLine;
  let bufLen = 0;
  const flush = (untilLineNo) => {
    if (bufLines.length === 0) return;
    out.push({
      path: chunk.path,
      startLine: bufStart,
      endLine: untilLineNo,
      text: bufLines.join("\n")
    });
    bufLines = [];
    bufLen = 0;
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";
    const lineLen = line.length + 1;
    if (lineLen > maxChars) {
      flush(chunk.startLine + i - 1);
      out.push({
        path: chunk.path,
        startLine: chunk.startLine + i,
        endLine: chunk.startLine + i,
        text: line.slice(0, maxChars)
      });
      bufStart = chunk.startLine + i + 1;
      continue;
    }
    if (bufLen + lineLen > maxChars && bufLines.length > 0) {
      flush(chunk.startLine + i - 1);
      bufStart = chunk.startLine + i;
    }
    bufLines.push(line);
    bufLen += lineLen;
  }
  flush(chunk.endLine);
  return out;
}
function toForwardRel(root, abs) {
  return path.relative(root, abs).split(path.sep).join("/");
}
async function* walkChunks(root, opts = {}) {
  const windowLines = opts.windowLines ?? 60;
  const overlap = Math.min(opts.overlap ?? 12, Math.max(0, windowLines - 1));
  const maxChunkChars = opts.maxChunkChars ?? DEFAULT_MAX_CHUNK_CHARS;
  const filters = compileFilters(opts.config ?? defaultIndexConfig());
  const onSkip = opts.onSkip ?? (() => {
  });
  const initial = [];
  if (filters.respectGitignore) {
    const rootIg = await loadGitignoreAt(root);
    if (rootIg) initial.push({ dirAbs: root, ig: rootIg });
  }
  const stack = [{ dir: root, layers: initial }];
  while (stack.length > 0) {
    const frame = stack.pop();
    if (!frame) break;
    const { dir, layers } = frame;
    let entries;
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const name = entry.name;
      const abs = path.join(dir, name);
      const rel = toForwardRel(root, abs);
      if (entry.isDirectory()) {
        if (filters.dirSet.has(name)) {
          onSkip(rel, "defaultDir");
          continue;
        }
        if (filters.respectGitignore && ignoredByLayers(layers, abs, true)) {
          onSkip(rel, "gitignore");
          continue;
        }
        if (filters.patternMatch(`${rel}/`) || filters.patternMatch(rel)) {
          onSkip(rel, "pattern");
          continue;
        }
        const childLayers = filters.respectGitignore ? await extendLayers(layers, abs) : layers;
        stack.push({ dir: abs, layers: childLayers });
        continue;
      }
      if (!entry.isFile()) continue;
      if (filters.fileSet.has(name)) {
        onSkip(rel, "defaultFile");
        continue;
      }
      const ext = path.extname(name).toLowerCase();
      if (filters.extSet.has(ext)) {
        onSkip(rel, "binaryExt");
        continue;
      }
      if (filters.respectGitignore && ignoredByLayers(layers, abs, false)) {
        onSkip(rel, "gitignore");
        continue;
      }
      if (filters.patternMatch(rel)) {
        onSkip(rel, "pattern");
        continue;
      }
      const result = await readSizeBoundedFile(abs, filters.maxFileBytes);
      if (result.kind === "skip") {
        onSkip(rel, result.reason);
        continue;
      }
      const text = result.text;
      if (text.indexOf("\0") !== -1) {
        onSkip(rel, "binaryContent");
        continue;
      }
      for (const chunk of chunkText(text, rel, windowLines, overlap, maxChunkChars)) {
        yield chunk;
      }
    }
  }
}
async function extendLayers(layers, dirAbs) {
  const ig = await loadGitignoreAt(dirAbs);
  return ig ? [...layers, { dirAbs, ig }] : layers;
}
async function readSizeBoundedFile(abs, maxBytes) {
  try {
    const fh = await fs.open(abs, "r");
    try {
      const stat = await fh.stat();
      if (stat.size > maxBytes) return { kind: "skip", reason: "tooLarge" };
      return { kind: "ok", text: await fh.readFile("utf8") };
    } finally {
      await fh.close();
    }
  } catch {
    return { kind: "skip", reason: "readError" };
  }
}

// src/index/semantic/embedding.ts
var DEFAULT_OLLAMA_URL = "http://localhost:11434";
var DEFAULT_EMBED_MODEL = "nomic-embed-text";
var DEFAULT_TIMEOUT_MS = 18e4;
var DEFAULT_BATCH_SIZE = 10;
var EmbeddingError = class extends Error {
  constructor(message, cause) {
    super(message);
    this.cause = cause;
    this.name = "EmbeddingError";
  }
  cause;
};
async function embed(text, opts = {}) {
  if (opts.provider === "openai-compat") return await embedOpenAICompat(text, opts);
  return await embedOllama(text, opts);
}
async function embedAll(texts, opts = {}) {
  if (opts.provider === "openai-compat") return await embedAllOpenAICompat(texts, opts);
  const out = [];
  for (let i = 0; i < texts.length; i++) {
    if (opts.signal?.aborted) throw new EmbeddingError("embedding aborted");
    const text = texts[i];
    if (text === void 0) continue;
    try {
      out.push(await embed(text, opts));
    } catch (err) {
      if (isAbortError(err) || opts.signal?.aborted) {
        throw new EmbeddingError("embedding aborted", err);
      }
      opts.onError?.(i, err);
      out.push(null);
    }
    opts.onProgress?.(i + 1, texts.length);
  }
  return out;
}
async function probeOllama(opts = {}) {
  const baseUrl = opts.baseUrl ?? process.env.OLLAMA_URL ?? DEFAULT_OLLAMA_URL;
  try {
    const res = await fetch(`${baseUrl}/api/tags`, { signal: opts.signal });
    if (!res.ok) return { ok: false, error: `Ollama returned ${res.status}` };
    const json = await res.json();
    const models = (json.models ?? []).map((m) => m.name).filter((n) => typeof n === "string");
    return { ok: true, models };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: msg };
  }
}
async function embedOllama(text, opts) {
  const baseUrl = opts.baseUrl ?? process.env.OLLAMA_URL ?? DEFAULT_OLLAMA_URL;
  const model = opts.model ?? process.env.REASONIX_EMBED_MODEL ?? DEFAULT_EMBED_MODEL;
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const { controller, cleanup } = composeAbort(opts.signal, timeoutMs, "embedding timeout");
  let res;
  try {
    res = await fetch(`${baseUrl}/api/embeddings`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ model, prompt: text }),
      signal: controller.signal
    });
  } catch (err) {
    cleanup();
    const msg = err instanceof Error ? err.message : String(err);
    if (/ECONNREFUSED|connect ECONNREFUSED|fetch failed/i.test(msg)) {
      throw new EmbeddingError(
        `Cannot reach Ollama at ${baseUrl}. Install from https://ollama.com, then run \`ollama pull ${model}\` and \`ollama serve\`. Override the URL via OLLAMA_URL.`,
        err
      );
    }
    throw new EmbeddingError(`embedding request failed: ${msg}`, err);
  } finally {
    cleanup();
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    if (res.status === 404 && /model.*not found/i.test(body)) {
      throw new EmbeddingError(
        `Embedding model "${model}" not pulled. Run \`ollama pull ${model}\` once, then retry.`
      );
    }
    throw new EmbeddingError(`Ollama returned ${res.status}: ${body.slice(0, 200)}`);
  }
  const json = await res.json();
  if (!json.embedding || !Array.isArray(json.embedding)) {
    throw new EmbeddingError("Ollama response missing 'embedding' array");
  }
  return toFloat32Array(json.embedding, "embedding");
}
async function embedOpenAICompat(text, opts) {
  const vectors = await requestOpenAICompatEmbeddings(text, opts);
  const v = vectors[0];
  if (!v) {
    throw new EmbeddingError(
      `Embedding provider returned no vector for the input (model ${opts.model})`
    );
  }
  return v;
}
async function embedAllOpenAICompat(texts, opts) {
  if (texts.length === 0) return [];
  if (opts.signal?.aborted) throw new EmbeddingError("embedding aborted");
  const batchSize = opts.batchSize ?? DEFAULT_BATCH_SIZE;
  const result = [];
  let done = 0;
  for (let i = 0; i < texts.length; i += batchSize) {
    if (opts.signal?.aborted) throw new EmbeddingError("embedding aborted");
    const batch = texts.slice(i, i + batchSize);
    const vectors = await requestOpenAICompatEmbeddings([...batch], opts);
    for (let j = 0; j < vectors.length; j++) {
      const idx = i + j;
      if (vectors[j] === null) {
        opts.onError?.(
          idx,
          new EmbeddingError(
            `provider dropped input ${idx} from batch ${Math.floor(i / batchSize) + 1} (model ${opts.model} returned no embedding for it)`
          )
        );
      }
    }
    result.push(...vectors);
    done += vectors.length;
    opts.onProgress?.(done, texts.length);
  }
  return result;
}
async function requestOpenAICompatEmbeddings(input, opts) {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const { controller, cleanup } = composeAbort(opts.signal, timeoutMs, "embedding timeout");
  const url = opts.baseUrl.trim();
  const body = {
    ...opts.extraBody ?? {},
    model: opts.model,
    input,
    encoding_format: "float"
  };
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        authorization: `Bearer ${opts.apiKey}`,
        "content-type": "application/json"
      },
      body: JSON.stringify(body),
      signal: controller.signal
    });
  } catch (err) {
    cleanup();
    if (isAbortError(err) || opts.signal?.aborted) {
      throw new EmbeddingError("embedding aborted", err);
    }
    const msg = err instanceof Error ? err.message : String(err);
    throw new EmbeddingError(`Cannot reach OpenAI-compatible embeddings at ${url}: ${msg}`, err);
  } finally {
    cleanup();
  }
  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    const bodyText = raw.slice(0, 300);
    if (res.status === 401 || res.status === 403) {
      throw new EmbeddingError(
        `OpenAI-compatible API rejected the API key for ${url}. Response ${res.status}: ${bodyText}`
      );
    }
    if (res.status === 404) {
      throw new EmbeddingError(
        `Embeddings endpoint not found at ${url}. Check the configured API URL. Response ${res.status}: ${bodyText}`
      );
    }
    if (res.status === 400) {
      throw new EmbeddingError(
        `Embedding provider returned 400: ${bodyText}. Check model and custom request body fields.`
      );
    }
    throw new EmbeddingError(`OpenAI-compatible API returned ${res.status}: ${bodyText}`);
  }
  const json = await res.json();
  if (!Array.isArray(json.data)) {
    throw new EmbeddingError("OpenAI-compatible response missing 'data' array");
  }
  const size = Array.isArray(input) ? input.length : 1;
  const out = new Array(size).fill(null);
  for (const row of json.data) {
    const rawIndex = row.index;
    if (typeof rawIndex !== "number" || !Number.isInteger(rawIndex) || rawIndex < 0 || rawIndex >= size) {
      throw new EmbeddingError("OpenAI-compatible response returned an invalid embedding index");
    }
    const index = rawIndex;
    if (!Array.isArray(row.embedding)) {
      throw new EmbeddingError(`OpenAI-compatible response missing embedding for index ${index}`);
    }
    out[index] = toFloat32Array(row.embedding, `data[${index}].embedding`);
  }
  return out;
}
function toFloat32Array(values, label) {
  const out = new Float32Array(values.length);
  for (let i = 0; i < values.length; i++) {
    const value = values[i];
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new EmbeddingError(`${label}[${i}] is not a finite number`);
    }
    out[i] = value;
  }
  return out;
}
function composeAbort(signal, timeoutMs, reason) {
  const controller = new AbortController();
  const onCallerAbort = () => controller.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason);
    else signal.addEventListener("abort", onCallerAbort, { once: true });
  }
  const timer = setTimeout(() => controller.abort(new Error(reason)), timeoutMs);
  return {
    controller,
    cleanup: () => {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", onCallerAbort);
    }
  };
}
function isAbortError(err) {
  if (err instanceof Error) {
    if (err.name === "AbortError") return true;
    if (/aborted/i.test(err.message)) return true;
  }
  return false;
}

// src/index/semantic/store.ts
import { promises as fs2 } from "fs";
import path2 from "path";
var STORE_VERSION = 1;
var META_FILE = "index.meta.json";
var DATA_FILE = "index.jsonl";
async function readIndexMeta(indexDir) {
  try {
    const raw = await fs2.readFile(path2.join(indexDir, META_FILE), "utf8");
    return normalizeMeta(JSON.parse(raw));
  } catch {
    return null;
  }
}
function compareIndexIdentity(meta, identity) {
  if (meta.provider !== identity.provider) return "provider";
  if (meta.model !== identity.model) return "model";
  return null;
}
async function wipeStoreFiles(indexDir) {
  await fs2.rm(path2.join(indexDir, DATA_FILE), { force: true });
  await fs2.rm(path2.join(indexDir, META_FILE), { force: true });
}
var SemanticStore = class {
  constructor(indexDir, identity) {
    this.indexDir = indexDir;
    this.identity = identity;
  }
  indexDir;
  identity;
  entries = [];
  byPath = /* @__PURE__ */ new Map();
  dim = 0;
  get provider() {
    return this.identity.provider;
  }
  get model() {
    return this.identity.model;
  }
  get empty() {
    return this.entries.length === 0;
  }
  get size() {
    return this.entries.length;
  }
  get all() {
    return this.entries;
  }
  fileMtimes() {
    const out = /* @__PURE__ */ new Map();
    for (const [p, group] of this.byPath) {
      const first = group[0];
      if (first) out.set(p, first.mtimeMs);
    }
    return out;
  }
  async add(entries) {
    if (entries.length === 0) return;
    if (this.dim === 0) this.dim = entries[0].embedding.length;
    const lines = [];
    for (const e of entries) {
      if (e.embedding.length !== this.dim) {
        throw new Error(
          `embedding dim mismatch: expected ${this.dim}, got ${e.embedding.length} for ${e.path}:${e.startLine}`
        );
      }
      this.entries.push(e);
      const list = this.byPath.get(e.path);
      if (list) list.push(e);
      else this.byPath.set(e.path, [e]);
      lines.push(serializeEntry(e));
    }
    await fs2.mkdir(this.indexDir, { recursive: true });
    await fs2.appendFile(path2.join(this.indexDir, DATA_FILE), `${lines.join("\n")}
`, "utf8");
    await this.writeMeta();
  }
  async remove(paths) {
    if (paths.length === 0) return 0;
    const drop = new Set(paths);
    const before = this.entries.length;
    this.entries = this.entries.filter((e) => !drop.has(e.path));
    for (const p of paths) this.byPath.delete(p);
    const removed = before - this.entries.length;
    if (removed > 0) await this.flush();
    return removed;
  }
  search(query, topK = 8, minScore = 0) {
    if (this.entries.length === 0) return [];
    if (query.length !== this.dim && this.dim !== 0) {
      throw new Error(`query dim ${query.length} \u2260 index dim ${this.dim}`);
    }
    const heap = [];
    for (const entry of this.entries) {
      const score = dot(query, entry.embedding);
      if (score < minScore) continue;
      if (heap.length < topK) {
        heap.push({ entry, score });
        if (heap.length === topK) heap.sort((a, b) => a.score - b.score);
      } else if (score > heap[0].score) {
        heap[0] = { entry, score };
        for (let i = 0; i < heap.length - 1; i++) {
          if (heap[i].score > heap[i + 1].score) {
            const tmp = heap[i];
            heap[i] = heap[i + 1];
            heap[i + 1] = tmp;
          }
        }
      }
    }
    return heap.sort((a, b) => b.score - a.score);
  }
  async flush() {
    await fs2.mkdir(this.indexDir, { recursive: true });
    const tmp = path2.join(this.indexDir, `${DATA_FILE}.tmp`);
    const final = path2.join(this.indexDir, DATA_FILE);
    const lines = this.entries.map(serializeEntry).join("\n");
    await fs2.writeFile(tmp, lines.length > 0 ? `${lines}
` : "", "utf8");
    await fs2.rename(tmp, final);
    await this.writeMeta();
  }
  async writeMeta() {
    const meta = {
      version: STORE_VERSION,
      provider: this.provider,
      model: this.model,
      dim: this.dim,
      updatedAt: (/* @__PURE__ */ new Date()).toISOString()
    };
    await fs2.writeFile(
      path2.join(this.indexDir, META_FILE),
      `${JSON.stringify(meta, null, 2)}
`,
      "utf8"
    );
  }
  async wipe() {
    this.entries = [];
    this.byPath.clear();
    this.dim = 0;
    await wipeStoreFiles(this.indexDir);
  }
};
async function openStore(indexDir, identity) {
  const store = new SemanticStore(indexDir, identity);
  const dataPath = path2.join(indexDir, DATA_FILE);
  const meta = await readIndexMeta(indexDir);
  if (meta) {
    if (meta.version !== STORE_VERSION) {
      throw new Error(
        `Index format version ${meta.version} does not match current ${STORE_VERSION}. Run \`reasonix index --rebuild\`.`
      );
    }
    const mismatch = compareIndexIdentity(meta, identity);
    if (mismatch !== null) {
      throw new Error(
        `Index was built with provider "${meta.provider}" model "${meta.model}" but current config is provider "${identity.provider}" model "${identity.model}". Run \`reasonix index --rebuild\`.`
      );
    }
  }
  let raw;
  try {
    raw = await fs2.readFile(dataPath, "utf8");
  } catch {
    return store;
  }
  for (const line of raw.split("\n")) {
    if (line.length === 0) continue;
    try {
      const entry = deserializeEntry(line);
      store.dim = entry.embedding.length;
      store.entries.push(entry);
      const map = store.byPath;
      const list = map.get(entry.path);
      if (list) list.push(entry);
      else map.set(entry.path, [entry]);
    } catch {
    }
  }
  return store;
}
function normalize(v) {
  let sum = 0;
  for (let i = 0; i < v.length; i++) sum += v[i] * v[i];
  const inv = sum > 0 ? 1 / Math.sqrt(sum) : 0;
  for (let i = 0; i < v.length; i++) v[i] = v[i] * inv;
  return v;
}
function dot(a, b) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}
function serializeEntry(e) {
  const buf = Buffer.from(e.embedding.buffer, e.embedding.byteOffset, e.embedding.byteLength);
  return JSON.stringify({
    p: e.path,
    s: e.startLine,
    e: e.endLine,
    m: e.mtimeMs,
    t: e.text,
    v: buf.toString("base64")
  });
}
function deserializeEntry(line) {
  const parsed = JSON.parse(line);
  const buf = Buffer.from(parsed.v, "base64");
  const embedding = new Float32Array(
    buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)
  );
  return {
    path: parsed.p,
    startLine: parsed.s,
    endLine: parsed.e,
    mtimeMs: parsed.m,
    text: parsed.t,
    embedding: new Float32Array(embedding)
  };
}
function normalizeMeta(meta) {
  return {
    version: typeof meta.version === "number" ? meta.version : STORE_VERSION,
    provider: meta.provider === "openai-compat" ? "openai-compat" : "ollama",
    model: typeof meta.model === "string" ? meta.model : "",
    dim: typeof meta.dim === "number" ? meta.dim : 0,
    updatedAt: typeof meta.updatedAt === "string" ? meta.updatedAt : (/* @__PURE__ */ new Date(0)).toISOString()
  };
}

// src/index/semantic/builder.ts
var INDEX_DIR_NAME = path3.join(".reasonix", "semantic");
function emptyBuckets() {
  return {
    defaultDir: 0,
    defaultFile: 0,
    binaryExt: 0,
    binaryContent: 0,
    tooLarge: 0,
    gitignore: 0,
    pattern: 0,
    readError: 0
  };
}
async function buildIndex(root, opts = {}) {
  const t0 = Date.now();
  const indexDir = path3.join(root, INDEX_DIR_NAME);
  const resolved = resolveBuildEmbeddingConfig(opts);
  opts.onProgress?.({ phase: "setup" });
  throwIfAborted(opts.signal);
  await probeEmbeddingProvider(resolved, opts.signal);
  throwIfAborted(opts.signal);
  if (opts.rebuild) await wipeStoreFiles(indexDir);
  const store = await openStore(indexDir, {
    provider: resolved.provider,
    model: resolved.model
  });
  const lastMtimes = store.fileMtimes();
  const seenPaths = /* @__PURE__ */ new Set();
  const fileChunks = /* @__PURE__ */ new Map();
  let filesScanned = 0;
  let filesSkipped = 0;
  const skipBuckets = emptyBuckets();
  for await (const chunk of walkChunks(root, {
    windowLines: opts.windowLines,
    overlap: opts.overlap,
    config: opts.indexConfig ?? defaultIndexConfig(),
    onSkip: (_p, reason) => {
      skipBuckets[reason]++;
    }
  })) {
    throwIfAborted(opts.signal);
    seenPaths.add(chunk.path);
    let bucket = fileChunks.get(chunk.path);
    if (!bucket) {
      filesScanned++;
      const abs = path3.join(root, chunk.path);
      let mtimeMs = 0;
      try {
        const stat = await fs3.stat(abs);
        mtimeMs = stat.mtimeMs;
      } catch {
        continue;
      }
      const last = lastMtimes.get(chunk.path);
      if (last !== void 0 && last === mtimeMs && !opts.rebuild) {
        filesSkipped++;
        continue;
      }
      bucket = { chunks: [], mtimeMs };
      fileChunks.set(chunk.path, bucket);
    }
    bucket.chunks.push(chunk);
    opts.onProgress?.({ phase: "scan", filesScanned });
  }
  throwIfAborted(opts.signal);
  const deletedPaths = [];
  for (const oldPath of lastMtimes.keys()) {
    if (!seenPaths.has(oldPath)) deletedPaths.push(oldPath);
  }
  const replacePaths = [...fileChunks.keys()].filter((p) => lastMtimes.has(p));
  throwIfAborted(opts.signal);
  const removed = await store.remove([...deletedPaths, ...replacePaths]);
  let chunksAdded = 0;
  let chunksSkipped = 0;
  const filesChanged = fileChunks.size;
  let chunksTotal = 0;
  for (const { chunks } of fileChunks.values()) chunksTotal += chunks.length;
  let chunksDone = 0;
  for (const [, bucket] of fileChunks) {
    throwIfAborted(opts.signal);
    if (bucket.chunks.length === 0) continue;
    const texts = bucket.chunks.map((c) => c.text);
    const vectors = await embedAll(texts, {
      ...resolved,
      signal: opts.signal,
      onProgress: (done, total) => {
        opts.onProgress?.({
          phase: "embed",
          filesScanned,
          filesChanged,
          chunksTotal,
          chunksDone: chunksDone + done
        });
        if (done === total) chunksDone += total;
      },
      onError: (idx, err) => {
        chunksSkipped++;
        const c = bucket.chunks[idx];
        const where = c ? `${c.path}:${c.startLine}-${c.endLine}` : `chunk #${idx}`;
        const msg = err instanceof Error ? err.message : String(err);
        process.stderr.write(`
  ! skipped ${where}: ${msg}
`);
      }
    });
    throwIfAborted(opts.signal);
    const entries = [];
    for (let i = 0; i < bucket.chunks.length; i++) {
      const vec = vectors[i];
      if (!vec) continue;
      const c = bucket.chunks[i];
      if (!c) continue;
      normalize(vec);
      entries.push({
        path: c.path,
        startLine: c.startLine,
        endLine: c.endLine,
        text: c.text,
        embedding: vec,
        mtimeMs: bucket.mtimeMs
      });
    }
    throwIfAborted(opts.signal);
    if (entries.length > 0) await store.add(entries);
    chunksAdded += entries.length;
  }
  throwIfAborted(opts.signal);
  opts.onProgress?.({
    phase: "done",
    filesScanned,
    filesSkipped,
    filesChanged,
    chunksTotal,
    chunksDone,
    skipBuckets
  });
  return {
    filesScanned,
    filesChanged,
    chunksAdded,
    chunksRemoved: removed,
    chunksSkipped,
    skipBuckets,
    durationMs: Date.now() - t0
  };
}
async function querySemantic(root, query, opts = {}) {
  const indexDir = path3.join(root, INDEX_DIR_NAME);
  const resolved = resolveQueryEmbeddingConfig(opts);
  const store = await openStore(indexDir, {
    provider: resolved.provider,
    model: resolved.model
  });
  if (store.empty) return null;
  const qvec = await embed(query, { ...resolved, signal: opts.signal });
  normalize(qvec);
  return store.search(qvec, opts.topK ?? 8, opts.minScore ?? 0.3);
}
async function indexExists(root) {
  const meta = path3.join(root, INDEX_DIR_NAME, "index.meta.json");
  try {
    await fs3.access(meta);
    return true;
  } catch {
    return false;
  }
}
async function indexCompatible(root, opts = {}) {
  const meta = await readIndexMeta(path3.join(root, INDEX_DIR_NAME));
  if (!meta) return false;
  return compareIndexIdentity(meta, resolveIndexIdentity(opts)) === null;
}
function resolveBuildEmbeddingConfig(opts) {
  if (opts.provider === "openai-compat") {
    if (!opts.baseUrl || !opts.apiKey || !opts.model) {
      throw new Error(
        "OpenAI-compatible embeddings require baseUrl, apiKey, and model when passed directly."
      );
    }
    return {
      provider: "openai-compat",
      baseUrl: opts.baseUrl,
      apiKey: opts.apiKey,
      model: opts.model,
      extraBody: opts.extraBody ?? {},
      timeoutMs: opts.timeoutMs ?? 3e4,
      batchSize: opts.batchSize ?? 10
    };
  }
  if (opts.baseUrl || opts.model) {
    return {
      provider: "ollama",
      baseUrl: opts.baseUrl ?? process.env.OLLAMA_URL ?? "http://localhost:11434",
      model: opts.model ?? process.env.REASONIX_EMBED_MODEL ?? "nomic-embed-text",
      timeoutMs: opts.timeoutMs ?? 3e4
    };
  }
  return resolveSemanticEmbeddingConfig(opts.configPath);
}
function resolveIndexIdentity(opts) {
  if (opts.provider && opts.model) {
    return { provider: opts.provider, model: opts.model };
  }
  const resolved = resolveSemanticEmbeddingConfig(opts.configPath);
  return { provider: resolved.provider, model: resolved.model };
}
function resolveQueryEmbeddingConfig(opts) {
  return resolveBuildEmbeddingConfig(opts);
}
async function probeEmbeddingProvider(config, signal) {
  if (config.provider === "openai-compat") return;
  const probe = await probeOllama({ baseUrl: config.baseUrl, signal });
  if (!probe.ok) {
    throw new Error(
      `Ollama is not reachable: ${probe.error}. Install from https://ollama.com, then \`ollama serve\` and \`ollama pull ${config.model}\`.`
    );
  }
}
function throwIfAborted(signal) {
  if (signal?.aborted) {
    throw new Error("semantic indexing aborted");
  }
}

export {
  walkChunks,
  probeOllama,
  readIndexMeta,
  compareIndexIdentity,
  INDEX_DIR_NAME,
  buildIndex,
  querySemantic,
  indexExists,
  indexCompatible
};
//# sourceMappingURL=chunk-I4SH5Z7S.js.map