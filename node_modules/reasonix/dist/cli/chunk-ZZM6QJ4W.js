#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }

// src/cli/cpu-prof.ts
import { writeFileSync } from "fs";
import { Session } from "inspector/promises";
import { resolve } from "path";
import { gzipSync } from "zlib";
var session = null;
var outPath = null;
var signalHandlerInstalled = false;
var stopping = false;
function defaultOutPath() {
  const stamp = (/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-").replace("Z", "");
  return resolve(process.cwd(), `reasonix-cpu-${stamp}.cpuprofile`);
}
async function startCpuProfile(pathArg) {
  if (session) return outPath ?? defaultOutPath();
  outPath = typeof pathArg === "string" ? resolve(pathArg) : defaultOutPath();
  session = new Session();
  session.connect();
  await session.post("Profiler.enable");
  await session.post("Profiler.start");
  process.stderr.write(`\u25B8 cpu profile recording \u2014 will save to ${outPath} on exit
`);
  installSignalHandler();
  return outPath;
}
async function stopAndSaveCpuProfile() {
  if (!session || !outPath || stopping) return;
  stopping = true;
  const s = session;
  const baseOut = outPath;
  session = null;
  try {
    const { profile } = await s.post("Profiler.stop");
    const json = JSON.stringify(profile);
    const gz = gzipSync(json);
    const gzPath = `${baseOut}.gz`;
    writeFileSync(gzPath, gz);
    const mb = (gz.length / (1024 * 1024)).toFixed(2);
    process.stderr.write(
      `\u25B8 cpu profile saved \u2192 ${gzPath} (${mb} MB gzipped)
  drag into a GitHub issue comment, or:
  gh issue comment <N> --repo esengine/DeepSeek-Reasonix -F "${gzPath}"
`
    );
  } catch (e) {
    process.stderr.write(`\u25B2 cpu profile save failed: ${e.message}
`);
  } finally {
    try {
      s.disconnect();
    } catch {
    }
  }
}
function installSignalHandler() {
  if (signalHandlerInstalled) return;
  signalHandlerInstalled = true;
  for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.on(sig, () => {
      void (async () => {
        await stopAndSaveCpuProfile();
        process.exit(sig === "SIGINT" ? 130 : 0);
      })();
    });
  }
}

// src/cli/startup-profile.ts
import { performance } from "perf_hooks";
var marks = [];
var dumped = false;
function envFlag() {
  const v = process.env.REASONIX_PROFILE_STARTUP;
  return v === "1" || v === "true" || v === "yes";
}
function markPhase(name) {
  if (!envFlag()) return;
  marks.push({ name, t: performance.now() });
}
function dumpStartupProfile(stream = process.stderr) {
  if (!envFlag() || dumped || marks.length === 0) return;
  dumped = true;
  const totalMs = marks[marks.length - 1].t;
  const widest = String(Math.round(totalMs)).length;
  const lines = ["[startup-profile]"];
  let prev = 0;
  for (const m of marks) {
    const cum = Math.round(m.t).toString().padStart(widest);
    const delta = Math.round(m.t - prev);
    lines.push(`  ${cum}ms  ${m.name.padEnd(28)}  (+${delta})`);
    prev = m.t;
  }
  lines.push(
    `\u2500\u2500\u2500 ${Math.round(totalMs)}ms total \xB7 last phase ${marks[marks.length - 1].name} \xB7 set REASONIX_PROFILE_STARTUP=0 to silence`
  );
  stream.write(`${lines.join("\n")}
`);
}

export {
  startCpuProfile,
  stopAndSaveCpuProfile,
  markPhase,
  dumpStartupProfile
};
//# sourceMappingURL=chunk-ZZM6QJ4W.js.map