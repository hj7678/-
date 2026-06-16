#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  createParser
} from "./chunk-25T6CVUP.js";
import {
  VERSION
} from "./chunk-XXC2BYTV.js";

// src/mcp/client.ts
import { basename, resolve } from "path";
import { pathToFileURL } from "url";

// src/mcp/types.ts
var MCP_PROTOCOL_VERSION = "2024-11-05";
function isJsonRpcError(msg) {
  return "error" in msg;
}

// src/mcp/client.ts
var McpClient = class {
  transport;
  clientInfo;
  workspaceDir;
  workspaceRoot;
  requestTimeoutMs;
  pending = /* @__PURE__ */ new Map();
  nextId = 1;
  readerStarted = false;
  initialized = false;
  _serverCapabilities = {};
  _serverInfo = { name: "", version: "" };
  _protocolVersion = "";
  _instructions;
  // Progress-token → handler for notifications/progress routing. Tokens
  // are minted per call when the caller supplies an onProgress
  // callback; cleared when the final response lands (or the pending
  // request rejects). No leaks — the `try/finally` in callTool
  // guarantees cleanup even on timeout.
  progressHandlers = /* @__PURE__ */ new Map();
  nextProgressToken = 1;
  constructor(opts) {
    this.transport = opts.transport;
    this.clientInfo = opts.clientInfo ?? { name: "reasonix", version: VERSION };
    const workspaceDir = opts.workspaceDir?.trim();
    if (workspaceDir) {
      this.workspaceDir = resolve(workspaceDir);
      this.workspaceRoot = {
        uri: pathToFileURL(this.workspaceDir).href,
        name: basename(this.workspaceDir) || this.workspaceDir
      };
    }
    this.requestTimeoutMs = opts.requestTimeoutMs ?? 6e4;
  }
  /** Server's advertised capabilities, available after initialize(). */
  get serverCapabilities() {
    return this._serverCapabilities;
  }
  /** Server's self-reported name + version, available after initialize(). */
  get serverInfo() {
    return this._serverInfo;
  }
  /** Protocol version the server agreed to during the handshake. */
  get protocolVersion() {
    return this._protocolVersion;
  }
  /** Optional free-form instructions the server provides at handshake. */
  get serverInstructions() {
    return this._instructions;
  }
  get workspaceRootDir() {
    return this.workspaceDir;
  }
  /** Compliant servers reject other methods until this completes. */
  async initialize(opts = {}) {
    if (this.initialized) throw new Error("MCP client already initialized");
    this.startReaderIfNeeded();
    const capabilities = {
      tools: {},
      resources: {},
      prompts: {},
      ...this.workspaceRoot ? { roots: {} } : {}
    };
    const params = {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities,
      clientInfo: this.clientInfo
    };
    const result = await this.request("initialize", params, opts.signal);
    this._serverCapabilities = result.capabilities ?? {};
    this._serverInfo = result.serverInfo ?? { name: "", version: "" };
    this._protocolVersion = result.protocolVersion ?? "";
    this._instructions = result.instructions;
    await this.transport.send({
      jsonrpc: "2.0",
      method: "notifications/initialized"
    });
    this.initialized = true;
    return result;
  }
  /** List tools the server exposes. */
  async listTools() {
    this.assertInitialized();
    return this.request("tools/list", {});
  }
  /** Abort sends `notifications/cancelled` and rejects immediately; late server responses are dropped. */
  async callTool(name, args, opts = {}) {
    this.assertInitialized();
    const params = { name, arguments: args ?? {} };
    let token;
    if (opts.onProgress) {
      token = this.nextProgressToken++;
      this.progressHandlers.set(token, opts.onProgress);
      params._meta = { progressToken: token };
    }
    try {
      return await this.request("tools/call", params, opts.signal);
    } finally {
      if (token !== void 0) this.progressHandlers.delete(token);
    }
  }
  /** Throws on method-not-found; callers should gate on `serverCapabilities.resources` first. */
  async listResources(cursor) {
    this.assertInitialized();
    return this.request("resources/list", {
      ...cursor ? { cursor } : {}
    });
  }
  /** Read the contents of a resource by URI. */
  async readResource(uri) {
    this.assertInitialized();
    return this.request("resources/read", {
      uri
    });
  }
  /** List prompt templates the server exposes. */
  async listPrompts(cursor) {
    this.assertInitialized();
    return this.request("prompts/list", {
      ...cursor ? { cursor } : {}
    });
  }
  async getPrompt(name, args) {
    this.assertInitialized();
    return this.request("prompts/get", {
      name,
      ...args ? { arguments: args } : {}
    });
  }
  /** Close the transport and reject any outstanding requests. */
  async close() {
    for (const [, pending] of this.pending) {
      clearTimeout(pending.timeout);
      pending.reject(new Error("MCP client closed"));
    }
    this.pending.clear();
    await this.transport.close();
  }
  assertInitialized() {
    if (!this.initialized) throw new Error("MCP client not initialized \u2014 call initialize() first");
  }
  async request(method, params, signal) {
    const id = this.nextId++;
    const frame = { jsonrpc: "2.0", id, method, params };
    let abortHandler = null;
    const promise = new Promise((resolve2, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        if (abortHandler && signal) signal.removeEventListener("abort", abortHandler);
        reject(
          new Error(`MCP request ${method} (id=${id}) timed out after ${this.requestTimeoutMs}ms`)
        );
      }, this.requestTimeoutMs);
      this.pending.set(id, {
        resolve: resolve2,
        reject,
        timeout
      });
      if (signal) {
        if (signal.aborted) {
          this.pending.delete(id);
          clearTimeout(timeout);
          reject(new Error(`MCP request ${method} (id=${id}) aborted before send`));
          return;
        }
        abortHandler = () => {
          this.pending.delete(id);
          clearTimeout(timeout);
          void this.transport.send({
            jsonrpc: "2.0",
            method: "notifications/cancelled",
            params: { requestId: id, reason: "aborted by user" }
          }).catch(() => {
          });
          reject(new Error(`MCP request ${method} (id=${id}) aborted by user`));
        };
        signal.addEventListener("abort", abortHandler, { once: true });
      }
    });
    promise.catch(() => void 0);
    const promiseSettled = promise.then(
      () => void 0,
      () => void 0
    );
    try {
      await Promise.race([this.transport.send(frame), promiseSettled]);
    } catch (err) {
      const pending = this.pending.get(id);
      if (pending) clearTimeout(pending.timeout);
      this.pending.delete(id);
      if (abortHandler && signal) signal.removeEventListener("abort", abortHandler);
      throw err;
    }
    try {
      return await promise;
    } finally {
      if (abortHandler && signal) signal.removeEventListener("abort", abortHandler);
    }
  }
  startReaderIfNeeded() {
    if (this.readerStarted) return;
    this.readerStarted = true;
    void this.readLoop();
  }
  async readLoop() {
    try {
      for await (const msg of this.transport.messages()) {
        this.dispatch(msg);
      }
    } catch (err) {
      for (const [, pending] of this.pending) {
        clearTimeout(pending.timeout);
        pending.reject(err);
      }
      this.pending.clear();
    }
  }
  dispatch(msg) {
    if (!("id" in msg) || msg.id === null || msg.id === void 0) {
      if ("method" in msg && msg.method === "notifications/progress") {
        const p = msg.params;
        if (!p || p.progressToken === void 0) return;
        const handler = this.progressHandlers.get(p.progressToken);
        if (!handler) return;
        handler({ progress: p.progress, total: p.total, message: p.message });
      }
      return;
    }
    if (!("result" in msg) && !("error" in msg)) {
      this.handleServerRequest(msg);
      return;
    }
    const pending = this.pending.get(msg.id);
    if (!pending) return;
    this.pending.delete(msg.id);
    clearTimeout(pending.timeout);
    const resp = msg;
    if (isJsonRpcError(resp)) {
      pending.reject(new Error(`MCP ${resp.error.code}: ${resp.error.message}`));
    } else {
      pending.resolve(resp.result);
    }
  }
  handleServerRequest(req) {
    if (req.method === "roots/list" && this.workspaceRoot) {
      void this.transport.send({
        jsonrpc: "2.0",
        id: req.id,
        result: { roots: [this.workspaceRoot] }
      }).catch(() => void 0);
      return;
    }
    void this.transport.send({
      jsonrpc: "2.0",
      id: req.id,
      error: { code: -32601, message: `method not found: ${req.method}` }
    }).catch(() => void 0);
  }
};

