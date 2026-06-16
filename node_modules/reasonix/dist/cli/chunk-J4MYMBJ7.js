#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  t
} from "./chunk-U7G72DHQ.js";
import {
  loadResolvedSkillPaths,
  memoryTypeDefaults,
  resolveSkillPaths
} from "./chunk-GCNBIWK7.js";

// src/memory/project.ts
import { existsSync, readFileSync, statSync } from "fs";
import { basename, join } from "path";
var PROJECT_MEMORY_FILE = "REASONIX.md";
var PROJECT_MEMORY_FILES = [
  "REASONIX.md",
  ".claude/CLAUDE.md",
  "CLAUDE.md",
  "AGENTS.md",
  "AGENT.md"
];
var PROJECT_MEMORY_MAX_CHARS = 8e3;
var FOREIGN_PLATFORM_FILE_MARKERS = ["SOUL.md", "PERSONA.md"];
function detectForeignAgentPlatform(rootDir) {
  const hits = [];
  for (const name of FOREIGN_PLATFORM_FILE_MARKERS) {
    if (existsSync(join(rootDir, name))) hits.push(name);
  }
  if (isDir(join(rootDir, "skills")) && isDir(join(rootDir, "memories"))) {
    hits.push("skills/ + memories/");
  }
  return hits.length > 0 ? hits : null;
}
function isDir(path) {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}
function findProjectMemoryPath(rootDir) {
  for (const name of PROJECT_MEMORY_FILES) {
    const path = join(rootDir, name);
    if (existsSync(path)) return path;
  }
  return null;
}
function resolveProjectMemoryWritePath(rootDir) {
  return findProjectMemoryPath(rootDir) ?? join(rootDir, PROJECT_MEMORY_FILE);
}
function readProjectMemory(rootDir) {
  const path = findProjectMemoryPath(rootDir);
  if (!path) return null;
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const originalChars = trimmed.length;
  const truncated = originalChars > PROJECT_MEMORY_MAX_CHARS;
  const content = truncated ? `${trimmed.slice(0, PROJECT_MEMORY_MAX_CHARS)}
\u2026 (truncated ${originalChars - PROJECT_MEMORY_MAX_CHARS} chars)` : trimmed;
  return { path, content, originalChars, truncated };
}
function memoryEnabled() {
  const env = process.env.REASONIX_MEMORY;
  if (env === "off" || env === "false" || env === "0") return false;
  return true;
}
function applyProjectMemory(basePrompt, rootDir) {
  if (!memoryEnabled()) return basePrompt;
  const mem = readProjectMemory(rootDir);
  if (!mem) return basePrompt;
  const filename = basename(mem.path);
  return `${basePrompt}

# Project memory (${filename})

The user pinned these notes about this project \u2014 treat them as authoritative context for every turn:

\`\`\`
${mem.content}
\`\`\`
`;
}

// src/prompt-fragments.ts
var TUI_FORMATTING_RULES = `Formatting (rendered in a TUI with a real markdown renderer):
- Tabular data \u2192 GitHub-Flavored Markdown tables with ASCII pipes (\`| col | col |\` header + \`| --- | --- |\` separator). Never use Unicode box-drawing characters (\u2502 \u2500 \u253C \u250C \u2510 \u2514 \u2518 \u251C \u2524) \u2014 they look intentional but break terminal word-wrap and render as garbled columns at narrow widths.
- Keep table cells short (one phrase each). If a cell needs a paragraph, use bullets below the table instead.
- Code, file paths with line ranges, and shell commands \u2192 fenced code blocks (\`\`\`).
- Do NOT draw decorative frames around content with \`\u250C\u2500\u2500\u2510 \u2502 \u2514\u2500\u2500\u2518\` characters. The renderer adds its own borders; extra ASCII art adds noise and shatters at narrow widths.
- For flow charts and diagrams: a plain bullet list with \`\u2192\` or \`\u2193\` between steps. Don't try to draw boxes-and-arrows in ASCII; it never survives word-wrap.`;
function escalationContract(modelId) {
  if (modelId === "deepseek-v4-pro") {
    return `Cost-aware escalation note: you are running on \`${modelId}\` \u2014 the escalation tier. There is no higher tier to escalate to, so the \`<<<NEEDS_PRO>>>\` marker is a no-op for you; deliver the strongest answer you can directly. If asked which model you are, answer \`${modelId}\`.`;
  }
  return `Cost-aware escalation (you are running on \`${modelId}\`):

If a task CLEARLY exceeds what this tier can do well \u2014 complex cross-file architecture refactors, subtle concurrency / security / correctness invariants you can't resolve with confidence, or a design trade-off you'd be guessing at \u2014 output the marker as the FIRST line of your response (nothing before it, not even whitespace on a separate line). This aborts the current call and retries this turn on deepseek-v4-pro, one shot.

Two accepted forms:
- \`<<<NEEDS_PRO>>>\` \u2014 bare marker, no rationale.
- \`<<<NEEDS_PRO: <one-sentence reason>>>>\` \u2014 preferred. The reason text appears in the user-visible warning ("\u21E7 flash requested escalation \u2014 <your reason>"), so they understand WHY a more expensive call is happening. Keep it under ~150 chars, no newlines, no nested \`>\` characters. Examples: \`<<<NEEDS_PRO: cross-file refactor across 6 modules with circular imports>>>\` or \`<<<NEEDS_PRO: subtle session-token race; flash would likely miss the locking invariant>>>\`.

Do NOT emit any other content in the same response when you request escalation. Use this sparingly: normal tasks \u2014 reading files, small edits, clear bug fixes, straightforward feature additions \u2014 stay on this tier. Request escalation ONLY when you would otherwise produce a guess or a visibly-mediocre answer. If in doubt, attempt the task here first; the system also escalates automatically if you hit 3+ repair / SEARCH-mismatch errors in a single turn (the user sees a typed breakdown). If asked which model you are, answer \`${modelId}\`.`;
}
var ESCALATION_CONTRACT = escalationContract("deepseek-v4-flash");
var NEGATIVE_CLAIM_RULE = `Negative claims ("X is missing", "Y isn't implemented", "there's no Z") are the #1 hallucination shape. They feel safe to write because no citation seems possible \u2014 but that's exactly why you must NOT write them on instinct.

If you have a search tool (\`search_content\`, \`grep\`, web search), call it FIRST before asserting absence:
- Returns matches \u2192 you were wrong; correct yourself and cite the matches.
- Returns nothing \u2192 state the absence WITH the search query as evidence: \`No callers of \\\`foo()\\\` found (search_content "foo").\`

If you have no search tool, qualify hard: "I haven't verified \u2014 this is a guess." Never assert absence with fake authority.`;

