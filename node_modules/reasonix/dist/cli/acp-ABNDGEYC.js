#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  buildCodeToolset
} from "./chunk-2WZT27GR.js";
import "./chunk-URAI4YRL.js";
import {
  Eventizer,
  autoResolveVerdict
} from "./chunk-GMQVINZK.js";
import {
  formatMcpLifecycleEvent,
  formatMcpSlowToast
} from "./chunk-LRO63VNK.js";
import {
  buildTransportFromSpec,
  preflightStdioSpec
} from "./chunk-MQJR7YQ2.js";
import {
  CacheFirstLoop,
  ImmutablePrefix,
  bridgeMcpTools,
  errorMeta
} from "./chunk-DFHI2MRB.js";
import {
  McpClient
} from "./chunk-4SBXAHR6.js";
import "./chunk-J26XOB2T.js";
import {
  openTranscriptFile,
  recordFromLoopEvent,
  writeRecord
} from "./chunk-R7JMQMLD.js";
import {
  pauseGate,
  resolveApprovalPrompt,
  toApprovalPrompt,
  toolKindFor
} from "./chunk-4V4TKQMB.js";
import "./chunk-FK7NXDRP.js";
import "./chunk-V4AXMN4X.js";
import {
  codeSystemPrompt
} from "./chunk-XHP6NYOT.js";
import "./chunk-J4MYMBJ7.js";
import "./chunk-PLHAZOLZ.js";
import "./chunk-L3VPEESB.js";
import "./chunk-I4SH5Z7S.js";
import "./chunk-BOWSNGQC.js";
import {
  DeepSeekClient
} from "./chunk-QSKDP3OS.js";
import "./chunk-25T6CVUP.js";
import "./chunk-NVI4XPOQ.js";
import "./chunk-6UNHNVJR.js";
import {
  timestampSuffix
} from "./chunk-P5SUHDUQ.js";
import {
  VERSION
} from "./chunk-XXC2BYTV.js";
import {
  loadDotenv
} from "./chunk-2UQP6H6T.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import {
  DEFAULT_MODEL,
  bridgeEndpointEnv,
  loadEditMode,
  loadEndpoint,
  loadModel,
  loadReasoningEffort,
  normalizeMcpConfig,
  readConfig
} from "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/cli/commands/acp.ts
import { AsyncLocalStorage } from "async_hooks";
import { existsSync, statSync } from "fs";
import { resolve } from "path";

// src/acp/dispatch.ts
function tryParseJson(raw) {
  if (!raw) return void 0;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}
function dispatchKernelEvent(server, sessionId, ev) {
  switch (ev.type) {
    case "model.delta": {
      if (!ev.text) return;
      const variant = ev.channel === "reasoning" ? "agent_thought_chunk" : "agent_message_chunk";
      emit(server, {
        sessionId,
        update: { sessionUpdate: variant, content: { type: "text", text: ev.text } }
      });
      return;
    }
    case "tool.preparing": {
      emit(server, {
        sessionId,
        update: {
          sessionUpdate: "tool_call",
          toolCallId: ev.callId,
          title: ev.name,
          kind: toolKindFor(ev.name),
          status: "pending"
        }
      });
      return;
    }
    case "tool.intent": {
      emit(server, {
        sessionId,
        update: {
          sessionUpdate: "tool_call_update",
          toolCallId: ev.callId,
          status: "in_progress"
        }
      });
      const rawInput = tryParseJson(ev.args);
      if (rawInput !== void 0) {
        emit(server, {
          sessionId,
          update: {
            sessionUpdate: "tool_call",
            toolCallId: ev.callId,
            title: ev.name,
            kind: toolKindFor(ev.name),
            status: "in_progress",
            rawInput
          }
        });
      }
      return;
    }
    case "tool.result": {
      emit(server, {
        sessionId,
        update: {
          sessionUpdate: "tool_call_update",
          toolCallId: ev.callId,
          status: ev.ok ? "completed" : "failed",
          content: [
            {
              type: "content",
              content: { type: "text", text: clip(ev.output) }
            }
          ]
        }
      });
      return;
    }
    case "error": {
      emit(server, {
        sessionId,
        update: {
          sessionUpdate: "agent_message_chunk",
          content: { type: "text", text: `

[error] ${ev.message}` },
          metadata: {
            error: {
              name: ev.name ?? "Error",
              message: ev.message,
              code: ev.code,
              phase: ev.phase,
              retryable: ev.retryable
            }
          }
        }
      });
      return;
    }
    default:
      return;
  }
}
var MAX_RESULT_CHARS = 8e3;
function clip(text) {
  if (text.length <= MAX_RESULT_CHARS) return text;
  return `${text.slice(0, MAX_RESULT_CHARS)}
\u2026(${text.length - MAX_RESULT_CHARS} more chars truncated)`;
}
function emit(server, params) {
  server.sendNotification("session/update", params);
}

