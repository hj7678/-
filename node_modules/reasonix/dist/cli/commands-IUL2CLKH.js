#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  checkOllamaStatus,
  pullOllamaModel,
  startOllamaDaemon
} from "./chunk-RRZIIMAF.js";
import {
  buildIndex
} from "./chunk-I4SH5Z7S.js";
import "./chunk-6UNHNVJR.js";
import {
  loadIndexConfig,
  resolveSemanticEmbeddingConfig
} from "./chunk-GCNBIWK7.js";
import "./chunk-TUK7OWJA.js";

// src/cli/commands/index.ts
import { resolve } from "path";

// src/index/semantic/i18n.ts
var cachedLocale = null;
function detectLocale() {
  if (cachedLocale) return cachedLocale;
  const override = (process.env.REASONIX_LANG ?? "").toLowerCase();
  if (override === "zh" || override === "en") {
    cachedLocale = override;
    return cachedLocale;
  }
  const env = process.env.LANG ?? process.env.LC_ALL ?? process.env.LC_MESSAGES ?? "";
  if (/^zh[-_]/i.test(env)) {
    cachedLocale = "zh";
    return "zh";
  }
  try {
    const sys = new Intl.DateTimeFormat().resolvedOptions().locale ?? "";
    if (/^zh[-_]/i.test(sys)) {
      cachedLocale = "zh";
      return "zh";
    }
  } catch {
  }
  cachedLocale = "en";
  return "en";
}
function t(key, vars = {}) {
  const loc = detectLocale();
  const dict = loc === "zh" ? ZH : EN;
  const tpl = dict[key] ?? EN[key];
  return tpl.replace(/\{(\w+)\}/g, (_m, name) => {
    const v = vars[name];
    return v === void 0 ? `{${name}}` : String(v);
  });
}
var EN = {
  // ── preflight ─────────────────────────────────────────────────────
  ollamaNotFound: "\u2717 `ollama` not found on PATH.\n  Install from https://ollama.com (one-time, ~150 MB), then retry.\n",
  daemonNotReachableHint: "\u2717 Ollama daemon not reachable. Run `ollama serve` and retry, or pass --yes to start it automatically.\n",
  daemonStartConfirm: "Ollama daemon isn't running. Start `ollama serve` now?",
  daemonAbortStart: "\u2717 aborted \u2014 start `ollama serve` yourself and retry.\n",
  daemonStarting: "\u25B8 starting `ollama serve`\u2026\n",
  daemonStartTimeout: "\u2717 daemon didn't come up within 15s. Try `ollama serve` in a separate terminal and retry.\n",
  daemonReady: "\u2713 daemon up{pid}\n",
  modelNotPulledHint: '\u2717 embedding model "{model}" not pulled. Run `ollama pull {model}` and retry, or pass --yes to pull it automatically.\n',
  modelPullConfirm: `Embedding model "{model}" isn't pulled yet. Pull it now? (~274 MB for nomic-embed-text)`,
  modelAbortPull: "\u2717 aborted \u2014 pull the model yourself and retry.\n",
  modelPulling: "\u25B8 pulling {model}\u2026\n",
  modelPullFailed: "\u2717 `ollama pull {model}` failed (exit {code}).\n",
  modelPulled: "\u2713 {model} pulled\n",
  // ── progress ─────────────────────────────────────────────────────
  // The TTY-mode progress writer paints `<spinner> <status>  <elapsed>s`
  // every 120ms. The status itself comes from one of these keys based
  // on the current phase. {files}, {done}, {total}, {pct} are
  // substituted by the writer.
  progressStarting: "starting\u2026",
  progressScan: "scanning project \xB7 {files} files",
  progressEmbed: "embedding {done}/{total} chunks \xB7 {pct}%",
  progressEmbedHeartbeat: "  {done}/{total}\n",
  progressScanLine: "scanning files\u2026\n",
  progressEmbedLine: "embedding {total} chunks across {files} files\u2026\n",
  // Final result line after a successful build.
  indexSuccess: "\u2713 indexed {scanned} files ({changed} changed, {added} new chunks, {removed} stale removed) in {seconds}s\n",
  indexSuccessWithSkips: "\u2713 indexed {scanned} files ({changed} changed, {added} new chunks, {removed} stale removed, {skipped} skipped due to embed errors) in {seconds}s\n",
  indexNothingToDo: "  (nothing to do \u2014 re-run with --rebuild to force a full rebuild)\n",
  indexFailed: "\u2717 index failed: {msg}\n",
  // ── /semantic slash ──────────────────────────────────────────────
  slashHeader: "semantic_search status",
  slashEnabled: "\u2713 enabled \u2014 index built, tool registered.",
  slashEnabledDetail: "  index size: {chunks} chunks across {files} files",
  slashEnabledHowto: "  the model will call semantic_search automatically when it fits.",
  slashIndexMissing: "\u2717 no index built yet for this project.",
  slashHowToBuild: "  to enable, exit Reasonix and run in your shell:\n      reasonix index",
  slashOllamaMissing: "  prerequisite: install Ollama from https://ollama.com",
  slashDaemonDown: "  Ollama is installed but the daemon isn't running. start it with: ollama serve",
  slashIndexInfo: "  what semantic_search does: cross-language code understanding via local embeddings.\n  better than grep when you describe WHAT something does, not WHICH token to find."
};
var ZH = {
  ollamaNotFound: "\u2717 \u672A\u627E\u5230 `ollama`\u3002\n  \u8BF7\u8BBF\u95EE https://ollama.com \u5B89\u88C5\uFF08\u4E00\u6B21\u6027\uFF0C\u7EA6 150 MB\uFF09\uFF0C\u7136\u540E\u91CD\u8BD5\u3002\n",
  daemonNotReachableHint: "\u2717 Ollama \u5B88\u62A4\u8FDB\u7A0B\u672A\u542F\u52A8\u3002\u8BF7\u8FD0\u884C `ollama serve` \u540E\u91CD\u8BD5\uFF0C\u6216\u52A0 --yes \u8BA9\u6211\u81EA\u52A8\u542F\u52A8\u3002\n",
  daemonStartConfirm: "Ollama \u5B88\u62A4\u8FDB\u7A0B\u672A\u8FD0\u884C\u3002\u73B0\u5728\u542F\u52A8 `ollama serve` \u5417\uFF1F",
  daemonAbortStart: "\u2717 \u5DF2\u53D6\u6D88\u2014\u2014\u8BF7\u81EA\u884C\u8FD0\u884C `ollama serve` \u540E\u91CD\u8BD5\u3002\n",
  daemonStarting: "\u25B8 \u6B63\u5728\u542F\u52A8 `ollama serve`\u2026\n",
  daemonStartTimeout: "\u2717 15 \u79D2\u5185\u5B88\u62A4\u8FDB\u7A0B\u672A\u5C31\u7EEA\u3002\u8BF7\u5728\u53E6\u4E00\u4E2A\u7EC8\u7AEF\u8FD0\u884C `ollama serve` \u540E\u91CD\u8BD5\u3002\n",
  daemonReady: "\u2713 \u5B88\u62A4\u8FDB\u7A0B\u5DF2\u542F\u52A8{pid}\n",
  modelNotPulledHint: '\u2717 \u5D4C\u5165\u6A21\u578B "{model}" \u672A\u4E0B\u8F7D\u3002\u8BF7\u8FD0\u884C `ollama pull {model}` \u540E\u91CD\u8BD5\uFF0C\u6216\u52A0 --yes \u8BA9\u6211\u81EA\u52A8\u4E0B\u8F7D\u3002\n',
  modelPullConfirm: '\u5D4C\u5165\u6A21\u578B "{model}" \u8FD8\u672A\u4E0B\u8F7D\u3002\u73B0\u5728\u4E0B\u8F7D\u5417\uFF1F\uFF08nomic-embed-text \u7EA6 274 MB\uFF09',
  modelAbortPull: "\u2717 \u5DF2\u53D6\u6D88\u2014\u2014\u8BF7\u81EA\u884C\u4E0B\u8F7D\u6A21\u578B\u540E\u91CD\u8BD5\u3002\n",
  modelPulling: "\u25B8 \u6B63\u5728\u4E0B\u8F7D {model}\u2026\n",
  modelPullFailed: "\u2717 `ollama pull {model}` \u5931\u8D25\uFF08\u9000\u51FA\u7801 {code}\uFF09\u3002\n",
  modelPulled: "\u2713 {model} \u4E0B\u8F7D\u5B8C\u6210\n",
  progressStarting: "\u6B63\u5728\u542F\u52A8\u2026",
  progressScan: "\u626B\u63CF\u9879\u76EE \xB7 \u5DF2\u626B\u63CF {files} \u4E2A\u6587\u4EF6",
  progressEmbed: "\u6B63\u5728\u5411\u91CF\u5316 {done}/{total} \u4E2A\u7247\u6BB5 \xB7 {pct}%",
  progressEmbedHeartbeat: "  {done}/{total}\n",
  progressScanLine: "\u6B63\u5728\u626B\u63CF\u6587\u4EF6\u2026\n",
  progressEmbedLine: "\u6B63\u5728\u5411\u91CF\u5316 {total} \u4E2A\u7247\u6BB5\uFF08\u6D89\u53CA {files} \u4E2A\u6587\u4EF6\uFF09\u2026\n",
  indexSuccess: "\u2713 \u5DF2\u5EFA\u7ACB\u7D22\u5F15\uFF1A\u626B\u63CF {scanned} \u4E2A\u6587\u4EF6\uFF08{changed} \u4E2A\u6709\u53D8\u5316\uFF0C\u65B0\u589E {added} \u4E2A\u7247\u6BB5\uFF0C\u79FB\u9664 {removed} \u4E2A\u8FC7\u671F\uFF09\uFF1B\u8017\u65F6 {seconds}s\n",
  indexSuccessWithSkips: "\u2713 \u5DF2\u5EFA\u7ACB\u7D22\u5F15\uFF1A\u626B\u63CF {scanned} \u4E2A\u6587\u4EF6\uFF08{changed} \u4E2A\u6709\u53D8\u5316\uFF0C\u65B0\u589E {added} \u4E2A\u7247\u6BB5\uFF0C\u79FB\u9664 {removed} \u4E2A\u8FC7\u671F\uFF0C\u8DF3\u8FC7 {skipped} \u4E2A\u5D4C\u5165\u5931\u8D25\u7684\u7247\u6BB5\uFF09\uFF1B\u8017\u65F6 {seconds}s\n",
  indexNothingToDo: "  \uFF08\u6CA1\u6709\u53D8\u5316\u2014\u2014\u52A0 --rebuild \u5F3A\u5236\u91CD\u5EFA\uFF09\n",
  indexFailed: "\u2717 \u5EFA\u7ACB\u7D22\u5F15\u5931\u8D25\uFF1A{msg}\n",
  slashHeader: "semantic_search \u72B6\u6001",
  slashEnabled: "\u2713 \u5DF2\u542F\u7528\u2014\u2014\u7D22\u5F15\u5DF2\u5EFA\u597D\uFF0C\u5DE5\u5177\u5DF2\u6CE8\u518C\u3002",
  slashEnabledDetail: "  \u7D22\u5F15\u89C4\u6A21\uFF1A{chunks} \u4E2A\u7247\u6BB5\uFF0C{files} \u4E2A\u6587\u4EF6",
  slashEnabledHowto: "  \u6A21\u578B\u5728\u5408\u9002\u7684\u65F6\u5019\u4F1A\u81EA\u52A8\u8C03\u7528 semantic_search\u3002",
  slashIndexMissing: "\u2717 \u5F53\u524D\u9879\u76EE\u8FD8\u6CA1\u6709\u7D22\u5F15\u3002",
  slashHowToBuild: "  \u542F\u7528\u65B9\u5F0F\uFF1A\u9000\u51FA Reasonix\uFF0C\u5728\u7EC8\u7AEF\u8FD0\u884C\uFF1A\n      reasonix index",
  slashOllamaMissing: "  \u524D\u7F6E\u4F9D\u8D56\uFF1A\u4ECE https://ollama.com \u5B89\u88C5 Ollama",
  slashDaemonDown: "  \u5DF2\u88C5 Ollama \u4F46\u5B88\u62A4\u8FDB\u7A0B\u672A\u542F\u52A8\uFF0C\u8BF7\u8FD0\u884C\uFF1Aollama serve",
  slashIndexInfo: '  semantic_search \u7528\u672C\u5730 embedding \u505A\u8DE8\u8BED\u8A00\u4EE3\u7801\u7406\u89E3\u3002\n  \u5F53\u4F60\u63CF\u8FF0"\u505A\u4EC0\u4E48"\u800C\u4E0D\u662F\u5177\u4F53 token \u65F6\uFF0C\u6BD4 grep \u66F4\u597D\u3002'
};

