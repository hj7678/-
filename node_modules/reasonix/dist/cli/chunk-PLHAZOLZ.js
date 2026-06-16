#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }

// src/mcp/catalog.ts
var MCP_CATALOG = [
  {
    name: "filesystem",
    summary: "read/write/search files inside a sandboxed directory",
    package: "@modelcontextprotocol/server-filesystem",
    userArgs: "<dir>",
    note: "the directory is a hard sandbox \u2014 the server refuses access outside it"
  },
  {
    name: "memory",
    summary: "persistent key-value memory across sessions",
    package: "@modelcontextprotocol/server-memory"
  },
  {
    name: "github",
    summary: "read issues, PRs, code search (needs GITHUB_PERSONAL_ACCESS_TOKEN)",
    package: "@modelcontextprotocol/server-github",
    note: "set GITHUB_PERSONAL_ACCESS_TOKEN in your env before spawning"
  },
  {
    name: "puppeteer",
    summary: "browser automation \u2014 take screenshots, click, type",
    package: "@modelcontextprotocol/server-puppeteer",
    note: "downloads Chromium on first run (~200 MB)"
  },
  {
    name: "everything",
    summary: "official test server \u2014 exercises every MCP feature",
    package: "@modelcontextprotocol/server-everything",
    note: "useful for debugging your Reasonix setup"
  }
];
function mcpCommandFor(entry) {
  const pkg = entry.package;
  const tail = entry.userArgs ? ` ${entry.userArgs}` : "";
  return `--mcp "${entry.name}=npx -y ${pkg}${tail}"`;
}

export {
  MCP_CATALOG,
  mcpCommandFor
};
//# sourceMappingURL=chunk-PLHAZOLZ.js.map