// src/mcp/inspect.ts
async function inspectMcpServer(client) {
  const t0 = Date.now();
  const tools = await trySection(() => client.listTools().then((r) => r.tools));
  const resources = await trySection(
    () => client.listResources().then((r) => r.resources)
  );
  const prompts = await trySection(() => client.listPrompts().then((r) => r.prompts));
  return {
    protocolVersion: client.protocolVersion || "(unknown)",
    serverInfo: client.serverInfo,
    capabilities: client.serverCapabilities ?? {},
    instructions: client.serverInstructions,
    tools,
    resources,
    prompts,
    elapsedMs: Date.now() - t0
  };
}
async function trySection(load) {
  try {
    const items = await load();
    return { supported: true, items };
  } catch (err) {
    const msg = err.message ?? String(err);
    if (/-32601/.test(msg) || /method not found/i.test(msg)) {
      return { supported: false, reason: "method not found (-32601)" };
    }
    return { supported: false, reason: msg };
  }
}

// src/mcp/stdio.ts
import { spawn } from "child_process";
var StdioTransport = class {
  child;
  queue = [];
  waiters = [];
  closed = false;
  stdoutBuffer = "";
  constructor(opts) {
    const env = opts.replaceEnv ? { ...opts.env ?? {} } : { ...process.env, ...opts.env ?? {} };
    const shell = opts.shell ?? process.platform === "win32";
    if (shell) {
      const line = [
        opts.command,
        ...(opts.args ?? []).map((a) => quoteArg(a, process.platform === "win32"))
      ].join(" ");
      this.child = spawn(line, [], {
        env,
        cwd: opts.cwd,
        stdio: ["pipe", "pipe", "pipe"],
        shell: true
      });
    } else {
      this.child = spawn(opts.command, opts.args ?? [], {
        env,
        cwd: opts.cwd,
        stdio: ["pipe", "pipe", "pipe"]
      });
    }
    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk) => this.onStdout(chunk));
    this.child.stderr.setEncoding("utf8");
    this.child.stderr.on("data", (chunk) => this.onStderr(chunk));
    this.child.on("close", () => this.onClose());
    this.child.on("error", (err) => {
      this.push({
        jsonrpc: "2.0",
        id: null,
        error: { code: -32e3, message: `transport error: ${err.message}` }
      });
    });
  }
  async send(message) {
    if (this.closed) throw new Error("MCP transport is closed");
    return new Promise((resolve2, reject) => {
      const line = `${JSON.stringify(message)}
`;
      this.child.stdin.write(line, "utf8", (err) => {
        if (err) reject(err);
        else resolve2();
      });
    });
  }
  async *messages() {
    while (true) {
      if (this.queue.length > 0) {
        yield this.queue.shift();
        continue;
      }
      if (this.closed) return;
      const next = await new Promise((resolve2) => {
        this.waiters.push(resolve2);
      });
      if (next === null) return;
      yield next;
    }
  }
  async close() {
    if (this.closed) return;
    this.closed = true;
    while (this.waiters.length > 0) this.waiters.shift()(null);
    try {
      this.child.stdin.end();
    } catch {
    }
    if (this.child.exitCode === null && !this.child.killed) {
      try {
        this.child.kill(process.platform === "win32" ? void 0 : "SIGTERM");
      } catch {
      }
    }
  }
  /** Parse incoming stdout chunks into NDJSON messages. */
  onStdout(chunk) {
    this.stdoutBuffer += chunk;
    let newlineIdx;
    while ((newlineIdx = this.stdoutBuffer.indexOf("\n")) !== -1) {
      const line = this.stdoutBuffer.slice(0, newlineIdx).trim();
      this.stdoutBuffer = this.stdoutBuffer.slice(newlineIdx + 1);
      if (!line) continue;
      try {
        const msg = JSON.parse(line);
        this.push(msg);
      } catch {
        if (process.env.REASONIX_DEBUG_MCP === "1") {
          process.stderr.write(`[mcp-stdio] dropped malformed line: ${line}
`);
        }
      }
    }
  }
  // Python MCP SDK writes info logs (`server.py:534 ListPromptsRequest`)
  // to stderr — letting those through would corrupt the TUI render.
  onStderr(chunk) {
    if (process.env.REASONIX_DEBUG_MCP === "1") {
      process.stderr.write(chunk);
    }
  }
  onClose() {
    this.closed = true;
    while (this.waiters.length > 0) this.waiters.shift()(null);
  }
  push(msg) {
    const waiter = this.waiters.shift();
    if (waiter) waiter(msg);
    else this.queue.push(msg);
  }
};
function quoteArg(s, windows) {
  if (!windows) {
    return `'${s.replace(/'/g, "'\\''")}'`;
  }
  return `"${s.replace(/"/g, '""')}"`;
}

