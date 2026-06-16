#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }

// src/version.ts
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { homedir } from "os";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
var REGISTRY_URL = "https://registry.npmjs.org/reasonix/latest";
var LATEST_CACHE_TTL_MS = 24 * 60 * 60 * 1e3;
var LATEST_FETCH_TIMEOUT_MS = 2e3;
function readPackageVersion() {
  try {
    let dir = dirname(fileURLToPath(import.meta.url));
    for (let i = 0; i < 6; i++) {
      const p = join(dir, "package.json");
      if (existsSync(p)) {
        const pkg = JSON.parse(readFileSync(p, "utf8"));
        if (pkg?.name === "reasonix" && typeof pkg.version === "string") {
          return pkg.version;
        }
      }
      const parent = dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  } catch {
  }
  return "0.0.0-dev";
}
var VERSION = readPackageVersion();
function cachePath(homeDirOverride) {
  return join(homeDirOverride ?? homedir(), ".reasonix", "version-cache.json");
}
function readCache(homeDirOverride) {
  try {
    const raw = readFileSync(cachePath(homeDirOverride), "utf8");
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.version === "string" && typeof parsed.checkedAt === "number") {
      return parsed;
    }
  } catch {
  }
  return null;
}
function writeCache(entry, homeDirOverride) {
  try {
    const p = cachePath(homeDirOverride);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, JSON.stringify(entry), "utf8");
  } catch {
  }
}
async function getLatestVersion(opts = {}) {
  const ttl = opts.ttlMs ?? LATEST_CACHE_TTL_MS;
  if (!opts.force) {
    const cached = readCache(opts.homeDir);
    if (cached && Date.now() - cached.checkedAt < ttl) return cached.version;
  }
  const fetchImpl = opts.fetchImpl ?? globalThis.fetch;
  if (!fetchImpl) return null;
  const url = opts.registryUrl ?? REGISTRY_URL;
  const timeout = opts.timeoutMs ?? LATEST_FETCH_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetchImpl(url, {
      signal: controller.signal,
      headers: { accept: "application/json" }
    });
    if (!res.ok) return null;
    const body = await res.json();
    if (typeof body.version !== "string") return null;
    writeCache({ version: body.version, checkedAt: Date.now() }, opts.homeDir);
    return body.version;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
function compareVersions(a, b) {
  const [aCore = "0", aPre = ""] = a.split("-", 2);
  const [bCore = "0", bPre = ""] = b.split("-", 2);
  const aParts = aCore.split(".").map((p) => Number.parseInt(p, 10) || 0);
  const bParts = bCore.split(".").map((p) => Number.parseInt(p, 10) || 0);
  for (let i = 0; i < 3; i++) {
    const diff = (aParts[i] ?? 0) - (bParts[i] ?? 0);
    if (diff !== 0) return diff;
  }
  if (!aPre && !bPre) return 0;
  if (!aPre) return 1;
  if (!bPre) return -1;
  return aPre < bPre ? -1 : aPre > bPre ? 1 : 0;
}
function detectInstallSource(bin) {
  const raw = bin ?? process.argv[1] ?? "";
  if (!raw) return "unknown";
  const norm = raw.replace(/\\/g, "/").toLowerCase();
  if (/\/_npx\//.test(norm)) return "npx";
  if (/\/\.pnpm\//.test(norm) && /dlx/i.test(norm)) return "npx";
  const ua = (process.env.npm_config_user_agent ?? "").toLowerCase();
  if (ua.includes("npx/")) return "npx";
  if (/\/\.bun\//.test(norm) || /\/bun\/install\//.test(norm)) return "bun";
  if (/\/pnpm\/global\//.test(norm) || /\/pnpm\/[^/]+\/node_modules\//.test(norm)) return "pnpm";
  if (/\/yarn\/global\//.test(norm) || /\/\.yarn\/global\//.test(norm)) return "yarn";
  if (/\/node_modules\/reasonix(\b|\/)/.test(norm)) return "npm";
  return "unknown";
}
function detectNpmInstallPrefix(bin) {
  const raw = bin ?? process.argv[1] ?? "";
  if (!raw) return null;
  const norm = raw.replace(/\\/g, "/");
  const posix = norm.match(/^(.+?)\/lib\/node_modules\/reasonix(?:\/|$)/i);
  if (posix) return posix[1] ?? null;
  const win = norm.match(/^(.+?)\/node_modules\/reasonix(?:\/|$)/i);
  if (win) return win[1] ?? null;
  return null;
}

export {
  VERSION,
  getLatestVersion,
  compareVersions,
  detectInstallSource,
  detectNpmInstallPrefix
};
//# sourceMappingURL=chunk-XXC2BYTV.js.map