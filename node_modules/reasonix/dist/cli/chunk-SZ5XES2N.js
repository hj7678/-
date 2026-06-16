#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  VERSION,
  compareVersions,
  detectInstallSource,
  detectNpmInstallPrefix,
  getLatestVersion
} from "./chunk-XXC2BYTV.js";

// src/cli/commands/update.ts
import { spawn } from "child_process";
var MANUAL_UPDATE_COMMANDS = [
  "npm install -g reasonix@latest",
  "bun add -g reasonix",
  "pnpm add -g reasonix@latest",
  "yarn global add reasonix@latest"
];
function planUpdate(input) {
  const diff = compareVersions(input.current, input.latest);
  if (diff > 0) {
    return {
      action: "newer-local",
      message: `current (${input.current}) is newer than the published ${input.latest} \u2014 nothing to do.`
    };
  }
  if (diff === 0) {
    return { action: "up-to-date", message: `reasonix ${input.current} is up to date.` };
  }
  if (input.installSource === "npx") {
    return {
      action: "npx-hint",
      message: [
        `reasonix ${input.latest} is available.`,
        "you're running via npx \u2014 the next `npx reasonix ...` launch will auto-fetch",
        "the latest (npx caches packages for a short window). to force a refresh",
        "sooner, clear the cache: `npm cache clean --force`."
      ].join("\n")
    };
  }
  if (input.installSource === "unknown") {
    return {
      action: "manual-hint",
      message: [
        `reasonix ${input.latest} is available, but the install source could not be determined automatically.`,
        "run one of these manually based on how you installed reasonix:",
        ...MANUAL_UPDATE_COMMANDS.map((c) => `  ${c}`)
      ].join("\n")
    };
  }
  const command = buildUpdateCommand(input.installSource, input.npmPrefix ?? null);
  return {
    action: "run-install",
    message: `upgrading reasonix ${input.current} \u2192 ${input.latest} (via ${input.installSource})`,
    command
  };
}
function buildUpdateCommand(source, npmPrefix) {
  switch (source) {
    case "npm":
      return npmPrefix ? ["npm", "--prefix", npmPrefix, "install", "-g", "reasonix@latest"] : ["npm", "install", "-g", "reasonix@latest"];
    case "bun":
      return ["bun", "add", "-g", "reasonix"];
    case "pnpm":
      return ["pnpm", "add", "-g", "reasonix@latest"];
    case "yarn":
      return ["yarn", "global", "add", "reasonix@latest"];
  }
}
function defaultSpawn(argv) {
  return new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), {
      stdio: "inherit",
      shell: process.platform === "win32"
    });
    child.once("error", reject);
    child.once("exit", (code) => resolve(code ?? 1));
  });
}
async function updateCommand(opts = {}) {
  const write = opts.write ?? ((m) => process.stdout.write(m));
  const exit = opts.exit ?? ((c) => process.exit(c));
  const fetchLatest = opts.fetchLatest ?? (() => getLatestVersion({ force: true }));
  const detectSource = opts.detectSource ?? (() => detectInstallSource());
  const detectPrefix = opts.detectPrefix ?? (() => detectNpmInstallPrefix());
  const doSpawn = opts.spawnInstall ?? defaultSpawn;
  write(`current: reasonix ${VERSION}
`);
  const latest = await fetchLatest();
  if (!latest) {
    write("could not reach registry.npmjs.org \u2014 check your network.\n");
    exit(1);
    return;
  }
  write(`latest:  reasonix ${latest}
`);
  const installSource = detectSource();
  const npmPrefix = installSource === "npm" ? detectPrefix() : null;
  const plan = planUpdate({ current: VERSION, latest, installSource, npmPrefix });
  write(`
${plan.message}
`);
  if (plan.action === "manual-hint") {
    exit(1);
    return;
  }
  if (plan.action !== "run-install" || !plan.command) return;
  if (opts.dryRun) {
    write(`(dry run) would run: ${plan.command.join(" ")}
`);
    return;
  }
  write(`
running: ${plan.command.join(" ")}
`);
  const code = await doSpawn(plan.command);
  if (code !== 0) {
    write(`
${plan.command[0]} exited with code ${code}. upgrade did not complete.
`);
    exit(code);
  }
}

export {
  MANUAL_UPDATE_COMMANDS,
  planUpdate,
  updateCommand
};
//# sourceMappingURL=chunk-SZ5XES2N.js.map