// src/acp/gates.ts
function acpPermissionKindFor(prompt) {
  switch (prompt.kind) {
    case "shell":
      return "execute";
    case "path":
      return prompt.data?.intent === "write" ? "edit" : "other";
    default:
      return "other";
  }
}
function acpOptionKindFor(kind) {
  switch (kind) {
    case "allow_once":
      return "allow_once";
    case "allow_always":
      return "allow_always";
    case "reject":
      return "reject_once";
    case "custom":
      return "allow_once";
  }
}
async function requestPermissionForGate(server, sessionId, req) {
  const prompt = toApprovalPrompt(req);
  const params = {
    sessionId,
    toolCall: {
      toolCallId: `gate-${req.id}`,
      title: prompt.title,
      kind: acpPermissionKindFor(prompt),
      status: "pending",
      rawInput: req.payload
    },
    options: prompt.actions.map(
      (a) => ({
        optionId: a.id,
        name: a.label,
        kind: acpOptionKindFor(a.kind)
      })
    )
  };
  let result;
  try {
    result = await server.sendRequest(
      "session/request_permission",
      params
    );
  } catch {
    result = { outcome: { outcome: "cancelled" } };
  }
  if (result.outcome.outcome === "cancelled") {
    return resolveApprovalPrompt(prompt, "");
  }
  return resolveApprovalPrompt(prompt, result.outcome.optionId);
}

// src/acp/protocol.ts
var ACP_PROTOCOL_VERSION = 1;
var ERR_PARSE = -32700;
var ERR_METHOD_NOT_FOUND = -32601;
var ERR_INVALID_PARAMS = -32602;
var ERR_INTERNAL = -32603;
function flattenPrompt(blocks) {
  const parts = [];
  for (const b of blocks) {
    if (b.type === "text") parts.push(b.text);
    else if (b.type === "resource" && b.resource.text) parts.push(b.resource.text);
  }
  return parts.join("\n\n").trim();
}

// src/acp/server.ts
import { createInterface } from "readline";
var AcpServer = class {
  requestHandlers = /* @__PURE__ */ new Map();
  notificationHandlers = /* @__PURE__ */ new Map();
  pending = /* @__PURE__ */ new Map();
  nextOutboundId = 1;
  output;
  rl;
  closed = false;
  constructor(opts = {}) {
    this.output = opts.output ?? process.stdout;
    const input = opts.input ?? process.stdin;
    this.rl = createInterface({ input });
    this.rl.on("line", (line) => {
      void this.handleLine(line);
    });
  }
  onRequest(method, handler) {
    this.requestHandlers.set(method, handler);
  }
  onNotification(method, handler) {
    this.notificationHandlers.set(method, handler);
  }
  sendNotification(method, params) {
    this.write({ jsonrpc: "2.0", method, params });
  }
  /** Send an outbound JSON-RPC request and resolve when the peer responds. */
  sendRequest(method, params) {
    const id = this.nextOutboundId++;
    return new Promise((resolve2, reject) => {
      this.pending.set(id, {
        resolve: resolve2,
        reject
      });
      this.write({ jsonrpc: "2.0", id, method, params });
    });
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    for (const p of this.pending.values()) p.reject(new Error("server closed"));
    this.pending.clear();
    this.rl.close();
  }
  /** Wait for the input stream to end. */
  done() {
    return new Promise((resolve2) => this.rl.once("close", () => resolve2()));
  }
  write(msg) {
    this.output.write(`${JSON.stringify(msg)}
`);
  }
  writeError(id, code, message) {
    this.write({ jsonrpc: "2.0", id, error: { code, message } });
  }
  async handleLine(raw) {
    const line = raw.trim();
    if (!line) return;
    let parsed;
    try {
      parsed = JSON.parse(line);
    } catch {
      this.writeError(null, ERR_PARSE, "parse error");
      return;
    }
    if (!parsed || typeof parsed !== "object") {
      this.writeError(null, ERR_PARSE, "expected JSON object");
      return;
    }
    const msg = parsed;
    if (typeof msg.method === "string" && msg.id !== void 0) {
      const id = msg.id;
      const handler = this.requestHandlers.get(msg.method);
      if (!handler) {
        this.writeError(id, ERR_METHOD_NOT_FOUND, `method not found: ${msg.method}`);
        return;
      }
      try {
        const result = await handler(msg.params);
        this.write({ jsonrpc: "2.0", id, result });
      } catch (err) {
        this.writeError(id, ERR_INTERNAL, err.message);
      }
      return;
    }
    if (typeof msg.method === "string" && msg.id === void 0) {
      const handler = this.notificationHandlers.get(msg.method);
      if (!handler) return;
      try {
        await handler(msg.params);
      } catch {
      }
      return;
    }
    if (msg.id !== void 0 && msg.method === void 0) {
      const response = parsed;
      const pending = this.pending.get(response.id);
      if (!pending) return;
      this.pending.delete(response.id);
      if (response.error) {
        pending.reject(new Error(response.error.message));
      } else {
        pending.resolve(response.result);
      }
    }
  }
};

