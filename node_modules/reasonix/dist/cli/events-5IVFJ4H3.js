#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  readEventLogFile
} from "./chunk-J5XJHLWM.js";
import {
  eventLogPath
} from "./chunk-FB27YXPX.js";
import "./chunk-P5SUHDUQ.js";
import {
  t
} from "./chunk-U7G72DHQ.js";
import "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/core/reducers.ts
function emptyConversation() {
  return { messages: [], pendingToolCalls: [] };
}
function emptyBudget(capUsd = null) {
  return {
    spentUsd: 0,
    capUsd,
    promptTokens: 0,
    completionTokens: 0,
    cacheHitTokens: 0,
    cacheMissTokens: 0,
    warned: false,
    blocked: false
  };
}
function emptyPlan() {
  return { steps: [], body: null, submittedTurn: null };
}
function emptyWorkspace() {
  return { filesTouched: /* @__PURE__ */ new Map(), lastCheckpointId: null };
}
function emptyCapabilities() {
  return { tools: [] };
}
function emptyStatus() {
  return { current: null };
}
function emptySessionMeta() {
  return {
    name: null,
    openedAt: null,
    resumedFromTurn: null,
    currentTurn: 0,
    lastError: null
  };
}
function emptyProjections(capUsd = null) {
  return {
    conversation: emptyConversation(),
    budget: emptyBudget(capUsd),
    plan: emptyPlan(),
    workspace: emptyWorkspace(),
    capabilities: emptyCapabilities(),
    status: emptyStatus(),
    session: emptySessionMeta()
  };
}
var conversation = (v, ev) => {
  switch (ev.type) {
    case "user.message": {
      const msg = { role: "user", content: ev.text };
      return { ...v, messages: [...v.messages, msg] };
    }
    case "model.final": {
      const msg = { role: "assistant", content: ev.content };
      if (ev.toolCalls.length > 0) msg.tool_calls = [...ev.toolCalls];
      if (ev.reasoningContent !== void 0) msg.reasoning_content = ev.reasoningContent;
      return { ...v, messages: [...v.messages, msg] };
    }
    case "tool.intent":
      return {
        ...v,
        pendingToolCalls: [...v.pendingToolCalls, { callId: ev.callId, name: ev.name }]
      };
    case "tool.result": {
      const msg = { role: "tool", content: ev.output, tool_call_id: ev.callId };
      return {
        messages: [...v.messages, msg],
        pendingToolCalls: v.pendingToolCalls.filter((c) => c.callId !== ev.callId)
      };
    }
    case "tool.denied": {
      const msg = {
        role: "tool",
        content: `denied: ${ev.reason}`,
        tool_call_id: ev.callId
      };
      return {
        messages: [...v.messages, msg],
        pendingToolCalls: v.pendingToolCalls.filter((c) => c.callId !== ev.callId)
      };
    }
    case "session.compacted":
      return { messages: [...ev.replacementMessages], pendingToolCalls: [] };
    default:
      return v;
  }
};
var budget = (v, ev) => {
  switch (ev.type) {
    case "model.final": {
      const u = ev.usage;
      return {
        ...v,
        spentUsd: v.spentUsd + ev.costUsd,
        promptTokens: v.promptTokens + (u.prompt_tokens ?? 0),
        completionTokens: v.completionTokens + (u.completion_tokens ?? 0),
        cacheHitTokens: v.cacheHitTokens + (u.prompt_cache_hit_tokens ?? 0),
        cacheMissTokens: v.cacheMissTokens + (u.prompt_cache_miss_tokens ?? 0)
      };
    }
    case "policy.budget.warning":
      return { ...v, warned: true };
    case "policy.budget.blocked":
      return { ...v, blocked: true };
    default:
      return v;
  }
};
var plan = (v, ev) => {
  switch (ev.type) {
    case "plan.submitted": {
      const steps = ev.steps.map((s) => ({
        id: s.id,
        title: s.title,
        action: s.action,
        risk: s.risk,
        completed: false
      }));
      return { steps, body: ev.body, submittedTurn: ev.turn };
    }
    case "plan.step.completed": {
      if (!v.steps.some((s) => s.id === ev.stepId)) return v;
      return {
        ...v,
        steps: v.steps.map(
          (s) => s.id === ev.stepId ? { ...s, completed: true, notes: ev.notes } : s
        )
      };
    }
    default:
      return v;
  }
};
var workspace = (v, ev) => {
  switch (ev.type) {
    case "effect.file.touched": {
      const next = new Map(v.filesTouched);
      next.set(ev.path, ev.mode);
      return { ...v, filesTouched: next };
    }
    case "checkpoint.created":
      return { ...v, lastCheckpointId: ev.checkpointId };
    default:
      return v;
  }
};
var capabilities = (v, ev) => {
  switch (ev.type) {
    case "capability.registered": {
      const filtered = v.tools.filter((t2) => t2.name !== ev.name);
      return { tools: [...filtered, { name: ev.name, permission: ev.permission }] };
    }
    case "capability.removed":
      return { tools: v.tools.filter((t2) => t2.name !== ev.name) };
    default:
      return v;
  }
};
var STATUS_CLEARING = /* @__PURE__ */ new Set([
  "model.delta",
  "model.final",
  "tool.dispatched",
  "tool.result",
  "tool.denied",
  "error"
]);
var status = (v, ev) => {
  if (ev.type === "status") return { current: ev.text };
  if (STATUS_CLEARING.has(ev.type) && v.current !== null) return { current: null };
  return v;
};
var sessionMeta = (v, ev) => {
  let next = v;
  if (ev.turn > next.currentTurn) next = { ...next, currentTurn: ev.turn };
  switch (ev.type) {
    case "session.opened":
      return {
        ...next,
        name: ev.name,
        openedAt: ev.ts,
        resumedFromTurn: ev.resumedFromTurn
      };
    case "error":
      return { ...next, lastError: ev.message };
    default:
      return next;
  }
};
function apply(state, ev) {
  return {
    conversation: conversation(state.conversation, ev),
    budget: budget(state.budget, ev),
    plan: plan(state.plan, ev),
    workspace: workspace(state.workspace, ev),
    capabilities: capabilities(state.capabilities, ev),
    status: status(state.status, ev),
    session: sessionMeta(state.session, ev)
  };
}
function replay(events, capUsd = null) {
  let s = emptyProjections(capUsd);
  for (const ev of events) s = apply(s, ev);
  return s;
}