// src/index/semantic/preflight.ts
import { stdin, stdout } from "process";
import { createInterface } from "readline/promises";
async function ollamaPreflight(opts) {
  const log = opts.log ?? ((line) => process.stderr.write(line));
  const status = await checkOllamaStatus(opts.model, opts.baseUrl);
  if (!status.binaryFound) {
    log(t("ollamaNotFound"));
    return false;
  }
  if (!status.daemonRunning) {
    if (!opts.interactive && !opts.yesToAll) {
      log(t("daemonNotReachableHint"));
      return false;
    }
    const ok = opts.yesToAll || await confirm(t("daemonStartConfirm"), true);
    if (!ok) {
      log(t("daemonAbortStart"));
      return false;
    }
    log(t("daemonStarting"));
    const started = await startOllamaDaemon({ baseUrl: opts.baseUrl, timeoutMs: 15e3 });
    if (!started.ready) {
      log(t("daemonStartTimeout"));
      return false;
    }
    log(t("daemonReady", { pid: started.pid ? ` (pid ${started.pid})` : "" }));
  }
  const after = status.daemonRunning ? status : await checkOllamaStatus(opts.model, opts.baseUrl);
  if (!after.modelPulled) {
    if (!opts.interactive && !opts.yesToAll) {
      log(t("modelNotPulledHint", { model: opts.model }));
      return false;
    }
    const ok = opts.yesToAll || await confirm(t("modelPullConfirm", { model: opts.model }), true);
    if (!ok) {
      log(t("modelAbortPull"));
      return false;
    }
    log(t("modelPulling", { model: opts.model }));
    const ESC = String.fromCharCode(27);
    const ANSI_CSI = new RegExp(`${ESC}\\[[0-9;]*[A-Za-z]`, "g");
    const code = await pullOllamaModel(opts.model, {
      onLine: (line) => {
        const cleaned = line.replace(ANSI_CSI, "").trim();
        if (cleaned.length === 0) return;
        log(`  ${cleaned}
`);
      }
    });
    if (code !== 0) {
      log(t("modelPullFailed", { model: opts.model, code }));
      return false;
    }
    log(t("modelPulled", { model: opts.model }));
  }
  return true;
}
async function semanticPreflight(config, opts) {
  if (config.provider === "openai-compat") return true;
  return await ollamaPreflight({
    ...opts,
    model: config.model,
    baseUrl: config.baseUrl
  });
}
async function confirm(question, defaultYes) {
  const suffix = defaultYes ? "[Y/n]" : "[y/N]";
  const rl = createInterface({ input: stdin, output: stdout });
  try {
    const raw = (await rl.question(`${question} ${suffix} `)).trim().toLowerCase();
    if (raw === "") return defaultYes;
    return raw === "y" || raw === "yes";
  } finally {
    rl.close();
  }
}