// src/skills.ts
import {
  constants,
  existsSync as existsSync2,
  mkdirSync,
  readFileSync as readFileSync2,
  readdirSync,
  statSync as statSync2,
  writeFileSync
} from "fs";
import { accessSync } from "fs";
import { homedir } from "os";
import { dirname, isAbsolute, join as join2, resolve } from "path";

// src/frontmatter.ts
var KEY_RE = /^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$/;
var FORBIDDEN_KEYS = /* @__PURE__ */ new Set(["__proto__", "constructor", "prototype"]);
function stripQuotes(s) {
  if (s.length < 2) return s;
  const first = s[0];
  const last = s[s.length - 1];
  if (first === '"' && last === '"' || first === "'" && last === "'") {
    return s.slice(1, -1);
  }
  return s;
}
function parseFrontmatter(raw) {
  const stripped = raw.charCodeAt(0) === 65279 ? raw.slice(1) : raw;
  const lines = stripped.split(/\r?\n/);
  if (lines[0] !== "---") return { data: {}, body: stripped };
  const end = lines.indexOf("---", 1);
  if (end < 0) return { data: {}, body: stripped };
  const entries = /* @__PURE__ */ new Map();
  let currentKey = null;
  for (let i = 1; i < end; i++) {
    const line = lines[i] ?? "";
    if (line.trim() === "") {
      currentKey = null;
      continue;
    }
    const m = line.match(KEY_RE);
    if (m?.[1] && !FORBIDDEN_KEYS.has(m[1])) {
      currentKey = m[1];
      entries.set(currentKey, (m[2] ?? "").trim());
    } else if (currentKey) {
      const cont = line.trim();
      const prev = entries.get(currentKey) ?? "";
      entries.set(currentKey, prev ? `${prev} ${cont}` : cont);
    }
  }
  const data = /* @__PURE__ */ Object.create(null);
  for (const [k, v] of entries) {
    if (FORBIDDEN_KEYS.has(k)) continue;
    data[k] = stripQuotes(v);
  }
  return {
    data,
    body: lines.slice(end + 1).join("\n").replace(/^\n+/, "")
  };
}