// src/cli/commands/events.ts
function eventsCommand(opts) {
  const path = eventLogPath(opts.name);
  let events = readEventLogFile(path);
  if (events.length === 0) {
    console.error(t("app.noEventsFor", { name: opts.name }));
    console.error(t("app.lookedAtFile", { path }));
    console.error(t("app.sidecarHint"));
    process.exit(1);
    return;
  }
  if (opts.type) events = events.filter((e) => e.type === opts.type);
  if (opts.since !== void 0 && Number.isFinite(opts.since)) {
    events = events.filter((e) => e.id >= opts.since);
  }
  if (opts.tail !== void 0 && Number.isFinite(opts.tail) && opts.tail > 0) {
    events = events.slice(-opts.tail);
  }
  if (opts.projection) {
    const p = replay(events);
    console.log(JSON.stringify(p, mapReplacer, 2));
    return;
  }
  if (opts.json) {
    for (const e of events) console.log(JSON.stringify(e));
    return;
  }
  console.log(`[events] ${opts.name}   ${events.length} event(s)   ${path}`);
  console.log("");
  for (const e of events) console.log(formatEvent(e));
}
function formatEvent(e) {
  const id = String(e.id).padStart(4);
  const turn = `t${e.turn}`.padEnd(4);
  const ts = e.ts.replace("T", " ").replace(/\.\d+Z$/, "");
  const type = e.type.padEnd(22);
  return `[${id}] ${turn} ${ts}  ${type}  ${detailsFor(e)}`;
}
function detailsFor(e) {
  switch (e.type) {
    case "user.message":
      return quote(e.text, 80);
    case "slash.invoked":
      return `/${e.name} ${e.args}`.trim();
    case "model.turn.started":
      return `model=${e.model} effort=${e.reasoningEffort} prefix=${e.prefixHash.slice(0, 8)}`;
    case "model.delta":
      return `${e.channel} ${quote(e.text, 60)}`;
    case "model.final": {
      const u = e.usage;
      const tokens = `in=${u.prompt_tokens ?? 0} out=${u.completion_tokens ?? 0}`;
      const tail = e.forcedSummary ? " [forcedSummary]" : "";
      return `cost=$${e.costUsd.toFixed(4)} ${tokens}${tail}`;
    }
    case "tool.intent":
      return `${e.callId} ${e.name} args=${truncate(e.args, 60)}`;
    case "tool.dispatched":
      return e.callId;
    case "tool.denied":
      return `${e.callId} reason=${e.reason}`;
    case "tool.result":
      return `${e.callId} ${e.ok ? "ok" : "err"} ${e.output.length}B${e.truncated ? " [trunc]" : ""}`;
    case "tool.call":
      return `${e.name} args=${truncate(JSON.stringify(e.args), 60)}`;
    case "tool.confirm.allow":
      return `${e.kind} ${quote(e.payload.command, 60)}`;
    case "tool.confirm.deny":
      return `${e.kind} ${quote(e.payload.command, 60)}${e.denyContext ? ` \u2014 ${truncate(e.denyContext, 40)}` : ""}`;
    case "tool.confirm.always_allow":
      return `${e.kind} ${quote(e.payload.command, 60)} prefix=${truncate(e.prefix, 30)}`;
    case "effect.file.touched":
      return `${e.mode} ${e.path} (${e.bytes}B)`;
    case "effect.memory.written":
      return `${e.scope}:${e.key}`;
    case "plan.submitted":
      return `${e.steps.length} step(s)`;
    case "plan.step.completed":
      return `${e.stepId}${e.title ? ` \u2014 ${e.title}` : ""}`;
    case "checkpoint.created":
      return `${e.checkpointId} "${e.name}" ${e.fileCount} file(s) ${e.bytes}B`;
    case "checkpoint.restored":
      return `${e.checkpointId} restored=${e.restored} removed=${e.removed} skipped=${e.skipped}`;
    case "hook.fired":
      return `${e.phase} ${e.hookName} \u2192 ${e.outcome}`;
    case "policy.budget.warning":
      return `$${e.spentUsd.toFixed(4)} / $${e.capUsd.toFixed(2)}`;
    case "policy.budget.blocked":
      return `$${e.spentUsd.toFixed(4)} / $${e.capUsd.toFixed(2)} BLOCKED`;
    case "policy.escalated":
      return `${e.fromModel} \u2192 ${e.toModel} (${e.reason})${e.rationale ? ` "${e.rationale}"` : ""}`;
    case "session.opened":
      return `${e.name} resumed-from-turn=${e.resumedFromTurn}`;
    case "session.compacted":
      return `${e.beforeMessages} \u2192 ${e.afterMessages} msgs (${e.reason})`;
    case "capability.registered":
      return `${e.name} ${e.permission}`;
    case "capability.removed":
      return e.name;
    case "status":
      return quote(e.text, 80);
    case "error":
      return `${e.recoverable ? "[recoverable] " : ""}${quote(e.message, 80)}`;
    default:
      return "";
  }
}
function quote(s, max) {
  const flat = s.replace(/\s+/g, " ").trim();
  return flat.length <= max ? `"${flat}"` : `"${flat.slice(0, max - 1)}\u2026"`;
}
function truncate(s, max) {
  return s.length <= max ? s : `${s.slice(0, max - 1)}\u2026`;
}
function mapReplacer(_key, value) {
  if (value instanceof Map) return Object.fromEntries(value);
  if (value instanceof Set) return [...value];
  return value;
}
export {
  eventsCommand
};
//# sourceMappingURL=events-5IVFJ4H3.js.map