// src/cli/commands/index.ts
async function indexCommand(opts = {}) {
  const root = resolve(opts.dir ?? process.cwd());
  const tty = process.stderr.isTTY === true && process.stdin.isTTY === true;
  const resolved = resolveSemanticEmbeddingConfig();
  const embedding = resolved.provider === "ollama" ? {
    ...resolved,
    model: opts.model ?? resolved.model,
    baseUrl: opts.ollamaUrl ?? resolved.baseUrl
  } : {
    ...resolved,
    model: opts.model ?? resolved.model
  };
  const preflightOk = await semanticPreflight(embedding, {
    interactive: tty && !opts.yes,
    yesToAll: opts.yes ?? false
  });
  if (!preflightOk) process.exit(1);
  const writer = makeProgressWriter(tty);
  const t0 = Date.now();
  let result;
  try {
    result = await buildIndex(root, {
      ...embedding,
      rebuild: opts.rebuild,
      indexConfig: loadIndexConfig(),
      onProgress: (p) => writer.update(p)
    });
  } catch (err) {
    writer.clear();
    const msg = err instanceof Error ? err.message : String(err);
    process.stderr.write(t("indexFailed", { msg }));
    process.exit(1);
  }
  writer.clear();
  const seconds = ((Date.now() - t0) / 1e3).toFixed(1);
  const successKey = result.chunksSkipped > 0 ? "indexSuccessWithSkips" : "indexSuccess";
  process.stderr.write(
    t(successKey, {
      scanned: result.filesScanned,
      changed: result.filesChanged,
      added: result.chunksAdded,
      removed: result.chunksRemoved,
      skipped: result.chunksSkipped,
      seconds
    })
  );
  const breakdown = renderSkipBreakdown(result.skipBuckets);
  if (breakdown) process.stderr.write(`${breakdown}
`);
  if (result.filesChanged === 0 && !opts.rebuild) {
    process.stderr.write(t("indexNothingToDo"));
  }
}
function renderSkipBreakdown(buckets) {
  const total = Object.values(buckets).reduce((a, b) => a + b, 0);
  if (total === 0) return "";
  const parts = [];
  if (buckets.gitignore) parts.push(`gitignore: ${buckets.gitignore}`);
  if (buckets.pattern) parts.push(`pattern: ${buckets.pattern}`);
  if (buckets.defaultDir) parts.push(`defaultDir: ${buckets.defaultDir}`);
  if (buckets.defaultFile) parts.push(`defaultFile: ${buckets.defaultFile}`);
  if (buckets.binaryExt) parts.push(`binaryExt: ${buckets.binaryExt}`);
  if (buckets.binaryContent) parts.push(`binaryContent: ${buckets.binaryContent}`);
  if (buckets.tooLarge) parts.push(`tooLarge: ${buckets.tooLarge}`);
  if (buckets.readError) parts.push(`readError: ${buckets.readError}`);
  return `  \xB7 skipped ${total} files (${parts.join(", ")})`;
}
var SPINNER_FRAMES = ["\u280B", "\u2819", "\u2839", "\u2838", "\u283C", "\u2834", "\u2826", "\u2827", "\u2807", "\u280F"];
var SPINNER_INTERVAL_MS = 120;
function makeProgressWriter(tty) {
  if (!tty) return makeNonTtyWriter();
  return makeTtyWriter();
}
function makeNonTtyWriter() {
  let lastPhase = null;
  let lastChunks = 0;
  return {
    update(p) {
      if (p.phase !== lastPhase) {
        lastPhase = p.phase;
        if (p.phase === "scan") {
          process.stderr.write(t("progressScanLine"));
        } else if (p.phase === "embed") {
          process.stderr.write(
            t("progressEmbedLine", {
              total: p.chunksTotal ?? 0,
              files: p.filesChanged ?? 0
            })
          );
        }
      }
      if (p.phase === "embed" && p.chunksDone !== void 0 && p.chunksDone - lastChunks >= 50) {
        lastChunks = p.chunksDone;
        process.stderr.write(
          t("progressEmbedHeartbeat", {
            done: p.chunksDone,
            total: p.chunksTotal ?? "?"
          })
        );
      }
    },
    clear() {
    }
  };
}
function makeTtyWriter() {
  let status = t("progressStarting");
  let lastLineLen = 0;
  let frameIdx = 0;
  const startTs = Date.now();
  const repaint = () => {
    const frame = SPINNER_FRAMES[frameIdx % SPINNER_FRAMES.length];
    frameIdx++;
    const elapsed = ((Date.now() - startTs) / 1e3).toFixed(1);
    const line = `${frame} ${status}  ${elapsed}s`;
    const padded = line + " ".repeat(Math.max(0, lastLineLen - line.length));
    process.stderr.write(`\r${padded}`);
    lastLineLen = line.length;
  };
  repaint();
  const interval = setInterval(repaint, SPINNER_INTERVAL_MS);
  return {
    update(p) {
      if (p.phase === "scan") {
        status = t("progressScan", { files: p.filesScanned ?? 0 });
      } else if (p.phase === "embed") {
        const done = p.chunksDone ?? 0;
        const total = p.chunksTotal ?? 0;
        const pct = total > 0 ? (done / total * 100).toFixed(0) : "0";
        status = t("progressEmbed", { done, total, pct });
      }
      repaint();
    },
    clear() {
      clearInterval(interval);
      if (lastLineLen > 0) {
        process.stderr.write(`\r${" ".repeat(lastLineLen)}\r`);
        lastLineLen = 0;
      }
    }
  };
}
export {
  indexCommand
};
//# sourceMappingURL=commands-IUL2CLKH.js.map