#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  SkillStore
} from "./chunk-J4MYMBJ7.js";

// src/core/event-redaction.ts
var SECRET_KEY_RE = /(secret|token|password|passphrase|api[-_]?key|authorization|cookie|credential|passwd|pwd)/i;
function redactEventValue(value) {
  return redactUnknown(value, null);
}
function redactUnknown(value, key) {
  if (Array.isArray(value)) return value.map((item) => redactUnknown(item, null));
  if (value && typeof value === "object") {
    const out = {};
    for (const [childKey, childValue] of Object.entries(value)) {
      out[childKey] = redactUnknown(childValue, childKey);
    }
    return out;
  }
  if (typeof value === "string") {
    if (key && SECRET_KEY_RE.test(key) || /^Bearer\s+/i.test(value)) return "[redacted]";
  }
  return value;
}

// src/core/eventize.ts
var Eventizer = class {
  nextId = 0;
  lastTurn = -1;
  nextToolSeq = 0;
  /** Tool calls announced via tool_call_delta but not yet dispatched. FIFO upgraded by tool_start. */
  preparingCallIds = [];
  /** Tool calls dispatched but not yet finished. FIFO popped by tool result. */
  inflightCallIds = [];
  /** Per-turn dedupe so each toolCallIndex emits exactly one tool.preparing. */
  announcedToolIdx = /* @__PURE__ */ new Set();
  consume(ev, ctx) {
    const out = [];
    if (ev.turn !== this.lastTurn) {
      this.lastTurn = ev.turn;
      this.announcedToolIdx.clear();
      out.push(this.turnStartedEvent(ev.turn, ctx));
    }
    switch (ev.role) {
      case "assistant_delta":
        if (ev.content) out.push(this.deltaEvent(ev.turn, "content", ev.content));
        if (ev.reasoningDelta) out.push(this.deltaEvent(ev.turn, "reasoning", ev.reasoningDelta));
        break;
      case "tool_call_delta": {
        const idx = ev.toolCallIndex;
        const name = ev.toolName;
        if (idx === void 0 || !name) break;
        const key = `${ev.turn}:${idx}`;
        if (this.announcedToolIdx.has(key)) break;
        this.announcedToolIdx.add(key);
        const callId = `tc-${++this.nextToolSeq}`;
        this.preparingCallIds.push(callId);
        out.push(this.toolPreparingEvent(ev.turn, callId, name));
        break;
      }
      case "assistant_final":
        out.push(this.finalEvent(ev));
        break;
      case "tool_start": {
        const callId = this.preparingCallIds.shift() ?? `tc-${++this.nextToolSeq}`;
        this.inflightCallIds.push(callId);
        out.push(this.toolIntentEvent(ev.turn, callId, ev.toolName ?? "", ev.toolArgs ?? ""));
        out.push(this.toolDispatchedEvent(ev.turn, callId));
        break;
      }
      case "tool": {
        const callId = this.inflightCallIds.shift() ?? `tc-orphan-${++this.nextToolSeq}`;
        const ok = !looksLikeToolError(ev.content, ev.toolName);
        out.push(this.toolResultEvent(ev.turn, callId, ok, ev.content, 0));
        break;
      }
      case "warning": {
        const classified = this.classifyWarning(ev);
        if (classified) out.push(classified);
        break;
      }
      case "error":
        out.push(
          this.errorEvent(ev.turn, ev.error ?? ev.content, ev.errorDetail?.recoverable ?? false, {
            name: ev.errorDetail?.name,
            code: ev.errorDetail?.code,
            phase: ev.errorDetail?.phase,
            retryable: ev.errorDetail?.retryable
          })
        );
        break;
      case "status":
        out.push(this.statusEvent(ev.turn, ev.content));
        break;
      // `done` / `branch_*` intentionally drop — no kernel-level event.
      default:
        break;
    }
    return out;
  }
  emitUserMessage(turn, text) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "user.message",
      text
    };
  }
  emitSlashInvoked(turn, name, args) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "slash.invoked",
      name,
      args
    };
  }
  emitSessionOpened(turn, name, resumedFromTurn) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "session.opened",
      name,
      resumedFromTurn
    };
  }
  emitSessionCompacted(turn, before, after, reason, replacementMessages) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "session.compacted",
      beforeMessages: before,
      afterMessages: after,
      reason,
      replacementMessages
    };
  }
  emitToolCall(turn, name, args) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.call",
      name,
      args: redactEventValue(args)
    };
  }
  emitToolConfirmAllow(turn, kind, payload) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.confirm.allow",
      kind,
      payload: redactEventValue(payload)
    };
  }
  emitToolConfirmDeny(turn, kind, payload, denyContext) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.confirm.deny",
      kind,
      payload: redactEventValue(payload),
      denyContext
    };
  }
  emitToolConfirmAlwaysAllow(turn, kind, payload, prefix) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.confirm.always_allow",
      kind,
      payload: redactEventValue(payload),
      prefix
    };
  }
  turnStartedEvent(turn, ctx) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "model.turn.started",
      model: ctx.model,
      reasoningEffort: ctx.reasoningEffort,
      prefixHash: ctx.prefixHash
    };
  }
  deltaEvent(turn, channel, text) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "model.delta",
      channel,
      text
    };
  }
  finalEvent(ev) {
    const usage = ev.stats ? {
      prompt_tokens: ev.stats.usage.promptTokens,
      completion_tokens: ev.stats.usage.completionTokens,
      total_tokens: ev.stats.usage.totalTokens,
      prompt_cache_hit_tokens: ev.stats.usage.promptCacheHitTokens,
      prompt_cache_miss_tokens: ev.stats.usage.promptCacheMissTokens
    } : {};
    const costUsd = ev.stats?.cost ?? 0;
    const out = {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn: ev.turn,
      type: "model.final",
      content: ev.content,
      // toolCalls land later via tool_start → tool.intent — not in this event.
      toolCalls: [],
      usage,
      costUsd
    };
    if (ev.forcedSummary) out.forcedSummary = true;
    return out;
  }
  toolPreparingEvent(turn, callId, name) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.preparing",
      callId,
      name
    };
  }
  toolIntentEvent(turn, callId, name, args) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.intent",
      callId,
      name,
      args
    };
  }
  toolDispatchedEvent(turn, callId) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.dispatched",
      callId
    };
  }
  toolResultEvent(turn, callId, ok, output, durationMs) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "tool.result",
      callId,
      ok,
      output,
      durationMs
    };
  }
  statusEvent(turn, text) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "status",
      text
    };
  }
  errorEvent(turn, message, recoverable, detail) {
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn,
      type: "error",
      message,
      recoverable,
      ...detail
    };
  }
  /** Pattern-match warning text since LoopEvent doesn't carry a typed kind. Returns null
   *  for low-severity warnings (self-correcting / counter messages); the UI surface drops
   *  them entirely instead of rendering noise. */
  classifyWarning(ev) {
    const c = ev.content;
    if (/\bauto-escalating to\b|\barmed\b.*pro|NEEDS_PRO/.test(c)) {
      return {
        id: ++this.nextId,
        ts: (/* @__PURE__ */ new Date()).toISOString(),
        turn: ev.turn,
        type: "policy.escalated",
        fromModel: "",
        toModel: "",
        reason: c.includes("armed") ? "user-request" : "self-report"
      };
    }
    if (/budget\b.*\$|\$\d.*\/\s*\$\d/.test(c)) {
      const blocked = /blocked|exceeded|refus/i.test(c);
      return {
        id: ++this.nextId,
        ts: (/* @__PURE__ */ new Date()).toISOString(),
        turn: ev.turn,
        type: blocked ? "policy.budget.blocked" : "policy.budget.warning",
        spentUsd: 0,
        capUsd: 0
      };
    }
    if (ev.severity === "low") return null;
    return {
      id: ++this.nextId,
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      turn: ev.turn,
      type: "warning",
      text: c,
      severity: ev.severity ?? "high"
    };
  }
};
function looksLikeToolError(content, _toolName) {
  if (!content) return false;
  if (content.startsWith("ERROR:")) return true;
  if (content.startsWith("[hook block]")) return true;
  if (/^\{"error"\s*:/.test(content)) return true;
  if (/\bConfirmationError:|\bNeedsConfirmationError\b/.test(content)) return true;
  return false;
}

// src/core/pause-policy.ts
function shouldAutoResolveCheckpoint(editMode) {
  return editMode === "auto" || editMode === "yolo";
}
function autoResolveVerdict(req, editMode) {
  if (req.kind === "plan_checkpoint" && shouldAutoResolveCheckpoint(editMode)) {
    return { type: "continue" };
  }
  if (req.kind === "path_access" && editMode === "yolo") {
    return { type: "run_once" };
  }
  if ((req.kind === "run_command" || req.kind === "run_background") && editMode === "yolo") {
    return { type: "run_once" };
  }
  return null;
}

// src/tools/skills.ts
function registerBuiltinSubagentTool(registry, store, subagentRunner, spec) {
  if (!store.read(spec.skillName)) return;
  registry.register({
    name: spec.toolName,
    description: spec.description,
    readOnly: true,
    parallelSafe: true,
    parameters: {
      type: "object",
      properties: {
        task: { type: "string", description: spec.taskDescription }
      },
      required: ["task"]
    },
    fn: async (args, ctx) => {
      if (!subagentRunner) {
        return JSON.stringify({
          error: `${spec.toolName}: no subagent runner is configured for this session \u2014 run inside \`reasonix code\`, or pass \`subagentRunner\` to \`registerSkillTools\`.`
        });
      }
      const task = typeof args.task === "string" ? args.task.trim() : "";
      if (!task) {
        return JSON.stringify({
          error: `${spec.toolName} requires a non-empty 'task' argument \u2014 describe the concrete question.`
        });
      }
      const skill = store.read(spec.skillName);
      if (!skill) {
        return JSON.stringify({
          error: `${spec.toolName}: built-in skill ${JSON.stringify(spec.skillName)} is no longer registered`
        });
      }
      if (skill.runAs !== "subagent") {
        return JSON.stringify({
          error: `${spec.toolName}: skill ${JSON.stringify(spec.skillName)} is overridden as inline; invoke it via run_skill instead.`
        });
      }
      return subagentRunner(skill, task, ctx?.signal);
    }
  });
}
function registerSkillTools(registry, opts = {}) {
  const store = new SkillStore({
    homeDir: opts.homeDir,
    projectRoot: opts.projectRoot,
    customSkillPaths: opts.customSkillPaths,
    disableBuiltins: opts.disableBuiltins,
    subagentModels: opts.subagentModels
  });
  const subagentRunner = opts.subagentRunner;
  const onSkillInstalled = opts.onSkillInstalled;
  const hasProjectScope = store.hasProjectScope();
  registry.register({
    name: "run_skill",
    description: "Invoke a user-defined playbook from the Skills index pinned in the system prompt. **For the built-in subagent skills (explore / research / review / security_review), prefer the dedicated top-level tools by the same name \u2014 they're cheaper to pick and produce the same result.** Pass `name` as the BARE skill identifier (e.g. 'my-custom-skill'), NOT the `[\u{1F9EC} subagent]` tag that appears after it in the index. Entries tagged `[\u{1F9EC} subagent]` spawn an isolated subagent \u2014 only the final distilled answer comes back. Plain skills are inlined: the body becomes a tool result you read and follow. For subagent skills, supply 'arguments' describing the concrete task \u2014 they'll be the only context the subagent has.",
    readOnly: true,
    parallelSafe: true,
    parameters: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Skill identifier as it appears in the pinned Skills index (e.g. 'explore', 'review', 'security-review'). Case-sensitive."
        },
        arguments: {
          type: "string",
          description: "Free-form arguments the skill should act on. For inline skills: appended to the body as an 'Arguments:' line; the skill's own instructions decide how to consume them. For `[\u{1F9EC} subagent]` skills: REQUIRED \u2014 becomes the entire task description the subagent receives, since it has no other context."
        }
      },
      required: ["name"]
    },
    fn: async (args, ctx) => {
      const raw = typeof args.name === "string" ? args.name.trim() : "";
      if (!raw) {
        return JSON.stringify({ error: "run_skill requires a 'name' argument" });
      }
      const stripped = raw.replace(/\[[^\]]*\]/g, " ").trim();
      const tokens = stripped.split(/\s+/).filter(Boolean);
      const name = tokens.find((t) => /^[a-zA-Z0-9]/.test(t)) ?? "";
      if (!name) {
        return JSON.stringify({
          error: "run_skill requires a 'name' argument",
          hint: `'${raw}' is just a marker/tag, not a skill name`
        });
      }
      const skill = store.read(name);
      if (!skill) {
        const available = store.list().map((s) => s.name).join(", ");
        return JSON.stringify({
          error: `unknown skill: ${JSON.stringify(name)}`,
          available: available || "(none \u2014 user has not defined any skills)"
        });
      }
      const rawArgs = typeof args.arguments === "string" ? args.arguments.trim() : "";
      if (skill.runAs === "subagent") {
        if (!subagentRunner) {
          return JSON.stringify({
            error: `run_skill: skill ${JSON.stringify(name)} is marked runAs=subagent but no subagent runner is configured for this session. Skill authors who need isolation should run inside reasonix code (or a library setup that passes subagentRunner to registerSkillTools).`
          });
        }
        if (!rawArgs) {
          return JSON.stringify({
            error: `run_skill: skill ${JSON.stringify(name)} is a subagent and requires 'arguments' \u2014 the subagent has no other context, so describe the concrete task in the arguments field.`
          });
        }
        return subagentRunner(skill, rawArgs, ctx?.signal);
      }
      const header = [
        `# Skill: ${skill.name}`,
        skill.description ? `> ${skill.description}` : "",
        `(scope: ${skill.scope} \xB7 ${skill.path})`
      ].filter(Boolean).join("\n");
      const argsBlock = rawArgs ? `

Arguments: ${rawArgs}` : "";
      const inner = `${header}

${skill.body}${argsBlock}`;
      return `<skill-pin name=${JSON.stringify(skill.name)}>
${inner}
</skill-pin>`;
    }
  });
  registerBuiltinSubagentTool(registry, store, subagentRunner, {
    toolName: "explore",
    skillName: "explore",
    description: "Run a focused read-only codebase investigation in an isolated subagent. **Use for broad survey questions across multiple files** \u2014 'find all places that X', 'how does Y work across the project', 'audit Z'. Returns one distilled answer with file:line citations. Chained `read_file` is the wrong tool for these \u2014 it bloats your context with raw file contents; `explore`'s reads + reasoning never enter your log.",
    taskDescription: "Concrete investigation question. The subagent has none of your context \u2014 write a self-contained prompt naming the symbol / pattern / behavior you want surveyed."
  });
  registerBuiltinSubagentTool(registry, store, subagentRunner, {
    toolName: "research",
    skillName: "research",
    description: "Combine web search + code reading in an isolated subagent. **Use when the answer needs both external reference and local verification** \u2014 'is X supported by lib Y in version Z', 'compare our impl against the spec', 'what's the canonical way to do Q'. Returns one synthesis citing code (file:line) and web (URL). Reads + searches stay in the subagent.",
    taskDescription: "Concrete research question. The subagent has none of your context \u2014 name the external thing to look up and the local code to compare against."
  });
  registerBuiltinSubagentTool(registry, store, subagentRunner, {
    toolName: "review",
    skillName: "review",
    description: "Review the pending changes (current branch diff) in an isolated subagent \u2014 flags correctness / security / missing-tests / hidden behavior per file:line. Read-only; you decide what to act on. Use before suggesting a PR-shaped change, or when you've finished a multi-step edit and want a second pass.",
    taskDescription: "What to focus the review on (e.g. 'focus on the auth changes' or 'general'). The subagent reads the diff itself."
  });
  registerBuiltinSubagentTool(registry, store, subagentRunner, {
    toolName: "security_review",
    skillName: "security-review",
    description: "Security-focused review of current branch diff in an isolated subagent \u2014 injection / authz / secrets / deserialization / path-traversal / crypto issues, severity-tagged. Use when shipping changes that touch auth, input parsing, file IO, or external requests. Read-only.",
    taskDescription: "Optional scope hint (e.g. 'focus on token handling in src/auth/') or 'full' for everything in the diff."
  });
  const installScopeDesc = hasProjectScope ? "'project' (default) writes to <repo>/.reasonix/skills/, scoped to this workspace only; 'global' writes to ~/.reasonix/skills/, available in every project." : "'global' (only option here \u2014 no project workspace) writes to ~/.reasonix/skills/.";
  registry.register({
    name: "install_skill",
    description: "Author and save a new skill \u2014 a reusable playbook future turns invoke via `run_skill`. Runnable immediately (same turn); appears in the pinned Skills index on next `/new` or launch. Skill bodies become prompts for future turns, so write what you'd want your future self to follow.",
    parameters: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Identifier \u2014 letters/digits/_/-/., 1-64 chars, starts alnum. Becomes the filename."
        },
        description: {
          type: "string",
          description: "\u2264120 char one-liner shown in the pinned Skills index \u2014 future agents read this to decide whether to invoke."
        },
        body: {
          type: "string",
          description: "Markdown playbook. For subagent skills, write the subagent's persona/rules \u2014 it gets no context besides `arguments` at runtime."
        },
        scope: {
          type: "string",
          enum: ["project", "global"],
          description: installScopeDesc
        },
        runAs: {
          type: "string",
          enum: ["inline", "subagent"],
          description: "inline (default) appends body to parent log. subagent spawns isolated child loop; only final answer returns (use for context-heavy work)."
        },
        model: {
          type: "string",
          description: "Optional `deepseek-*` model override for runAs=subagent. Ignored otherwise."
        },
        allowedTools: {
          type: "array",
          items: { type: "string" },
          description: "Optional tool allowlist for runAs=subagent (e.g. ['read_file','search_content'])."
        }
      },
      required: ["name", "description", "body"]
    },
    fn: async (args) => {
      const name = typeof args.name === "string" ? args.name.trim() : "";
      const description = typeof args.description === "string" ? args.description.replace(/[\r\n]+/g, " ").trim() : "";
      const body = typeof args.body === "string" ? args.body : "";
      if (!name) return JSON.stringify({ error: "install_skill requires a non-empty 'name'" });
      if (!description) {
        return JSON.stringify({
          error: "install_skill requires a non-empty 'description' \u2014 it is what appears in the Skills index and how future agents decide whether to invoke the skill"
        });
      }
      if (!body.trim()) {
        return JSON.stringify({
          error: "install_skill requires a non-empty 'body' \u2014 the playbook the skill executes when invoked"
        });
      }
      const scopeRaw = typeof args.scope === "string" ? args.scope.trim() : "";
      let scope;
      if (scopeRaw === "global") scope = "global";
      else if (scopeRaw === "project") scope = "project";
      else scope = hasProjectScope ? "project" : "global";
      if (scope === "project" && !hasProjectScope) {
        return JSON.stringify({
          error: "install_skill: scope='project' requires a workspace \u2014 run from `reasonix code`, or use scope='global'"
        });
      }
      const runAsRaw = typeof args.runAs === "string" ? args.runAs.trim() : "";
      const runAs = runAsRaw === "subagent" ? "subagent" : "inline";
      const fmLines = ["---", `name: ${name}`, `description: ${description}`];
      if (runAs === "subagent") {
        fmLines.push("runAs: subagent");
        const model = typeof args.model === "string" ? args.model.trim() : "";
        if (model) fmLines.push(`model: ${model}`);
        if (Array.isArray(args.allowedTools)) {
          const tools = args.allowedTools.filter((t) => typeof t === "string").map((t) => t.trim()).filter(Boolean);
          if (tools.length > 0) fmLines.push(`allowed-tools: ${tools.join(", ")}`);
        }
      }
      fmLines.push("---", "");
      const content = `${fmLines.join("\n")}${body.replace(/\s+$/, "")}
`;
      const result = store.createWithContent(name, scope, content);
      if ("error" in result) {
        return JSON.stringify({ error: result.error });
      }
      try {
        onSkillInstalled?.({ name, path: result.path, scope });
      } catch {
      }
      return JSON.stringify({
        ok: true,
        name,
        scope,
        path: result.path,
        runAs,
        note: "Skill is callable right now via run_skill({ name }). It will appear in the pinned Skills index after the next /new or launch."
      });
    }
  });
  return registry;
}

export {
  registerSkillTools,
  Eventizer,
  shouldAutoResolveCheckpoint,
  autoResolveVerdict
};
//# sourceMappingURL=chunk-GMQVINZK.js.map