// src/mcp/sse.ts
var SseTransport = class {
  url;
  headers;
  queue = [];
  waiters = [];
  controller = new AbortController();
  closed = false;
  postUrl = null;
  endpointReady;
  resolveEndpoint;
  rejectEndpoint;
  constructor(opts) {
    this.url = opts.url;
    this.headers = opts.headers ?? {};
    this.endpointReady = new Promise((resolve2, reject) => {
      this.resolveEndpoint = resolve2;
      this.rejectEndpoint = reject;
    });
    this.endpointReady.catch(() => void 0);
    void this.runStream();
  }
  async send(message) {
    if (this.closed) throw new Error("MCP SSE transport is closed");
    const postUrl = await this.endpointReady;
    const res = await fetch(postUrl, {
      method: "POST",
      headers: { "content-type": "application/json", ...this.headers },
      body: JSON.stringify(message),
      signal: this.controller.signal
    });
    await res.arrayBuffer().catch(() => void 0);
    if (!res.ok) {
      throw new Error(`MCP SSE POST ${postUrl} failed: ${res.status} ${res.statusText}`);
    }
  }
  async *messages() {
    while (true) {
      if (this.queue.length > 0) {
        yield this.queue.shift();
        continue;
      }
      if (this.closed) return;
      const next = await new Promise((resolve2) => {
        this.waiters.push(resolve2);
      });
      if (next === null) return;
      yield next;
    }
  }
  async close() {
    if (this.closed) return;
    this.closed = true;
    while (this.waiters.length > 0) this.waiters.shift()(null);
    this.rejectEndpoint(new Error("MCP SSE transport closed before endpoint was ready"));
    try {
      this.controller.abort();
    } catch {
    }
  }
  async runStream() {
    let res;
    try {
      res = await fetch(this.url, {
        method: "GET",
        headers: { accept: "text/event-stream", ...this.headers },
        signal: this.controller.signal
      });
    } catch (err) {
      this.failHandshake(`SSE connect to ${this.url} failed: ${err.message}`);
      return;
    }
    if (!res.ok || !res.body) {
      await res.body?.cancel().catch(() => void 0);
      this.failHandshake(`SSE handshake ${this.url} \u2192 ${res.status} ${res.statusText}`);
      return;
    }
    const parser = createParser({
      onEvent: (ev) => this.handleEvent(ev.event ?? "message", ev.data)
    });
    const decoder = new TextDecoder();
    try {
      for await (const chunk of res.body) {
        parser.feed(decoder.decode(chunk, { stream: true }));
      }
    } catch (err) {
      if (!this.closed) {
        this.pushError(`SSE stream error: ${err.message}`);
      }
    } finally {
      this.markClosed();
    }
  }
  handleEvent(type, data) {
    if (type === "endpoint") {
      if (this.postUrl) return;
      try {
        this.postUrl = new URL(data, this.url).toString();
        this.resolveEndpoint(this.postUrl);
      } catch (err) {
        this.failHandshake(`SSE endpoint event had bad URL "${data}": ${err.message}`);
      }
      return;
    }
    if (type === "message") {
      try {
        const parsed = JSON.parse(data);
        this.pushMessage(parsed);
      } catch {
      }
      return;
    }
  }
  failHandshake(reason) {
    this.rejectEndpoint(new Error(reason));
    this.pushError(reason);
    this.markClosed();
  }
  pushMessage(msg) {
    const waiter = this.waiters.shift();
    if (waiter) waiter(msg);
    else this.queue.push(msg);
  }
  pushError(message) {
    this.pushMessage({
      jsonrpc: "2.0",
      id: null,
      error: { code: -32e3, message }
    });
  }
  markClosed() {
    if (this.closed) return;
    this.closed = true;
    while (this.waiters.length > 0) this.waiters.shift()(null);
  }
};

