#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  probeOllama
} from "./chunk-I4SH5Z7S.js";

// src/index/semantic/ollama-launcher.ts
import { spawn, spawnSync } from "child_process";
import { existsSync } from "fs";
import { join } from "path";
import { setTimeout as sleep } from "timers/promises";
function findOllamaBinary() {
  const cmd = process.platform === "win32" ? "where" : "which";
  const out = spawnSync(cmd, ["ollama"], { encoding: "utf8" });
  if (out.status === 0) {
    const first = out.stdout.split(/\r?\n/).find((l) => l.trim().length > 0);
    if (first) return first.trim();
  }
  if (process.platform === "win32") {
    const local = process.env.LOCALAPPDATA;
    if (local) {
      const candidate = join(local, "Programs", "Ollama", "ollama.exe");
      if (existsSync(candidate)) return candidate;
    }
  }
  return null;
}
async function checkOllamaStatus(modelName, baseUrl) {
  const binary = findOllamaBinary();
  const probe = await probeOllama({ baseUrl });
  const installedModels = probe.ok ? probe.models : [];
  const wanted = modelName.includes(":") ? modelName : `${modelName}:latest`;
  const modelPulled = installedModels.some((m) => m === modelName || m === wanted);
  return {
    binaryFound: binary !== null,
    daemonRunning: probe.ok,
    modelPulled,
    modelName,
    installedModels
  };
}
async function startOllamaDaemon(opts = {}) {
  const timeoutMs = opts.timeoutMs ?? 15e3;
  const child = spawn(findOllamaBinary() ?? "ollama", ["serve"], {
    detached: true,
    stdio: "ignore",
    windowsHide: true
  });
  child.unref();
  const pid = child.pid ?? null;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (opts.signal?.aborted) return { ready: false, pid };
    const probe = await probeOllama({ baseUrl: opts.baseUrl, signal: opts.signal });
    if (probe.ok) return { ready: true, pid };
    await sleep(500);
  }
  return { ready: false, pid };
}
async function pullOllamaModel(modelName, opts = {}) {
  return new Promise((resolve) => {
    const child = spawn(findOllamaBinary() ?? "ollama", ["pull", modelName], {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    });
    if (opts.signal) {
      const onAbort = () => child.kill();
      opts.signal.addEventListener("abort", onAbort, { once: true });
      child.once("exit", () => opts.signal?.removeEventListener("abort", onAbort));
    }
    streamLines(child.stdout, (l) => opts.onLine?.(l, "stdout"));
    streamLines(child.stderr, (l) => opts.onLine?.(l, "stderr"));
    child.once("exit", (code) => resolve(code ?? -1));
    child.once("error", () => resolve(-1));
  });
}
function streamLines(stream, cb) {
  if (!stream) return;
  let buf = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buf += chunk;
    let nl = buf.indexOf("\n");
    while (nl !== -1) {
      const line = buf.slice(0, nl).replace(/\r$/, "");
      buf = buf.slice(nl + 1);
      if (line.length > 0) cb(line);
      nl = buf.indexOf("\n");
    }
  });
  stream.on("end", () => {
    if (buf.length > 0) cb(buf.replace(/\r$/, ""));
  });
}

export {
  checkOllamaStatus,
  startOllamaDaemon,
  pullOllamaModel
};
//# sourceMappingURL=chunk-RRZIIMAF.js.map