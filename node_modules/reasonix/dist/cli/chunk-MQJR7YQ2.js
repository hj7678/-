#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  SseTransport,
  StdioTransport,
  StreamableHttpTransport
} from "./chunk-4SBXAHR6.js";

// src/mcp/preflight.ts
import { statSync } from "fs";
var FILESYSTEM_PKG = "@modelcontextprotocol/server-filesystem";
function preflightStdioSpec(spec) {
  const pkgIndex = spec.args.indexOf(FILESYSTEM_PKG);
  if (pkgIndex < 0) return;
  const positional = spec.args.slice(pkgIndex + 1).filter((a) => !a.startsWith("-"));
  for (const dir of positional) {
    let stat;
    try {
      stat = statSync(dir);
    } catch {
      throw new Error(
        `MCP filesystem sandbox '${dir}' does not exist \u2014 create it with: mkdir -p '${dir}'`
      );
    }
    if (!stat.isDirectory()) {
      throw new Error(`MCP filesystem sandbox '${dir}' exists but is not a directory`);
    }
  }
}

// src/mcp/transport-from-spec.ts
function buildTransportFromSpec(spec, opts = {}) {
  if (spec.transport === "sse") {
    return new SseTransport({ url: spec.url, headers: opts.headers ?? spec.headers });
  }
  if (spec.transport === "streamable-http") {
    return new StreamableHttpTransport({
      url: spec.url,
      headers: opts.headers ?? spec.headers
    });
  }
  return new StdioTransport({
    command: spec.command,
    args: spec.args,
    env: opts.env ?? spec.env,
    cwd: opts.cwd
  });
}

export {
  preflightStdioSpec,
  buildTransportFromSpec
};
//# sourceMappingURL=chunk-MQJR7YQ2.js.map