// src/mcp/streamable-http.ts
var SESSION_HEADER = "mcp-session-id";
var StreamableHttpTransport = class {
  url;
  extraHeaders;
  queue = [];
  waiters = [];
  controller = new AbortController();
  /** Session id minted by server on (typically) the initialize response. */
  sessionId = null;
  closed = false;
  /** Background SSE read-loops kicked off by send(); awaited on close(). */
  streams = /* @__PURE__ */ new Set();
  constructor(opts) {
    this.url = opts.url;
    this.extraHeaders = opts.headers ?? {};
  }
  async send(message) {
    if (this.closed) throw new Error("MCP Streamable HTTP transport is closed");
    const headers = {
      "content-type": "application/json",
      // Both accepted — server picks. application/json first signals a
      // mild preference for the simpler shape when the response is a
      // single message.
      accept: "application/json, text/event-stream",
      ...this.extraHeaders
    };
    if (this.sessionId !== null) headers["mcp-session-id"] = this.sessionId;
    let res;
    try {
      res = await fetch(this.url, {
        method: "POST",
        headers,
        body: JSON.stringify(message),
        signal: this.controller.signal
      });
    } catch (err) {
      throw new Error(`MCP Streamable HTTP POST ${this.url} failed: ${err.message}`);
    }
    const serverSessionId = res.headers.get(SESSION_HEADER);
    if (serverSessionId && this.sessionId === null) {
      this.sessionId = serverSessionId;
    }
    if (res.status === 404 && this.sessionId !== null) {
      await res.body?.cancel().catch(() => void 0);
      throw new Error(
        `MCP Streamable HTTP session expired (server returned 404 with Mcp-Session-Id "${this.sessionId}"). Reinitialize the client.`
      );
    }
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(
        `MCP Streamable HTTP POST ${this.url} \u2192 ${res.status} ${res.statusText}${body ? `: ${body}` : ""}`
      );
    }
    if (res.status === 202) {
      await res.body?.cancel().catch(() => void 0);
      return;
    }
    const ct = (res.headers.get("content-type") ?? "").toLowerCase();
    if (ct.includes("application/json")) {
      let parsed;
      try {
        parsed = await res.json();
      } catch (err) {
        throw new Error(`MCP Streamable HTTP body wasn't valid JSON: ${err.message}`);
      }
      if (Array.isArray(parsed)) {
        for (const item of parsed) this.pushMessage(item);
      } else {
        this.pushMessage(parsed);
      }
      return;
    }
    if (ct.includes("text/event-stream")) {
      if (!res.body) {
        throw new Error("MCP Streamable HTTP SSE response had no body");
      }
      const stream = this.consumeStream(res.body);
      this.streams.add(stream);
      stream.finally(() => this.streams.delete(stream));
      return;
    }
    await res.body?.cancel().catch(() => void 0);
  }
  async *messages() {
    while (true) {
      if (this.queue.length > 0) {
        yield this.queue.shift();
        continue;
      }
      if (this.closed) return;
      const next = await new Promise((resolve2) => {
        this.waiters.push(resolve2);
      });
      if (next === null) return;
      yield next;
    }
  }
  async close() {
    if (this.closed) return;
    this.closed = true;
    while (this.waiters.length > 0) this.waiters.shift()(null);
    try {
      this.controller.abort();
    } catch {
    }
    await Promise.allSettled(Array.from(this.streams));
  }
  /** Visible for tests — confirm session header round-trip. */
  getSessionId() {
    return this.sessionId;
  }
  async consumeStream(body) {
    const parser = createParser({
      onEvent: (ev) => {
        const type = ev.event ?? "message";
        if (type !== "message") return;
        try {
          const parsed = JSON.parse(ev.data);
          this.pushMessage(parsed);
        } catch {
        }
      }
    });
    const decoder = new TextDecoder();
    try {
      for await (const chunk of body) {
        if (this.closed) break;
        parser.feed(decoder.decode(chunk, { stream: true }));
      }
    } catch (err) {
      if (!this.closed) {
        this.pushMessage({
          jsonrpc: "2.0",
          id: null,
          error: {
            code: -32e3,
            message: `Streamable HTTP stream error: ${err.message}`
          }
        });
      }
    }
  }
  pushMessage(msg) {
    const waiter = this.waiters.shift();
    if (waiter) waiter(msg);
    else this.queue.push(msg);
  }
};

export {
  McpClient,
  StdioTransport,
  SseTransport,
  StreamableHttpTransport,
  inspectMcpServer
};
//# sourceMappingURL=chunk-4SBXAHR6.js.map