#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
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
  ToolRegistry,
  bridgeMcpTools
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
import "./chunk-4V4TKQMB.js";
import {
  appendUsage
} from "./chunk-FK7NXDRP.js";
import "./chunk-V4AXMN4X.js";
import "./chunk-XHP6NYOT.js";
import "./chunk-J4MYMBJ7.js";
import "./chunk-BOWSNGQC.js";
import {
  DeepSeekClient
} from "./chunk-QSKDP3OS.js";
import "./chunk-25T6CVUP.js";
import "./chunk-NVI4XPOQ.js";
import "./chunk-6UNHNVJR.js";
import "./chunk-P5SUHDUQ.js";
import "./chunk-XXC2BYTV.js";
import {
  loadDotenv
} from "./chunk-2UQP6H6T.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import {
  bridgeEndpointEnv,
  defaultConfigPath,
  isPlausibleKey,
  loadApiKey,
  loadEndpoint,
  loadToolRateLimit,
  normalizeMcpConfig,
  readConfig,
  saveApiKey
} from "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/cli/commands/run.ts
import { stdin, stdout } from "process";
import { createInterface } from "readline/promises";
async function ensureApiKey() {
  const existing = loadApiKey();
  if (existing) return existing;
  if (!stdin.isTTY) {
    process.stderr.write(t("run.missingApiKey"));
    process.exit(1);
  }
  process.stdout.write(
    "DeepSeek API key not configured.\nGet one at https://platform.deepseek.com/api_keys\n"
  );
  const rl = createInterface({ input: stdin, output: stdout });
  try {
    while (true) {
      const answer = (await rl.question("API key \u203A ")).trim();
      if (!answer) continue;
      if (!isPlausibleKey(answer)) {
        process.stdout.write("Key looks too short. Paste the full token (16+ chars, no spaces).\n");
        continue;
      }
      saveApiKey(answer);
      process.stdout.write(`Saved to ${defaultConfigPath()}

`);
      return answer;
    }
  } finally {
    rl.close();
  }
}
async function runCommand(opts) {
  loadDotenv();
  await ensureApiKey();
  bridgeEndpointEnv();
  const cfg = readConfig();
  const normalizedSpecs = normalizeMcpConfig(
    cfg,
    opts.mcp && opts.mcp.length > 0 ? opts.mcp : void 0
  );
  const clients = [];
  let tools;
  let successCount = 0;
  const workspaceDir = process.cwd();
  if (normalizedSpecs.length > 0) {
    tools = new ToolRegistry({ rateLimit: loadToolRateLimit() });
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
        const prefix2 = spec.name ? `${spec.name}_` : normalizedSpecs.length === 1 && opts.mcpPrefix ? opts.mcpPrefix : "";
        if (spec.transport === "stdio") preflightStdioSpec(spec);
        const transport = buildTransportFromSpec(spec, { cwd: workspaceDir });
        mcp = new McpClient({ transport, workspaceDir });
        await mcp.initialize();
        const bridge = await bridgeMcpTools(mcp, {
          registry: tools,
          namePrefix: prefix2,
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
        successCount++;
      } catch (err) {
        await mcp?.close().catch(() => void 0);
        process.stderr.write(
          `${formatMcpLifecycleEvent({ state: "failed", name: label, reason: err.message })}
  ${t("mcpLifecycle.failedSetupConfigHint")}
`
        );
      }
    }
    if (successCount === 0) tools = void 0;
  }
  const ep = loadEndpoint();
  const client = new DeepSeekClient({ apiKey: ep.apiKey, baseUrl: ep.baseUrl });
  const prefix = new ImmutablePrefix({
    system: opts.system,
    toolSpecs: tools?.specs()
  });
  const loop = new CacheFirstLoop({
    client,
    prefix,
    tools,
    model: opts.model,
    budgetUsd: opts.budgetUsd
  });
  const prefixHash = prefix.fingerprint;
  let transcriptStream = null;
  if (opts.transcript) {
    transcriptStream = openTranscriptFile(opts.transcript, {
      version: 1,
      source: "reasonix run",
      model: opts.model,
      startedAt: (/* @__PURE__ */ new Date()).toISOString()
    });
    writeRecord(transcriptStream, {
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn: 1,
      role: "user",
      content: opts.task
    });
  }
  try {
    for await (const ev of loop.step(opts.task)) {
      if (ev.role === "assistant_delta" && ev.content) process.stdout.write(ev.content);
      if (ev.role === "tool") process.stdout.write(`
[tool ${ev.toolName}] ${ev.content}
`);
      if (ev.role === "error") process.stderr.write(`
[error] ${ev.error}
`);
      if (ev.role === "done") process.stdout.write("\n");
      if (ev.role === "assistant_final" && ev.stats?.usage) {
        appendUsage({ session: null, model: ev.stats.model, usage: ev.stats.usage });
      }
      if (transcriptStream && ev.role !== "assistant_delta") {
        writeRecord(transcriptStream, recordFromLoopEvent(ev, { model: opts.model, prefixHash }));
      }
    }
  } finally {
    transcriptStream?.end();
  }
  const s = loop.stats.summary();
  process.stdout.write(
    `
\u2014 turns:${s.turns} cache:${(s.cacheHitRatio * 100).toFixed(1)}% cost:$${s.totalCostUsd.toFixed(6)} save-vs-claude:${s.savingsVsClaudePct.toFixed(1)}%
`
  );
  if (opts.transcript) {
    process.stdout.write(`
transcript: ${opts.transcript}
`);
    process.stdout.write(`  \u2192 npx reasonix replay ${opts.transcript}
`);
  }
  for (const c of clients) await c.close();
}
export {
  runCommand
};
//# sourceMappingURL=run-ABQYOPVM.js.map