// src/skills.ts
var SKILLS_DIRNAME = "skills";
var SKILL_FILE = "SKILL.md";
var SKILLS_INDEX_MAX_CHARS = 4e3;
var VALID_SKILL_NAME = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/;
function validateSkillFrontmatter(raw) {
  const { data } = parseFrontmatter(raw);
  const desc = (data.description ?? "").trim();
  if (!desc) {
    return {
      error: `skill frontmatter is missing a non-empty "description:" line \u2014 without it the skill will not appear in the model's skills index`
    };
  }
  return { ok: true };
}
function isValidSkillName(name) {
  return VALID_SKILL_NAME.test(name);
}
function parseAllowedTools(raw) {
  if (raw === void 0) return void 0;
  const names = raw.split(",").map((s) => s.trim()).filter(Boolean);
  return names.length > 0 ? Object.freeze(names) : void 0;
}
function subagentModelForPreset(preset) {
  return preset === "pro" ? "deepseek-v4-pro" : "deepseek-v4-flash";
}
var SkillStore = class {
  homeDir;
  projectRoot;
  customSkillPaths;
  disableBuiltins;
  subagentModels;
  constructor(opts = {}) {
    this.homeDir = opts.homeDir ?? homedir();
    this.projectRoot = opts.projectRoot ? resolve(opts.projectRoot) : void 0;
    const baseDir = this.projectRoot ?? process.cwd();
    this.customSkillPaths = dedupePaths(
      opts.customSkillPaths?.map((p) => resolveCustomSkillPath(p, baseDir, this.homeDir)) ?? []
    );
    this.disableBuiltins = opts.disableBuiltins === true;
    this.subagentModels = opts.subagentModels ?? {};
  }
  /** True iff this store was configured with a project root. */
  hasProjectScope() {
    return this.projectRoot !== void 0;
  }
  /** Project scope first so per-repo skill overrides custom/global entries with the same name. */
  roots() {
    const out = [];
    if (this.projectRoot) {
      out.push({
        dir: join2(this.projectRoot, ".reasonix", SKILLS_DIRNAME),
        scope: "project"
      });
      out.push({
        dir: join2(this.projectRoot, ".agents", SKILLS_DIRNAME),
        scope: "project"
      });
      out.push({
        dir: join2(this.projectRoot, ".claude", SKILLS_DIRNAME),
        scope: "project"
      });
    }
    for (const dir of this.customSkillPaths) out.push({ dir, scope: "custom" });
    out.push({ dir: join2(this.homeDir, ".reasonix", SKILLS_DIRNAME), scope: "global" });
    out.push({ dir: join2(this.homeDir, ".agents", SKILLS_DIRNAME), scope: "global" });
    out.push({ dir: join2(this.homeDir, ".claude", SKILLS_DIRNAME), scope: "global" });
    return out.map((root, priority) => ({ ...root, priority, status: skillPathStatus(root.dir) }));
  }
  customRoots() {
    return this.roots().filter((root) => root.scope === "custom");
  }
  /** Higher-priority root wins on collision (project > custom > global > builtin); sorted for stable prefix hash. */
  list() {
    const byName = /* @__PURE__ */ new Map();
    for (const { dir, scope, status } of this.roots()) {
      if (status !== "ok") continue;
      let entries;
      try {
        entries = readdirSync(dir, { withFileTypes: true });
      } catch {
        continue;
      }
      for (const entry of entries) {
        const skill = this.readEntry(dir, scope, entry);
        if (!skill) continue;
        if (!byName.has(skill.name)) byName.set(skill.name, skill);
      }
    }
    if (!this.disableBuiltins) {
      for (const skill of BUILTIN_SKILLS) {
        if (!byName.has(skill.name)) byName.set(skill.name, skill);
      }
    }
    return [...byName.values()].map((s) => this.applyModelOverride(s)).sort((a, b) => a.name.localeCompare(b.name));
  }
  /** Apply `subagentModels` config override on top of frontmatter `model:`. Inline skills are unaffected. */
  applyModelOverride(skill) {
    if (skill.runAs !== "subagent") return skill;
    const override = this.subagentModels[skill.name];
    if (!override) return skill;
    return { ...skill, model: subagentModelForPreset(override) };
  }
  /** Scaffold a new skill stub at the chosen scope. Refuses to overwrite. */
  create(name, scope) {
    return this.createWithContent(name, scope, skillStubBody(name));
  }
  /** Like `create` but writes caller-supplied file contents instead of the stub — used by the scaffold tool. */
  createWithContent(name, scope, content) {
    if (!isValidSkillName(name)) {
      return { error: `invalid skill name: "${name}" \u2014 use letters, digits, _, -, .` };
    }
    if (scope === "project" && !this.projectRoot) {
      return { error: "project scope requires a workspace \u2014 run from `reasonix code`" };
    }
    const root = scope === "project" ? join2(this.projectRoot ?? "", ".reasonix", SKILLS_DIRNAME) : join2(this.homeDir, ".reasonix", SKILLS_DIRNAME);
    const flat = join2(root, `${name}.md`);
    const folder = join2(root, name, SKILL_FILE);
    if (existsSync2(folder)) {
      return { error: `skill "${name}" already exists at ${folder}` };
    }
    mkdirSync(dirname(flat), { recursive: true });
    try {
      writeFileSync(flat, content, { encoding: "utf8", flag: "wx" });
    } catch (err) {
      if (err.code === "EEXIST") {
        return { error: `skill "${name}" already exists at ${flat}` };
      }
      throw err;
    }
    return { path: flat };
  }
  /** Resolve one skill by name. Returns `null` if not found or malformed. */
  read(name) {
    if (!isValidSkillName(name)) return null;
    for (const { dir, scope, status } of this.roots()) {
      if (status !== "ok") continue;
      const dirCandidate = join2(dir, name, SKILL_FILE);
      if (existsSync2(dirCandidate) && statSync2(dirCandidate).isFile()) {
        return this.parse(dirCandidate, name, scope);
      }
      const flatCandidate = join2(dir, `${name}.md`);
      if (existsSync2(flatCandidate) && statSync2(flatCandidate).isFile()) {
        return this.parse(flatCandidate, name, scope);
      }
    }
    if (!this.disableBuiltins) {
      for (const skill of BUILTIN_SKILLS) {
        if (skill.name === name) return skill;
      }
    }
    return null;
  }
  readEntry(dir, scope, entry) {
    if (entry.isDirectory()) {
      if (!isValidSkillName(entry.name)) return null;
      const file = join2(dir, entry.name, SKILL_FILE);
      if (!existsSync2(file)) return null;
      return this.parse(file, entry.name, scope);
    }
    if (entry.isFile() && entry.name.endsWith(".md")) {
      const stem = entry.name.slice(0, -3);
      if (!isValidSkillName(stem)) return null;
      return this.parse(join2(dir, entry.name), stem, scope);
    }
    return null;
  }
  parse(path, stem, scope) {
    let raw;
    try {
      raw = readFileSync2(path, "utf8");
    } catch {
      return null;
    }
    const { data, body } = parseFrontmatter(raw);
    const name = data.name && isValidSkillName(data.name) ? data.name : stem;
    const description = (data.description ?? "").trim();
    if (!description) {
      console.warn(
        `[skills] "${name}" at ${path} has no description: \u2014 it will be loaded but won't appear in the skills index.`
      );
    }
    return {
      name,
      description,
      body: body.trim(),
      scope,
      path,
      allowedTools: parseAllowedTools(data["allowed-tools"]),
      runAs: parseRunAs(data.runAs, data.context, data.agent),
      model: data.model?.startsWith("deepseek-") ? data.model : void 0
    };
  }
};
function dedupePaths(paths) {
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  for (const path of paths) {
    const key = process.platform === "win32" ? path.toLowerCase() : path;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(path);
  }
  return out;
}
function resolveCustomSkillPath(path, baseDir, homeDir) {
  const trimmed = path.trim();
  const expanded = trimmed === "~" ? homeDir : trimmed.startsWith("~/") || trimmed.startsWith("~\\") ? join2(homeDir, trimmed.slice(2)) : trimmed;
  return resolve(isAbsolute(expanded) ? expanded : join2(baseDir, expanded));
}
function skillPathStatus(dir) {
  try {
    const stat = statSync2(dir);
    if (!stat.isDirectory()) return "not-directory";
    accessSync(dir, constants.R_OK);
    return "ok";
  } catch (err) {
    const code = err.code;
    if (code === "ENOENT") return "missing";
    return "unreadable";
  }
}
function parseRunAs(raw, context, agent) {
  if (raw?.trim() === "subagent") return "subagent";
  if (context?.trim().toLowerCase() === "fork") return "subagent";
  if (agent?.trim()) return "subagent";
  return "inline";
}
function skillStubBody(name) {
  return `---
name: ${name}
description: One-liner \u2014 what does this skill do?
---

# ${name}

Replace this body with the playbook the model should follow when this skill is invoked.

Tips:
- Reference tools by name (run_command, edit_file, search_content, ...)
- Add \`runAs: subagent\` to frontmatter to spawn an isolated subagent loop
- Add \`allowed-tools: read_file, search_content\` to scope a subagent's tools
`;
}
function skillDescription(s) {
  if (s.scope !== "builtin") return s.description;
  const key = s.name === "security-review" ? "securityReview" : s.name;
  return t(`builtinSkills.${key}`);
}
function skillIndexLine(s) {
  const safeDesc = skillDescription(s).replace(/\n/g, " ").trim();
  const tag = s.runAs === "subagent" ? " [\u{1F9EC} subagent]" : "";
  const max = 130 - s.name.length - tag.length;
  const clipped = safeDesc.length > max ? `${safeDesc.slice(0, Math.max(1, max - 1))}\u2026` : safeDesc;
  return clipped ? `- ${s.name}${tag} \u2014 ${clipped}` : `- ${s.name}${tag}`;
}
var MISSING_DESCRIPTION_PLACEHOLDER = '(no description \u2014 frontmatter is missing a "description:" line; tell the user to add one)';
function applySkillsIndex(basePrompt, opts = {}) {
  const store = new SkillStore(opts);
  const skills = store.list();
  if (skills.length === 0) return basePrompt;
  const lines = skills.map(
    (s) => skillIndexLine(s.description ? s : { ...s, description: MISSING_DESCRIPTION_PLACEHOLDER })
  );
  const joined = lines.join("\n");
  const truncated = joined.length > SKILLS_INDEX_MAX_CHARS ? `${joined.slice(0, SKILLS_INDEX_MAX_CHARS)}
\u2026 (truncated ${joined.length - SKILLS_INDEX_MAX_CHARS} chars)` : joined;
  return [
    basePrompt,
    "",
    "# Skills \u2014 playbooks you can invoke",
    "",
    'One-liner index. Each entry is either a built-in or a user-authored playbook. Call `run_skill({ name: "<skill-name>", arguments: "<task>" })` \u2014 the `name` is JUST the skill identifier (e.g. `"explore"`), NOT the `[\u{1F9EC} subagent]` tag that appears after it. Entries tagged `[\u{1F9EC} subagent]` spawn an **isolated subagent** \u2014 its tool calls and reasoning never enter your context, only its final answer does. Use subagent skills for tasks that would otherwise flood your context (deep exploration, multi-step research, anything where you only need the conclusion). Plain skills are inlined: their body becomes a tool result you read and act on directly. The user can also invoke a skill via `/skill <name>`.',
    "",
    "```",
    truncated,
    "```"
  ].join("\n");
}
var BUILTIN_EXPLORE_BODY = `You are running as an exploration subagent. Your job is to investigate the codebase the parent agent pointed you at, then return one focused, distilled answer.

How to operate:
- Use read_file, search_files, search_content, directory_tree, list_directory, get_file_info as your primary tools. Stay read-only.
- For "find all places that call / reference / use X" questions, use \`search_content\` (content grep) \u2014 NOT \`search_files\` (which only matches file names). This is the most common subagent mistake; using the wrong tool gives empty results and you waste your iter budget chasing a phantom.
- Cast a wide net first (search_content for symbol references, directory_tree for structure) to map the territory; then read the 3-10 most relevant files in full.
- Don't read every file \u2014 be selective. Aim for breadth on the first pass, depth only where the question demands it.
- Stop exploring as soon as you can answer the question. The parent doesn't see your tool calls, so over-exploration is pure waste.

Your final answer:
- One paragraph (or a few short bullets). Lead with the conclusion.
- Cite specific file paths + line ranges when they support the answer.
- If the question can't be answered from what you found, say so plainly and suggest where to look next.
- No follow-up offers, no "let me know if you need more." The parent will ask again if they need more.

${NEGATIVE_CLAIM_RULE}

${TUI_FORMATTING_RULES}

The 'task' the parent gave you is the question you must answer. Treat any other reading of it as scope creep.`;
var BUILTIN_RESEARCH_BODY = `You are running as a research subagent. Your job is to gather information from code AND the web, synthesize it, and return one focused conclusion.

How to operate:
- Combine code reading (read_file, search_files) with web tools (web_search, web_fetch) as appropriate to the question.
- For "how does X work" / "is Y supported" questions: web first to find the canonical reference, then verify against the local code.
- For "what's our policy on Z" / "where do we use Q": local code first, web only if you need to compare against external standards.
- Cap yourself at ~10 tool calls. If you can't converge in 10, return what you have plus a note about what's missing.

Your final answer:
- One paragraph (or short bullets). Lead with the conclusion.
- Cite both code (file:line) AND web sources (URL) when they back the answer.
- Distinguish "I verified this in code" from "I read this on a docs page" \u2014 the parent will trust the former more.
- If the answer is uncertain, say so. Don't invent confidence.

${NEGATIVE_CLAIM_RULE}

${TUI_FORMATTING_RULES}

The 'task' the parent gave you is the research question. Stay on it.`;
var BUILTIN_REVIEW_BODY = `You are running as a code-review subagent. Your job is to inspect the changes the user is about to ship \u2014 usually the current git branch vs its upstream \u2014 and produce a focused review the parent can hand back to the user.

How to operate:
- Default scope: the current branch's diff vs the default branch. If the user's task names a specific commit range or files, honor that instead.
- Discover scope first: \`run_command git status\`, \`git diff --stat\`, \`git log --oneline\` to see what changed. Then \`git diff\` (or \`git diff <base>...HEAD\`) for the actual hunks.
- Read the touched files (\`read_file\`) when the diff alone doesn't carry enough context \u2014 function signatures, surrounding invariants, callers.
- For "any callers depending on this?" questions: \`search_content\` against the symbol BEFORE asserting impact.
- Stay read-only. Never \`run_command git commit\`, never write files, never propose SEARCH/REPLACE blocks. The parent decides whether to act on your findings.
- Cap yourself at ~12 tool calls. If the diff is too big to review in one pass, pick the riskiest 2-3 files and say so explicitly.

What to look for, in priority order:
1. **Correctness bugs** \u2014 off-by-one, null/undefined handling, race conditions, wrong sign / wrong operator, edge cases the code doesn't handle.
2. **Security** \u2014 injection (SQL, shell, path traversal), secrets in code, missing authz checks, unsafe deserialization.
3. **Behavior changes the diff hides** \u2014 renames that miss callers, removed branches that were load-bearing, error-handling that now swallows what used to surface.
4. **Tests** \u2014 does the change have tests for the new behavior? Are existing tests still meaningful, or did the change make them tautological?
5. **Style + consistency** \u2014 only flag deviations that matter (unsafe \`any\`, missing types in TypeScript, inconsistent error shape). Don't pile on cosmetic nits if the substance is clean.

Your final answer:
- Lead with a one-sentence verdict: "ship as-is" / "minor nits, OK to ship after" / "blocking issues, do not ship".
- Then a short bulleted list of issues, each with: file:line citation + the problem in one sentence + what to change.
- Group by severity if you have more than 4 items: **Blocking**, **Should-fix**, **Nits**.
- If everything looks clean, say so plainly. Don't manufacture concerns.

${NEGATIVE_CLAIM_RULE}

${TUI_FORMATTING_RULES}

The 'task' the parent gave you describes WHAT to review (a branch, a file set, or "the pending changes"). Stay on it; don't redesign the feature.`;
var BUILTIN_SECURITY_REVIEW_BODY = `You are running as a security-review subagent. Your job is to inspect the changes the user is about to ship \u2014 usually the current git branch vs its upstream \u2014 through a security lens specifically, and report exploitable issues.

How to operate:
- Default scope: the current branch's diff vs the default branch. If the user names a different range or a directory, honor that.
- Discover scope first: \`git status\`, \`git diff --stat\`, \`git diff <base>...HEAD\`. Read touched files (\`read_file\`) when the diff alone doesn't carry security context \u2014 auth checks, input validation, the actual handler that calls into the changed function.
- Use \`search_content\` to verify "is this user-controlled input ever sanitized later?" / "are there other call sites that depend on this validation?" before asserting impact.
- Stay read-only. Never write, never run destructive commands, never propose SEARCH/REPLACE blocks. The parent decides what to act on.
- Cap yourself at ~12 tool calls. If the diff is too big, focus on the riskiest 2-3 files and say so explicitly.

Threat model \u2014 flag with severity:

**CRITICAL** (do-not-ship):
- SQL / NoSQL / shell / template injection \u2014 user input concatenated into a query, command, or template without parameterization.
- Path traversal \u2014 user-controlled filenames touching the filesystem without canonicalization + sandbox check.
- Authentication / authorization missing \u2014 endpoints / actions that should require a session check but don't.
- Hardcoded secrets \u2014 API keys, passwords, signing tokens visible in the diff.
- Deserialization of untrusted input \u2014 \`pickle.loads\`, \`yaml.load\` (non-safe), \`eval\`, \`Function()\`, \`unserialize()\`.
- Cryptographic mistakes \u2014 homemade crypto, weak hashes (MD5/SHA-1) for passwords, missing IVs, ECB mode, predictable nonces.

**HIGH**:
- XSS \u2014 user input rendered into HTML without escaping (or wrong escaping context).
- SSRF \u2014 fetching URLs from user input without an allowlist.
- Race conditions in security-relevant code \u2014 TOCTOU on auth/file checks.
- Open redirects \u2014 user-controlled URL passed to a redirect helper.
- Insufficient logging on security events (login failure, permission denial) \u2014 only flag if the codebase clearly DOES log elsewhere.

**MEDIUM**:
- Verbose error messages leaking internal paths / stack traces / SQL.
- Missing rate limiting on a credential / token endpoint.
- Cross-origin / cookie-flag issues (missing \`Secure\` / \`HttpOnly\` / \`SameSite\`).

Things to NOT pile on (out of scope here \u2014 the regular /review covers them):
- Style, formatting, naming.
- Performance, refactor opportunities, test coverage gaps that aren't security-relevant.
- "Should be a constant" / "extract this helper" \u2014 irrelevant to ship-blocking.

Your final answer:
- Lead with a one-sentence verdict: "no security issues found", "minor concerns", or "blocking issues".
- Then a list grouped by severity. Each item: file:line + 1-sentence threat + 1-sentence fix direction (no full SEARCH/REPLACE \u2014 the user / parent agent will write that).
- If clean, say so plainly. Don't manufacture findings.

${NEGATIVE_CLAIM_RULE}

${TUI_FORMATTING_RULES}

The 'task' the parent gave you names what to review. Stay on it; don't redesign the feature.`;
var BUILTIN_TEST_BODY = `You are running as the parent agent \u2014 this skill is INLINED, not a subagent. The user invoked /test (or asked you to "run the tests and fix failures"). Your job: run the project's test suite, diagnose any failure, propose fixes as SEARCH/REPLACE edit blocks, then re-run. Repeat until green or you hit a wall you should escalate.

How to operate:

1. **Detect the test command**.
   - Look for \`package.json\` \u2192 \`scripts.test\` first (most common: \`npm test\`, \`pnpm test\`, \`yarn test\`).
   - If no package.json or no test script: try \`pytest\`, \`go test ./...\`, \`cargo test\` based on what files exist (pyproject.toml/requirements.txt \u2192 pytest; go.mod \u2192 go test; Cargo.toml \u2192 cargo test).
   - If you can't tell, ASK the user for the command \u2014 don't guess. One question, one tool call to confirm.

2. **Run it via run_command** (typical timeout 120s, bigger if the suite is large). Capture stdout + stderr.

3. **Read the failures**. Pull out: which test names failed, the actual error/traceback, the file + line that threw. Don't just paraphrase \u2014 locate the exact assertion or stack frame.

4. **Propose fixes**. For each distinct failure:
   - If the failure is in PRODUCTION code (test catches a real bug) \u2192 propose a SEARCH/REPLACE that fixes the production code.
   - If the failure is in TEST code (test is wrong, codebase is right) \u2192 propose a SEARCH/REPLACE that updates the test, AND say so explicitly: "This is a test bug, not a production bug \u2014 updating the assertion."
   - If the failure is environmental (missing dep, wrong node version, missing fixture file) \u2192 say so and stop. Don't try to install packages or change config without checking with the user.

5. **Apply + re-run**. After the user accepts the edit blocks, run the test command again. Iterate.

6. **Stop conditions**:
   - All tests pass \u2192 report green, summarize what changed.
   - Same test still failing after 2 fix attempts on the same line \u2192 STOP. Tell the user "I've tried twice, it's still failing \u2014 here's what I think is happening, want me to try a different angle?". Don't loop indefinitely.
   - 3+ unrelated failures \u2192 fix one at a time, smallest first, so each pass narrows the surface.

Don't:
- Run \`npm install\` / \`pip install\` / \`cargo update\` without asking \u2014 those mutate lockfiles and have global effects.
- Disable, skip, or delete failing tests to "make it green". If a test seems wrong, update its assertion with a one-sentence explanation, but never add \`.skip\` / \`it.skip\` / \`@pytest.mark.skip\`.
- Modify the test runner config (vitest.config, jest.config, etc.) to silence failures.

Lead each turn with a one-line status: "\u25B8 running \`npm test\` ..." \u2192 "\u25B8 2 failures in tests/foo.test.ts \u2014 first is \u2026" \u2192 so the user always knows where you are without scrolling tool output.`;
var BUILTIN_SKILLS = Object.freeze([
  Object.freeze({
    name: "explore",
    description: "Explore the codebase in an isolated subagent \u2014 wide-net read-only investigation that returns one distilled answer. Best for: 'find all places that...', 'how does X work across the project', 'survey the code for Y'.",
    body: BUILTIN_EXPLORE_BODY,
    scope: "builtin",
    path: "(builtin)",
    runAs: "subagent"
  }),
  Object.freeze({
    name: "research",
    description: "Research a question by combining web search + code reading in an isolated subagent. Best for: 'is X feature supported by lib Y', 'what's the canonical way to do Z', 'compare our impl against the spec'.",
    body: BUILTIN_RESEARCH_BODY,
    scope: "builtin",
    path: "(builtin)",
    runAs: "subagent"
  }),
  Object.freeze({
    name: "review",
    description: "Review the pending changes (current branch diff by default) in an isolated subagent \u2014 flags correctness, security, missing tests, hidden behavior changes; reports verdict + per-issue file:line. Read-only; the parent decides what to act on.",
    body: BUILTIN_REVIEW_BODY,
    scope: "builtin",
    path: "(builtin)",
    runAs: "subagent"
  }),
  Object.freeze({
    name: "security-review",
    description: "Security-focused review of the current branch diff in an isolated subagent \u2014 flags injection/authz/secrets/deserialization/path-traversal/crypto issues, severity-tagged. Read-only. Use when shipping changes that touch auth, input parsing, file IO, or external requests.",
    body: BUILTIN_SECURITY_REVIEW_BODY,
    scope: "builtin",
    path: "(builtin)",
    runAs: "subagent"
  }),
  Object.freeze({
    name: "test",
    description: "Run the project's test suite, diagnose failures, propose SEARCH/REPLACE fixes, re-run until green (or stop after 2 fix attempts on the same failure). Inlined \u2014 runs in the parent loop so you see the edit blocks and can /apply them. Detects npm/pnpm/yarn/pytest/go/cargo.",
    body: BUILTIN_TEST_BODY,
    scope: "builtin",
    path: "(builtin)",
    runAs: "inline"
  })
]);

