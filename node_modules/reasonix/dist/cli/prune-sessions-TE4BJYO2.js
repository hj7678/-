#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  listSessions,
  pruneStaleSessions
} from "./chunk-P5SUHDUQ.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/cli/commands/prune-sessions.ts
function pruneSessionsCommand(opts) {
  const days = opts.days ?? 90;
  if (!Number.isFinite(days) || days < 1) {
    console.error(t("sessions.daysInvalid", { days }));
    process.exit(1);
  }
  if (opts.dryRun) {
    const cutoff = Date.now() - days * 24 * 60 * 60 * 1e3;
    const stale = listSessions().filter((s) => s.mtime.getTime() < cutoff);
    if (stale.length === 0) {
      console.log(t("sessions.noIdleSessions", { days }));
      return;
    }
    console.log(t("sessions.wouldPrune", { count: stale.length, days }));
    for (const s of stale) {
      console.log(`  ${s.name}`);
    }
    console.log("");
    console.log(t("sessions.dryRunHint"));
    return;
  }
  const removed = pruneStaleSessions(days);
  if (removed.length === 0) {
    console.log(t("sessions.noIdleSessions", { days }));
    return;
  }
  console.log(t("sessions.prunedCount", { count: removed.length, days }));
  for (const name of removed) {
    console.log(`  ${name}`);
  }
}
export {
  pruneSessionsCommand
};
//# sourceMappingURL=prune-sessions-TE4BJYO2.js.map