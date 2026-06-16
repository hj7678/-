#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  MemoryStore,
  readGlobalReasonixMemory,
  readProjectMemory
} from "./chunk-J4MYMBJ7.js";

// src/desktop/memory-browser.ts
import { existsSync, readFileSync } from "fs";
import { basename, resolve } from "path";
function collectMemoryEntriesForWorkspace(projectRoot, opts = {}) {
  const out = [];
  const project = readProjectMemory(projectRoot);
  if (project) {
    out.push({
      kind: "project_file",
      scope: "project",
      name: basename(project.path),
      path: project.path,
      description: "Project memory file",
      type: "freeform"
    });
  }
  const global = readGlobalReasonixMemory(opts.reasonixHome);
  if (global) {
    out.push({
      kind: "global_file",
      scope: "global",
      name: basename(global.path),
      path: global.path,
      description: "Global memory file",
      type: "freeform"
    });
  }
  const store = new MemoryStore({ homeDir: opts.reasonixHome, projectRoot });
  for (const entry of store.list()) {
    out.push(structuredInfo(store, entry));
  }
  return out;
}
function readMemoryEntryDetail(request, projectRoot, opts = {}) {
  const requested = resolve(request.path);
  const entry = collectMemoryEntriesForWorkspace(projectRoot, opts).find(
    (candidate) => resolve(candidate.path) === requested
  );
  if (!entry) throw new Error(`memory path not available: ${request.path}`);
  if (entry.kind === "structured") {
    const store = new MemoryStore({ homeDir: opts.reasonixHome, projectRoot });
    const structured = store.read(entry.scope, entry.name);
    return {
      ...entry,
      description: structured.description,
      type: structured.type,
      body: structured.body,
      createdAt: structured.createdAt
    };
  }
  if (!existsSync(entry.path)) throw new Error(`memory file missing: ${entry.path}`);
  return {
    ...entry,
    body: readFileSync(entry.path, "utf8").trim()
  };
}
function structuredInfo(store, entry) {
  return {
    kind: "structured",
    scope: entry.scope,
    name: entry.name,
    path: store.pathFor(entry.scope, entry.name),
    description: entry.description,
    type: entry.type
  };
}

export {
  collectMemoryEntriesForWorkspace,
  readMemoryEntryDetail
};
//# sourceMappingURL=chunk-B5JISV5I.js.map