// src/memory/user.ts
import { createHash } from "crypto";
import {
  existsSync as existsSync3,
  mkdirSync as mkdirSync2,
  readFileSync as readFileSync3,
  readdirSync as readdirSync2,
  unlinkSync,
  writeFileSync as writeFileSync2
} from "fs";
import { homedir as homedir2 } from "os";
import { join as join3, resolve as resolve2 } from "path";
var USER_MEMORY_DIR = "memory";
var MEMORY_INDEX_FILE = "MEMORY.md";
var MEMORY_INDEX_MAX_CHARS = 4e3;
var VALID_NAME = /^[a-zA-Z0-9_-][a-zA-Z0-9_.-]{1,38}[a-zA-Z0-9]$/;
function sanitizeMemoryName(raw) {
  const trimmed = String(raw ?? "").trim();
  if (!VALID_NAME.test(trimmed)) {
    throw new Error(
      `invalid memory name: ${JSON.stringify(raw)} \u2014 must be 3-40 chars, alnum/_/-, no path separators`
    );
  }
  return trimmed;
}
function projectHash(rootDir) {
  const abs = resolve2(rootDir);
  return createHash("sha1").update(abs).digest("hex").slice(0, 16);
}
function scopeDir(opts) {
  if (opts.scope === "global") {
    return join3(opts.homeDir, USER_MEMORY_DIR, "global");
  }
  if (!opts.projectRoot) {
    throw new Error("scope=project requires a projectRoot on MemoryStore");
  }
  return join3(opts.homeDir, USER_MEMORY_DIR, projectHash(opts.projectRoot));
}
function ensureDir(p) {
  if (!existsSync3(p)) mkdirSync2(p, { recursive: true });
}
function formatFrontmatter(e) {
  const lines = [
    "---",
    `name: ${e.name}`,
    `description: ${e.description.replace(/\n/g, " ")}`,
    `type: ${e.type}`,
    `scope: ${e.scope}`,
    `created: ${e.createdAt}`
  ];
  if (e.priority) lines.push(`priority: ${e.priority}`);
  if (e.expires) lines.push(`expires: ${e.expires}`);
  lines.push("---", "");
  return lines.join("\n");
}
function coercePriority(v) {
  return v === "low" || v === "medium" || v === "high" ? v : void 0;
}
function coerceExpires(v) {
  return v === "project_end" ? v : void 0;
}
function todayIso() {
  const d = /* @__PURE__ */ new Date();
  return d.toISOString().slice(0, 10);
}
function indexLine(e) {
  const safeDesc = e.description.replace(/\n/g, " ").trim();
  const max = 130 - e.name.length;
  const clipped = safeDesc.length > max ? `${safeDesc.slice(0, Math.max(1, max - 1))}\u2026` : safeDesc;
  return `- [${e.name}](${e.name}.md) \u2014 ${clipped}`;
}
var MemoryStore = class {
  homeDir;
  projectRoot;
  constructor(opts = {}) {
    this.homeDir = opts.homeDir ?? join3(homedir2(), ".reasonix");
    this.projectRoot = opts.projectRoot ? resolve2(opts.projectRoot) : void 0;
  }
  /** Directory this store writes `scope` files into, creating it if needed. */
  dir(scope) {
    const d = scopeDir({ homeDir: this.homeDir, scope, projectRoot: this.projectRoot });
    ensureDir(d);
    return d;
  }
  /** Absolute path to a memory file (no existence check). */
  pathFor(scope, name) {
    return join3(this.dir(scope), `${sanitizeMemoryName(name)}.md`);
  }
  /** True iff this store is configured with a project scope available. */
  hasProjectScope() {
    return this.projectRoot !== void 0;
  }
  loadIndex(scope) {
    if (scope === "project" && !this.projectRoot) return null;
    const file = join3(
      scopeDir({ homeDir: this.homeDir, scope, projectRoot: this.projectRoot }),
      MEMORY_INDEX_FILE
    );
    if (!existsSync3(file)) return null;
    let raw;
    try {
      raw = readFileSync3(file, "utf8");
    } catch {
      return null;
    }
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const originalChars = trimmed.length;
    const truncated = originalChars > MEMORY_INDEX_MAX_CHARS;
    const content = truncated ? `${trimmed.slice(0, MEMORY_INDEX_MAX_CHARS)}
\u2026 (truncated ${originalChars - MEMORY_INDEX_MAX_CHARS} chars)` : trimmed;
    return { content, originalChars, truncated };
  }
  /** Read one memory file's body (frontmatter stripped). Throws if missing. */
  read(scope, name) {
    const file = this.pathFor(scope, name);
    if (!existsSync3(file)) {
      throw new Error(`memory not found: scope=${scope} name=${name}`);
    }
    const raw = readFileSync3(file, "utf8");
    const { data, body } = parseFrontmatter(raw);
    const entry = {
      name: data.name ?? name,
      type: data.type ?? "project",
      scope: data.scope ?? scope,
      description: data.description ?? "",
      body: body.trim(),
      createdAt: data.created ?? ""
    };
    const priority = coercePriority(data.priority);
    if (priority) entry.priority = priority;
    const expires = coerceExpires(data.expires);
    if (expires) entry.expires = expires;
    return entry;
  }
  /** Skips malformed files — index stays queryable even if one file is hand-edited into nonsense. */
  list() {
    const out = [];
    const scopes = this.projectRoot ? ["global", "project"] : ["global"];
    for (const scope of scopes) {
      const dir = scopeDir({ homeDir: this.homeDir, scope, projectRoot: this.projectRoot });
      if (!existsSync3(dir)) continue;
      let entries;
      try {
        entries = readdirSync2(dir);
      } catch {
        continue;
      }
      for (const entry of entries) {
        if (entry === MEMORY_INDEX_FILE) continue;
        if (!entry.endsWith(".md")) continue;
        const name = entry.slice(0, -3);
        try {
          out.push(this.read(scope, name));
        } catch {
        }
      }
    }
    return out;
  }
  write(input) {
    if (input.scope === "project" && !this.projectRoot) {
      throw new Error("cannot write project-scoped memory: no projectRoot configured");
    }
    const name = sanitizeMemoryName(input.name);
    const desc = String(input.description ?? "").trim();
    if (!desc) throw new Error("memory description cannot be empty");
    const body = String(input.body ?? "").trim();
    if (!body) throw new Error("memory body cannot be empty");
    const entry = {
      ...input,
      name,
      description: desc,
      body,
      createdAt: todayIso()
    };
    if (input.priority) entry.priority = input.priority;
    if (input.expires) entry.expires = input.expires;
    const dir = this.dir(input.scope);
    const file = join3(dir, `${name}.md`);
    const content = `${formatFrontmatter(entry)}${body}
`;
    writeFileSync2(file, content, "utf8");
    this.regenerateIndex(input.scope);
    return file;
  }
  /** Delete one memory + its index line. No-op if the file is already gone. */
  delete(scope, rawName) {
    if (scope === "project" && !this.projectRoot) {
      throw new Error("cannot delete project-scoped memory: no projectRoot configured");
    }
    const file = this.pathFor(scope, rawName);
    if (!existsSync3(file)) return false;
    unlinkSync(file);
    this.regenerateIndex(scope);
    return true;
  }
  /** Sorted by name — same file set must produce byte-identical MEMORY.md for stable prefix hashing. */
  regenerateIndex(scope) {
    const dir = scopeDir({ homeDir: this.homeDir, scope, projectRoot: this.projectRoot });
    if (!existsSync3(dir)) return;
    let files;
    try {
      files = readdirSync2(dir);
    } catch {
      return;
    }
    const mdFiles = files.filter((f) => f !== MEMORY_INDEX_FILE && f.endsWith(".md")).sort((a, b) => a.localeCompare(b));
    const indexPath = join3(dir, MEMORY_INDEX_FILE);
    if (mdFiles.length === 0) {
      if (existsSync3(indexPath)) unlinkSync(indexPath);
      return;
    }
    const lines = [];
    for (const f of mdFiles) {
      const name = f.slice(0, -3);
      try {
        const entry = this.read(scope, name);
        lines.push(indexLine({ name: entry.name || name, description: entry.description }));
      } catch {
        lines.push(`- [${name}](${name}.md) \u2014 (malformed, check frontmatter)`);
      }
    }
    writeFileSync2(indexPath, `${lines.join("\n")}
`, "utf8");
  }
};
function readGlobalReasonixMemory(homeDir = join3(homedir2(), ".reasonix")) {
  const path = join3(homeDir, "REASONIX.md");
  if (!existsSync3(path)) return null;
  let raw;
  try {
    raw = readFileSync3(path, "utf8");
  } catch {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const originalChars = trimmed.length;
  const truncated = originalChars > 8e3;
  const content = truncated ? `${trimmed.slice(0, 8e3)}
\u2026 (truncated ${originalChars - 8e3} chars)` : trimmed;
  return { path, content, originalChars, truncated };
}
function applyGlobalReasonixMemory(basePrompt, homeDir) {
  if (!memoryEnabled()) return basePrompt;
  const dir = homeDir ?? join3(homedir2(), ".reasonix");
  const mem = readGlobalReasonixMemory(dir);
  if (!mem) return basePrompt;
  return [
    basePrompt,
    "",
    "# Global memory (~/.reasonix/REASONIX.md)",
    "",
    "Cross-project notes the user pinned via the `#g` prompt prefix. Treat as authoritative \u2014 same level of trust as project memory.",
    "",
    "```",
    mem.content,
    "```"
  ].join("\n");
}
function readGlobalClaudeMemory(homeDir = homedir2()) {
  const path = join3(homeDir, ".claude", "CLAUDE.md");
  if (!existsSync3(path)) return null;
  let raw;
  try {
    raw = readFileSync3(path, "utf8");
  } catch {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const originalChars = trimmed.length;
  const truncated = originalChars > 8e3;
  const content = truncated ? `${trimmed.slice(0, 8e3)}
\u2026 (truncated ${originalChars - 8e3} chars)` : trimmed;
  return { path, content, originalChars, truncated };
}
function applyGlobalClaudeMemory(basePrompt) {
  if (!memoryEnabled()) return basePrompt;
  const mem = readGlobalClaudeMemory();
  if (!mem) return basePrompt;
  return [
    basePrompt,
    "",
    "# Global memory (~/.claude/CLAUDE.md)",
    "",
    "Cross-project notes from your Claude Code configuration. Treat as authoritative \u2014 same level of trust as project memory.",
    "",
    "```",
    mem.content,
    "```"
  ].join("\n");
}
function effectivePriority(entry, cfg) {
  if (entry.priority) return entry.priority;
  return memoryTypeDefaults(entry.type, cfg).priority;
}
function highPriorityBlock(entries, cfg) {
  const high = entries.filter((e) => effectivePriority(e, cfg) === "high");
  if (high.length === 0) return null;
  const lines = [
    "# HIGH PRIORITY constraints (must observe)",
    "",
    "These memories were declared `priority: high` (via config.memory.customTypes or the memory file itself). Treat them as hard rules \u2014 violations override any other guidance below.",
    ""
  ];
  for (const e of high) {
    const head = `!!! [${e.scope}/${e.type}/${e.name}] ${e.description || "(no description)"}`;
    lines.push(head);
    if (e.body) lines.push("", e.body);
    lines.push("");
  }
  return lines.join("\n").trimEnd();
}
function applyUserMemory(basePrompt, opts = {}) {
  if (!memoryEnabled()) return basePrompt;
  const store = new MemoryStore(opts);
  const global = store.loadIndex("global");
  const project = store.hasProjectScope() ? store.loadIndex("project") : null;
  const high = highPriorityBlock(store.list(), opts.cfg);
  if (!global && !project && !high) return basePrompt;
  const parts = [basePrompt];
  if (high) parts.push("", high);
  if (global) {
    parts.push(
      "",
      "# User memory \u2014 global (~/.reasonix/memory/global/MEMORY.md)",
      "",
      "Cross-project facts and preferences the user has told you in prior sessions. TREAT AS AUTHORITATIVE \u2014 don't re-verify via filesystem or web. One-liners index detail files; call `recall_memory` for full bodies only when the one-liner isn't enough.",
      "",
      "```",
      global.content,
      "```"
    );
  }
  if (project) {
    parts.push(
      "",
      "# User memory \u2014 this project",
      "",
      "Per-project facts the user established in prior sessions (not committed to the repo). TREAT AS AUTHORITATIVE. Same recall pattern as global memory.",
      "",
      "```",
      project.content,
      "```"
    );
  }
  return parts.join("\n");
}
function applyMemoryStack(basePrompt, rootDir, opts = {}) {
  const homeDir = opts.homeDir;
  const cfg = opts.cfg;
  const withProject = applyProjectMemory(basePrompt, rootDir);
  const withGlobal = applyGlobalReasonixMemory(
    withProject,
    homeDir ? join3(homeDir, ".reasonix") : void 0
  );
  const withGlobalClaude = applyGlobalClaudeMemory(withGlobal);
  const withMemory = applyUserMemory(withGlobalClaude, { projectRoot: rootDir, homeDir, cfg });
  const customSkillPaths = cfg?.skills?.paths ? resolveSkillPaths(cfg.skills.paths, rootDir) : loadResolvedSkillPaths(rootDir);
  return applySkillsIndex(withMemory, { projectRoot: rootDir, homeDir, customSkillPaths });
}

export {
  PROJECT_MEMORY_FILE,
  PROJECT_MEMORY_FILES,
  PROJECT_MEMORY_MAX_CHARS,
  detectForeignAgentPlatform,
  findProjectMemoryPath,
  resolveProjectMemoryWritePath,
  readProjectMemory,
  memoryEnabled,
  parseFrontmatter,
  TUI_FORMATTING_RULES,
  escalationContract,
  NEGATIVE_CLAIM_RULE,
  SKILLS_DIRNAME,
  SKILL_FILE,
  validateSkillFrontmatter,
  SkillStore,
  sanitizeMemoryName,
  MemoryStore,
  readGlobalReasonixMemory,
  effectivePriority,
  applyMemoryStack
};
//# sourceMappingURL=chunk-J4MYMBJ7.js.map