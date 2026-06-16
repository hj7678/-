#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  DeepSeekClient
} from "./chunk-QSKDP3OS.js";
import "./chunk-25T6CVUP.js";
import {
  loadDotenv
} from "./chunk-2UQP6H6T.js";
import {
  loadEndpoint
} from "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/cli/commands/commit.ts
import { spawn, spawnSync } from "child_process";
import { mkdtempSync, readFileSync, unlinkSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { stdin, stdout } from "process";
import { createInterface } from "readline/promises";
var DEFAULT_MODEL = "deepseek-v4-flash";
var DIFF_BYTE_CAP = 80 * 1024;
var LOG_COUNT = 10;
var SYSTEM_PROMPT = `You draft git commit messages.

Output ONLY the commit message \u2014 no preamble, no \`\`\` fences, no "Here's a commit message:" lead-in. The first line of your output IS the commit subject.

Match the project's existing style:
- Look at the recent commits provided. Mirror their voice, conventional-commit prefix usage (or absence), tense, length, body structure.
- If recent commits use a "type(scope): summary" prefix, use it. If they don't, don't invent one.
- Subject line: one line, \u226472 chars, imperative mood, no trailing period.
- Body (optional): explain WHY when the diff isn't self-evident. Wrap at ~72 chars. Skip the body for trivial changes \u2014 repeating the subject in the body is noise.

The diff is the source of truth for what changed; describe THAT, not your guesses about the broader project. If the diff includes a deletion you can't explain from the surrounding context, name it but don't speculate about why.

No emojis unless the recent commits use them.
No co-author trailers, no "Generated with X" footers.`;
function runGit(args, opts = {}) {
  const result = spawnSync("git", args, {
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
    input: opts.input,
    maxBuffer: 32 * 1024 * 1024
  });
  return {
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
    status: result.status
  };
}
function dieIfNotGitRepo() {
  const r = runGit(["rev-parse", "--is-inside-work-tree"]);
  if (r.status !== 0) {
    process.stderr.write("reasonix commit: not inside a git repository.\n");
    process.exit(1);
  }
}
function readDiff() {
  const staged = runGit(["diff", "--staged", "--no-color"]);
  if (staged.status !== 0) {
    process.stderr.write(`reasonix commit: git diff --staged failed: ${staged.stderr.trim()}
`);
    process.exit(1);
  }
  if (staged.stdout.trim().length > 0) {
    return capDiff(staged.stdout, "staged");
  }
  const wt = runGit(["diff", "--no-color"]);
  if (wt.stdout.trim().length === 0) {
    return null;
  }
  return capDiff(wt.stdout, "working-tree");
}
function capDiff(raw, source) {
  if (raw.length <= DIFF_BYTE_CAP) {
    return { diff: raw, source, truncated: false };
  }
  const head = raw.slice(0, Math.floor(DIFF_BYTE_CAP * 0.7));
  const tail = raw.slice(-Math.floor(DIFF_BYTE_CAP * 0.3));
  return {
    diff: `${head}

[\u2026 ${raw.length - DIFF_BYTE_CAP} bytes of diff truncated \u2026]

${tail}`,
    source,
    truncated: true
  };
}
function readRecentCommits() {
  const r = runGit(["log", `-${LOG_COUNT}`, "--no-merges", "--format=%s%n%b%n---END---"]);
  if (r.status !== 0) {
    return "";
  }
  return r.stdout.trim();
}
async function draftMessage(client, model, diff, recentCommits) {
  const userParts = [];
  if (recentCommits) {
    userParts.push(`Recent commits (style reference):

${recentCommits}`);
  }
  if (diff.source === "working-tree") {
    userParts.push(
      "(NOTE: diff is from the working tree, not the staging area \u2014 nothing is staged yet. The user will stage selectively after seeing the draft.)"
    );
  }
  userParts.push(`Diff to summarize:

${diff.diff}`);
  const resp = await client.chat({
    model,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: userParts.join("\n\n") }
    ],
    temperature: 0.2
  });
  return stripCodeFences(resp.content.trim());
}
function stripCodeFences(s) {
  const trimmed = s.trim();
  const fenceOpen = /^```[a-zA-Z]*\n/;
  const fenceClose = /\n?```$/;
  if (fenceOpen.test(trimmed) && fenceClose.test(trimmed)) {
    return trimmed.replace(fenceOpen, "").replace(fenceClose, "").trim();
  }
  return trimmed;
}
function printDraft(message) {
  const sep = "\u2500".repeat(60);
  process.stdout.write(`
${sep}
${message}
${sep}

`);
}
async function promptChoice() {
  const rl = createInterface({ input: stdin, output: stdout });
  try {
    const answer = await rl.question("[a]ccept / [r]egenerate / [e]dit / [c]ancel: ");
    const k = answer.trim().toLowerCase();
    if (k === "" || k === "a" || k === "y" || k === "yes") return "accept";
    if (k === "r" || k === "regen" || k === "regenerate") return "regen";
    if (k === "e" || k === "edit") return "edit";
    return "cancel";
  } finally {
    rl.close();
  }
}
function editInExternal(initial) {
  const editor = process.env.GIT_EDITOR ?? process.env.VISUAL ?? process.env.EDITOR;
  if (!editor) {
    process.stderr.write(
      "reasonix commit: no $EDITOR / $VISUAL / $GIT_EDITOR set \u2014 can't open editor. Pick [a]ccept and `git commit --amend` afterwards.\n"
    );
    return null;
  }
  const dir = mkdtempSync(join(tmpdir(), "reasonix-commit-"));
  const path = join(dir, "COMMIT_EDITMSG");
  writeFileSync(path, initial, "utf8");
  const result = spawnSync(`${editor} "${path}"`, {
    stdio: "inherit",
    shell: true
  });
  if (result.status !== 0) {
    try {
      unlinkSync(path);
    } catch {
    }
    process.stderr.write(
      `reasonix commit: editor exited ${result.status} \u2014 keeping prior draft.
`
    );
    return null;
  }
  let edited;
  try {
    edited = readFileSync(path, "utf8");
  } catch {
    return null;
  } finally {
    try {
      unlinkSync(path);
    } catch {
    }
  }
  const cleaned = edited.split(/\r?\n/).filter((line) => !/^\s*#/.test(line)).join("\n").trim();
  return cleaned || null;
}
function commitWithMessage(message) {
  const child = spawn("git", ["commit", "-F", "-"], {
    stdio: ["pipe", "inherit", "inherit"]
  });
  child.stdin.write(message);
  child.stdin.end();
  child.on("close", (code) => {
    if (code !== 0) {
      process.stderr.write(`reasonix commit: git commit exited ${code}.
`);
      process.exit(code ?? 1);
    }
  });
}
async function commitCommand(opts = {}) {
  loadDotenv();
  dieIfNotGitRepo();
  const ep = loadEndpoint();
  if (!ep.apiKey) {
    process.stderr.write(
      "reasonix commit: DEEPSEEK_API_KEY not set. Run `reasonix setup` to save one, or export it.\n"
    );
    process.exit(1);
  }
  const diff = readDiff();
  if (!diff) {
    process.stderr.write(
      "reasonix commit: no staged changes and working tree is clean \u2014 nothing to commit.\n"
    );
    process.exit(1);
  }
  if (diff.source === "working-tree") {
    process.stderr.write(
      "reasonix commit: nothing staged \u2014 drafting from working-tree diff. Stage your changes and re-run, or use the draft as a starting point.\n"
    );
  }
  if (diff.truncated) {
    process.stderr.write(
      "reasonix commit: diff exceeded 80KB; head + tail sent to the model. Large diffs often produce vague drafts \u2014 consider committing in smaller chunks.\n"
    );
  }
  const client = new DeepSeekClient({ apiKey: ep.apiKey, baseUrl: ep.baseUrl });
  const model = opts.model ?? DEFAULT_MODEL;
  const recentCommits = readRecentCommits();
  let message = "";
  let firstPass = true;
  while (true) {
    if (firstPass) {
      process.stdout.write("Drafting commit message\u2026\n");
    } else {
      process.stdout.write("Regenerating\u2026\n");
    }
    firstPass = false;
    try {
      message = await draftMessage(client, model, diff, recentCommits);
    } catch (err) {
      process.stderr.write(`reasonix commit: model call failed \u2014 ${err.message}
`);
      process.exit(1);
    }
    if (!message) {
      process.stderr.write("reasonix commit: model returned an empty draft. Try again.\n");
      process.exit(1);
    }
    printDraft(message);
    if (opts.yes) break;
    if (diff.source === "working-tree") {
      process.stdout.write(
        "(no staged changes \u2014 draft printed above for you to copy. Stage with `git add` and re-run to commit.)\n"
      );
      return;
    }
    const choice = await promptChoice();
    if (choice === "accept") break;
    if (choice === "cancel") {
      process.stderr.write("commit cancelled.\n");
      return;
    }
    if (choice === "edit") {
      const edited = editInExternal(message);
      if (edited) {
        message = edited;
        printDraft(message);
        const next = await promptChoice();
        if (next === "accept") break;
        if (next === "cancel") {
          process.stderr.write("commit cancelled.\n");
          return;
        }
      }
    }
  }
  commitWithMessage(message);
}
export {
  commitCommand
};
//# sourceMappingURL=commit-JT7LYBTL.js.map