// src/cli/commands/acp.ts
function resolveMcpPrefix(specName, specCount, globalPrefix) {
  if (specName) return `${specName}_`;
  if (specCount === 1 && globalPrefix) return globalPrefix;
  return "";
}
async function loadMcpServers(tools, specs, globalPrefix, workspaceDir = process.cwd()) {
  const clients = [];
  if (specs.length === 0) return clients;
  const cfg = readConfig();
  const normalizedSpecs = normalizeMcpConfig(cfg, specs);
  for (const spec of normalizedSpecs) {
    let label = "anon";
    let mcp;
    try {
      label = spec.name ?? "anon";
      if (spec.disabled) {
        process.stderr.write(`${formatMcpLifecycleEvent({ state: "disabled", name: label })}
`);
        continue;
      }
      process.stderr.write(`${formatMcpLifecycleEvent({ state: "handshake", name: label })}
`);
      const t0 = Date.now();
      const prefix = resolveMcpPrefix(spec.name, normalizedSpecs.length, globalPrefix);
      if (spec.transport === "stdio") preflightStdioSpec(spec);
      const transport = buildTransportFromSpec(spec, { cwd: workspaceDir });
      mcp = new McpClient({ transport, workspaceDir });
      await mcp.initialize();
      const bridge = await bridgeMcpTools(mcp, {
        registry: tools,
        namePrefix: prefix,
        serverName: label,
        onSlow: (info) => process.stderr.write(
          `${formatMcpSlowToast({ name: info.serverName, p95Ms: info.p95Ms, sampleSize: info.sampleSize })}
`
        )
      });
      process.stderr.write(
        `${formatMcpLifecycleEvent({
          state: "connected",
          name: label,
          tools: bridge.registeredNames.length,
          ms: Date.now() - t0
        })}
`
      );
      clients.push(mcp);
    } catch (err) {
      await mcp?.close().catch(() => void 0);
      process.stderr.write(
        `${formatMcpLifecycleEvent({ state: "failed", name: label, reason: err.message })}
  \u2192 ${t("mcpLifecycle.failedSetupConfigHint")}
`
      );
    }
  }
  return clients;
}
function resolveDir(raw, fallback) {
  if (!raw) return fallback;
  const abs = resolve(raw);
  if (!existsSync(abs) || !statSync(abs).isDirectory()) {
    throw new Error(`workspace directory not found: ${abs}`);
  }
  return abs;
}
async function buildSession(opts) {
  const model = opts.modelOverride || loadModel() || DEFAULT_MODEL;
  const toolset = await buildCodeToolset({ rootDir: opts.rootDir });
  const mcpClients = await loadMcpServers(
    toolset.tools,
    opts.mcpSpecs ?? [],
    opts.mcpPrefix,
    opts.rootDir
  );
  const system = codeSystemPrompt(opts.rootDir, {
    hasSemanticSearch: toolset.semantic.enabled,
    modelId: model,
    systemAppend: opts.systemAppend
  });
  const ep = loadEndpoint();
  const client = new DeepSeekClient({ apiKey: ep.apiKey, baseUrl: ep.baseUrl });
  const prefix = new ImmutablePrefix({ system, toolSpecs: toolset.tools.specs() });
  const loop = new CacheFirstLoop({
    client,
    prefix,
    tools: toolset.tools,
    model,
    budgetUsd: opts.budgetUsd,
    session: `acp-${timestampSuffix()}`
  });
  return {
    id: `sess_${timestampSuffix()}-${Math.random().toString(36).slice(2, 8)}`,
    rootDir: opts.rootDir,
    model,
    toolset,
    mcpClients,
    loop,
    eventizer: new Eventizer(),
    ctx: {
      model,
      prefixHash: prefix.fingerprint,
      reasoningEffort: loadReasoningEffort()
    },
    aborter: null
  };
}
async function acpCommand(opts) {
  loadDotenv();
  bridgeEndpointEnv();
  const defaultDir = resolveDir(opts.dir, process.cwd());
  const sessions = /* @__PURE__ */ new Map();
  const sessionContext = new AsyncLocalStorage();
  const server = new AcpServer();
  let transcriptStream = null;
  if (opts.transcript) {
    const defaultModel = opts.model || loadModel() || DEFAULT_MODEL;
    transcriptStream = openTranscriptFile(opts.transcript, {
      version: 1,
      source: "reasonix acp",
      model: defaultModel,
      startedAt: (/* @__PURE__ */ new Date()).toISOString()
    });
  }
  pauseGate.on((req) => {
    const editMode = opts.yolo ? "yolo" : loadEditMode();
    const auto = autoResolveVerdict(req, editMode);
    if (auto !== null) {
      pauseGate.resolve(req.id, auto);
      return;
    }
    const activeSessionId = sessionContext.getStore();
    if (!activeSessionId || !sessions.has(activeSessionId)) {
      pauseGate.cancel(req.id);
      return;
    }
    void (async () => {
      const verdict = await requestPermissionForGate(server, activeSessionId, req);
      pauseGate.resolve(req.id, verdict);
    })();
  });
  server.onRequest("initialize", (params) => {
    if (!params || typeof params !== "object") {
      throw Object.assign(new Error("initialize: missing params"), { code: ERR_INVALID_PARAMS });
    }
    return {
      protocolVersion: ACP_PROTOCOL_VERSION,
      agentCapabilities: {
        loadSession: false,
        promptCapabilities: { image: false, audio: false, embeddedContext: true },
        mcpCapabilities: { http: false, sse: false }
      },
      agentInfo: { name: "reasonix", title: "Reasonix", version: VERSION },
      authMethods: []
    };
  });
  server.onRequest("session/new", async (params) => {
    const rootDir = resolveDir(params?.cwd, defaultDir);
    const session = await buildSession({
      rootDir,
      modelOverride: opts.model,
      budgetUsd: opts.budgetUsd,
      mcpSpecs: opts.mcpSpecs,
      mcpPrefix: opts.mcpPrefix,
      systemAppend: process.env.REASONIX_ACP_SYSTEM_APPEND || void 0
    });
    sessions.set(session.id, session);
    return { sessionId: session.id };
  });
  server.onRequest("session/prompt", async (params) => {
    if (!params?.sessionId) {
      throw Object.assign(new Error("session/prompt: missing sessionId"), {
        code: ERR_INVALID_PARAMS
      });
    }
    const session = sessions.get(params.sessionId);
    if (!session) {
      throw Object.assign(new Error(`session/prompt: unknown session ${params.sessionId}`), {
        code: ERR_INVALID_PARAMS
      });
    }
    const text = flattenPrompt(params.prompt);
    if (!text) {
      throw Object.assign(new Error("session/prompt: empty prompt"), { code: ERR_INVALID_PARAMS });
    }
    session.aborter = new AbortController();
    let stopReason = "end_turn";
    try {
      await sessionContext.run(session.id, async () => {
        for await (const ev of session.loop.step(text)) {
          if (session.aborter?.signal.aborted) {
            stopReason = "cancelled";
            break;
          }
          if (transcriptStream) {
            writeRecord(
              transcriptStream,
              recordFromLoopEvent(ev, {
                model: session.ctx.model,
                prefixHash: session.ctx.prefixHash
              })
            );
          }
          for (const kev of session.eventizer.consume(ev, session.ctx)) {
            dispatchKernelEvent(server, session.id, kev);
            if (kev.type === "error") stopReason = "error";
          }
        }
      });
    } catch (err) {
      const cause = err instanceof Error ? err : new Error(String(err));
      const message = cause.message;
      const { code, phase } = errorMeta(cause);
      server.sendNotification("session/update", {
        sessionId: session.id,
        update: {
          sessionUpdate: "agent_message_chunk",
          content: { type: "text", text: `

[error] ${message}` },
          metadata: {
            error: {
              name: cause.name || "Error",
              message,
              code,
              phase,
              retryable: false
            }
          }
        }
      });
      stopReason = "error";
    } finally {
      session.aborter = null;
    }
    return { stopReason, transcriptPath: opts.transcript || null };
  });
  server.onNotification("session/cancel", (params) => {
    const session = params?.sessionId ? sessions.get(params.sessionId) : void 0;
    session?.aborter?.abort();
  });
  try {
    await server.done();
  } finally {
    transcriptStream?.end();
    const closes = [];
    for (const session of sessions.values()) {
      for (const mcp of session.mcpClients) {
        closes.push(mcp.close().catch(() => void 0));
      }
    }
    await Promise.all(closes);
  }
}
export {
  acpCommand,
  loadMcpServers
};
//# sourceMappingURL=acp-ABNDGEYC.js.map