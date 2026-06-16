#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  MCP_CATALOG
} from "./chunk-PLHAZOLZ.js";

// src/mcp/registry-fetch.ts
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { homedir } from "os";
import { dirname, join } from "path";
var OFFICIAL_REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers";
var SMITHERY_REGISTRY_URL = "https://registry.smithery.ai/servers";
var CACHE_TTL_MS = 24 * 60 * 60 * 1e3;
var FETCH_TIMEOUT_MS = 1e4;
var CACHE_SCHEMA_VERSION = 2;
function defaultCachePath() {
  return join(homedir(), ".reasonix", "mcp-registry-cache.json");
}
function readCache(path) {
  try {
    const raw = readFileSync(path, "utf8");
    const parsed = JSON.parse(raw);
    if (parsed.schemaVersion !== CACHE_SCHEMA_VERSION || typeof parsed.fetchedAt !== "number" || !Array.isArray(parsed.entries) || typeof parsed.pagination?.pagesLoaded !== "number") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}
function writeCache(path, file) {
  try {
    const dir = dirname(path);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    writeFileSync(path, JSON.stringify(file, null, 2));
  } catch {
  }
}
async function timeoutFetch(url, fetcher) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetcher(url, { signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}
function normalizeOfficialPackage(pkg) {
  if (!pkg) return void 0;
  const runtime = pkg.registryType === "npm" ? "npm" : pkg.registryType === "pypi" ? "pypi" : null;
  if (!runtime) return void 0;
  const t = pkg.transport?.type;
  const transport = t === "sse" ? "sse" : t === "streamable-http" ? "streamable-http" : "stdio";
  const requiredEnv = (pkg.environmentVariables ?? []).map((e) => e.name).filter((n) => typeof n === "string" && n.length > 0);
  const install = { runtime, transport };
  if (pkg.identifier) install.packageId = pkg.identifier;
  if (pkg.version) install.version = pkg.version;
  if (requiredEnv.length > 0) install.requiredEnv = requiredEnv;
  return install;
}
function normalizeOfficial(server) {
  if (!server?.name) return null;
  let install = normalizeOfficialPackage(server.packages?.[0]);
  if (!install && server.remotes?.[0]?.url) {
    const remote = server.remotes[0];
    const transport = remote.type === "streamable-http" ? "streamable-http" : "sse";
    install = { runtime: "remote", transport, url: remote.url };
  }
  const entry = {
    name: server.name,
    title: server.title || server.name,
    description: server.description ?? "",
    source: "official"
  };
  if (install) entry.install = install;
  if (server.websiteUrl) entry.homepage = server.websiteUrl;
  const icon = server.icons?.find((i) => i.src)?.src;
  if (icon) entry.iconUrl = icon;
  return entry;
}
async function fetchOfficialPage(cursor, fetcher = globalThis.fetch) {
  const url = cursor ? `${OFFICIAL_REGISTRY_URL}?cursor=${encodeURIComponent(cursor)}` : OFFICIAL_REGISTRY_URL;
  const resp = await timeoutFetch(url, fetcher);
  if (!resp.ok) throw new Error(`official registry HTTP ${resp.status}`);
  const json = await resp.json();
  const entries = [];
  for (const e of json.servers ?? []) {
    const norm = normalizeOfficial(e.server);
    if (norm) entries.push(norm);
  }
  return { entries, nextCursor: json.metadata?.nextCursor ?? null };
}
function normalizeSmithery(s) {
  if (!s.qualifiedName) return null;
  const entry = {
    name: s.qualifiedName,
    title: s.displayName || s.qualifiedName,
    description: s.description ?? "",
    source: "smithery"
  };
  if (typeof s.useCount === "number") entry.popularity = s.useCount;
  if (s.homepage) entry.homepage = s.homepage;
  if (s.iconUrl) entry.iconUrl = s.iconUrl;
  return entry;
}
async function fetchSmitheryDetail(qualifiedName, fetcher = globalThis.fetch) {
  const url = `${SMITHERY_REGISTRY_URL}/${encodeURIComponent(qualifiedName)}`;
  const resp = await timeoutFetch(url, fetcher);
  if (!resp.ok) return null;
  const json = await resp.json();
  const conn = json.connections?.[0];
  if (!conn) return null;
  if (conn.type === "http" || conn.type === "ws") {
    const deploymentUrl = conn.deploymentUrl ?? json.deploymentUrl;
    if (!deploymentUrl) return null;
    return { runtime: "remote", transport: "streamable-http", url: deploymentUrl };
  }
  if (conn.type === "stdio") {
    return {
      runtime: "npm",
      packageId: "@smithery/cli",
      transport: "stdio",
      extraArgs: ["run", qualifiedName]
    };
  }
  return null;
}
async function fetchSmitheryFirstPage(fetcher = globalThis.fetch) {
  const resp = await timeoutFetch(SMITHERY_REGISTRY_URL, fetcher);
  if (!resp.ok) throw new Error(`smithery HTTP ${resp.status}`);
  const json = await resp.json();
  const entries = (json.servers ?? []).map(normalizeSmithery).filter((x) => x !== null);
  if (entries.length === 0) throw new Error("smithery returned no entries");
  return entries;
}
function fallbackFromCatalog() {
  return MCP_CATALOG.map((e) => ({
    name: e.name,
    title: e.name,
    description: e.summary,
    source: "local",
    install: {
      runtime: "npm",
      packageId: e.package,
      transport: "stdio"
    }
  }));
}
function newOfficialCache(initial) {
  const seen = /* @__PURE__ */ new Map();
  for (const e of initial.entries) if (!seen.has(e.name)) seen.set(e.name, e);
  return {
    schemaVersion: CACHE_SCHEMA_VERSION,
    fetchedAt: Date.now(),
    source: "official",
    entries: [...seen.values()],
    pagination: { pagesLoaded: 1, nextCursor: initial.nextCursor }
  };
}
function newStaticCache(source, entries) {
  return {
    schemaVersion: CACHE_SCHEMA_VERSION,
    fetchedAt: Date.now(),
    source,
    entries,
    pagination: { pagesLoaded: 1, nextCursor: null }
  };
}
async function openRegistry(opts = {}) {
  const fetcher = opts.fetcher ?? globalThis.fetch;
  const cachePath = opts.cachePath ?? defaultCachePath();
  const errors = [];
  if (!opts.noCache && !opts.preferSource) {
    const cached = readCache(cachePath);
    if (cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS && cached.entries.length > 0) {
      return {
        source: cached.source,
        cache: cached,
        fromCache: true,
        fetchedAt: cached.fetchedAt,
        errors: [],
        cachePath
      };
    }
  }
  const tryOfficial = async () => {
    const first = await fetchOfficialPage(null, fetcher);
    const cache = newOfficialCache(first);
    opts.onProgress?.({ source: "official", page: 1, entries: cache.entries.length });
    writeCache(cachePath, cache);
    return {
      source: "official",
      cache,
      fromCache: false,
      fetchedAt: cache.fetchedAt,
      errors,
      cachePath
    };
  };
  const trySmithery = async () => {
    const entries = await fetchSmitheryFirstPage(fetcher);
    const cache = newStaticCache("smithery", entries);
    opts.onProgress?.({ source: "smithery", page: 1, entries: entries.length });
    writeCache(cachePath, cache);
    return {
      source: "smithery",
      cache,
      fromCache: false,
      fetchedAt: cache.fetchedAt,
      errors,
      cachePath
    };
  };
  const tryLocal = () => {
    const cache = newStaticCache("local", fallbackFromCatalog());
    return {
      source: "local",
      cache,
      fromCache: false,
      fetchedAt: cache.fetchedAt,
      errors,
      cachePath
    };
  };
  if (opts.preferSource === "local") return tryLocal();
  if (opts.preferSource === "smithery") {
    try {
      return await trySmithery();
    } catch (e) {
      errors.push(`smithery: ${e.message}`);
      return tryLocal();
    }
  }
  try {
    return await tryOfficial();
  } catch (e) {
    errors.push(`official: ${e.message}`);
  }
  try {
    return await trySmithery();
  } catch (e) {
    errors.push(`smithery: ${e.message}`);
  }
  const stale = readCache(cachePath);
  if (stale) {
    return {
      source: stale.source,
      cache: stale,
      fromCache: true,
      fetchedAt: stale.fetchedAt,
      errors,
      cachePath
    };
  }
  return tryLocal();
}
async function loadMorePages(handle, opts = {}) {
  if (handle.source !== "official") {
    return { pagesAdded: 0, newEntries: 0, exhausted: true };
  }
  const cache = handle.cache;
  if (cache.pagination.nextCursor === null) {
    return { pagesAdded: 0, newEntries: 0, exhausted: true };
  }
  const fetcher = opts.fetcher ?? globalThis.fetch;
  const limit = opts.pages ?? 1;
  const seen = new Set(cache.entries.map((e) => e.name));
  const matchCount = () => {
    if (!opts.filter) return 0;
    let n = 0;
    for (const e of cache.entries) if (opts.filter(e)) n++;
    return n;
  };
  let pagesAdded = 0;
  let newEntries = 0;
  for (let i = 0; i < limit; i++) {
    if (cache.pagination.nextCursor === null) break;
    if (opts.matchTarget !== void 0 && matchCount() >= opts.matchTarget) break;
    const result = await fetchOfficialPage(cache.pagination.nextCursor, fetcher);
    for (const e of result.entries) {
      if (!seen.has(e.name)) {
        seen.add(e.name);
        cache.entries.push(e);
        newEntries++;
      }
    }
    cache.pagination.pagesLoaded += 1;
    cache.pagination.nextCursor = result.nextCursor;
    pagesAdded += 1;
    opts.onProgress?.({
      source: "official",
      page: cache.pagination.pagesLoaded,
      entries: cache.entries.length
    });
  }
  if (pagesAdded > 0) writeCache(handle.cachePath, cache);
  return {
    pagesAdded,
    newEntries,
    exhausted: cache.pagination.nextCursor === null
  };
}
function specStringFor(name, install) {
  const localName = name.split("/").pop() ?? name;
  const safe = localName.replace(/[^a-zA-Z0-9_-]/g, "-").replace(/^-+|-+$/g, "") || "mcp";
  if (install.runtime === "remote") {
    if (!install.url) throw new Error(`remote install for ${name} has no URL`);
    if (install.transport === "streamable-http") return `${safe}=streamable+${install.url}`;
    return `${safe}=${install.url}`;
  }
  const trail = install.extraArgs?.length ? ` ${install.extraArgs.join(" ")}` : "";
  if (install.runtime === "npm") {
    if (!install.packageId) throw new Error(`npm install for ${name} has no packageId`);
    const pinned = install.version ? `${install.packageId}@${install.version}` : install.packageId;
    return `${safe}=npx -y ${pinned}${trail}`;
  }
  if (install.runtime === "pypi") {
    if (!install.packageId) throw new Error(`pypi install for ${name} has no packageId`);
    return `${safe}=uvx ${install.packageId}${trail}`;
  }
  throw new Error(`unsupported install runtime: ${install.runtime}`);
}
function handleToFetchResult(handle) {
  return {
    entries: handle.cache.entries,
    source: handle.source,
    fromCache: handle.fromCache,
    fetchedAt: handle.fetchedAt,
    errors: handle.errors,
    hasMore: handle.cache.pagination.nextCursor !== null
  };
}

export {
  fetchSmitheryDetail,
  openRegistry,
  loadMorePages,
  specStringFor,
  handleToFetchResult
};
//# sourceMappingURL=chunk-XJXDHAES.js.map