#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  bootstrapSemanticSearchInCodeMode
} from "./chunk-URAI4YRL.js";
import {
  registerSkillTools
} from "./chunk-GMQVINZK.js";
import {
  preflightStdioSpec
} from "./chunk-MQJR7YQ2.js";
import {
  SHARED_SUBAGENT_SINK,
  ToolRegistry,
  formatSubagentResult,
  registerChoiceTool,
  registerFilesystemTools,
  registerMemoryTools,
  registerPlanTool,
  registerTodoTool,
  registerWebTools,
  spawnSubagent
} from "./chunk-DFHI2MRB.js";
import {
  JobRegistry,
  registerShellTools
} from "./chunk-4V4TKQMB.js";
import {
  SkillStore
} from "./chunk-J4MYMBJ7.js";
import {
  MCP_CATALOG
} from "./chunk-PLHAZOLZ.js";
import {
  grammarForPath
} from "./chunk-L3VPEESB.js";
import {
  DeepSeekClient
} from "./chunk-QSKDP3OS.js";
import {
  defaultConfigPath,
  loadEditMode,
  loadEndpoint,
  loadFilesystemOutlineThresholdBytes,
  loadJavaSourceEnabled,
  loadProjectShellAllowed,
  loadResolvedSkillPaths,
  loadSubagentModels,
  loadToolRateLimit,
  parseMcpSpec,
  readConfig,
  searchEnabled,
  writeConfig
} from "./chunk-GCNBIWK7.js";

// src/tools/code-query.ts
import { readFile } from "fs/promises";
import { resolve as pathResolve } from "path";

// src/core/lazy.ts
function lazy(load) {
  let pending = null;
  return () => {
    if (!pending) pending = load();
    return pending;
  };
}

// src/tools/code-query.ts
var loadSymbols = lazy(() => import("./symbols-UQ274IOB.js"));
var loadFindInCode = lazy(() => import("./find-in-code-YLEIK5FK.js"));
var UNSUPPORTED = "language not supported (TS/TSX/JS/JSX/Python/Go/Rust/Java); use search_content for grep-style matching";
function registerCodeQueryTools(registry, opts) {
  const { rootDir } = opts;
  registry.register({
    name: "get_symbols",
    description: "Outline a single TS/TSX/JS/JSX/Python/Go/Rust/Java file via tree-sitter \u2014 returns its top-level + nested symbols (functions, classes, methods, interfaces, types, enums, namespaces) with 1-based line/column. Grammar-aware, ignores names inside comments/strings. Use for 'what's in this file' / 'where is X defined here'; for cross-file scans use search_content. Result: {path, symbols:[{name, kind, line, column, endLine, endColumn, parent?}]} or {path, error}.",
    readOnly: true,
    parallelSafe: true,
    stormExempt: true,
    parameters: {
      type: "object",
      properties: {
        path: {
          type: "string",
          description: "File path (relative to project root or absolute)."
        }
      },
      required: ["path"]
    },
    fn: async (args) => {
      const filePath = resolveProjectPath(rootDir, args.path);
      if (!grammarForPath(filePath)) {
        return JSON.stringify({ path: args.path, error: UNSUPPORTED });
      }
      const source = await readFile(filePath, "utf8");
      const { extractSymbols } = await loadSymbols();
      const symbols = await extractSymbols(filePath, source);
      return JSON.stringify({ path: args.path, symbols });
    }
  });
  registry.register({
    name: "find_in_code",
    description: "Find an identifier `name` in a single TS/TSX/JS/JSX/Python/Go/Rust/Java file, AST-filtered \u2014 skips matches inside comments and strings. Optional `kind` narrows by syntactic role: 'call' (function call site), 'definition' (declaration name), 'reference' (other uses), 'any' (default). Within-file only \u2014 does NOT resolve cross-file references; use search_content + reading for that. Result: {path, matches:[{line, column, kind, snippet}]} or {path, error}.",
    readOnly: true,
    parallelSafe: true,
    stormExempt: true,
    parameters: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Exact identifier text to find."
        },
        path: {
          type: "string",
          description: "File path (relative to project root or absolute)."
        },
        kind: {
          type: "string",
          enum: ["any", "call", "definition", "reference"],
          description: "Filter by syntactic role. Default 'any'."
        }
      },
      required: ["name", "path"]
    },
    fn: async (args) => {
      const filePath = resolveProjectPath(rootDir, args.path);
      if (!grammarForPath(filePath)) {
        return JSON.stringify({ path: args.path, error: UNSUPPORTED });
      }
      const source = await readFile(filePath, "utf8");
      const kind = args.kind ?? "any";
      const findOpts = kind === "any" ? {} : { kind };
      const { findInCode } = await loadFindInCode();
      const matches = await findInCode(filePath, source, args.name, findOpts);
      return JSON.stringify({ path: args.path, matches });
    }
  });
}
function resolveProjectPath(rootDir, raw) {
  const stripped = raw.replace(/^[/\\]+/, "");
  return pathResolve(rootDir, stripped.length === 0 ? "." : stripped);
}

// src/java/class-source-finder.ts
import { execFile } from "child_process";
import * as fs2 from "fs";
import * as fsp from "fs/promises";
import * as os from "os";
import * as path from "path";

// src/java/zip-reader.ts
import * as fs from "fs";
import * as zlib from "zlib";
var EOCD_SIGNATURE = 101010256;
var CENTRAL_DIR_SIGNATURE = 33639248;
var LOCAL_FILE_SIGNATURE = 67324752;
var EOCD_MIN_SIZE = 22;
var EOCD_MAX_COMMENT = 65535;
var COMPRESSION_STORED = 0;
var COMPRESSION_DEFLATED = 8;
function readU32LE(buf, offset) {
  return buf.readUInt32LE(offset);
}
function readU16LE(buf, offset) {
  return buf.readUInt16LE(offset);
}
function findEOCD(fd, fileSize) {
  const searchStart = Math.max(0, fileSize - EOCD_MAX_COMMENT - EOCD_MIN_SIZE);
  let chunkOffset = fileSize;
  while (chunkOffset > searchStart) {
    const readSize = Math.min(1024, chunkOffset - searchStart);
    chunkOffset -= readSize;
    const buf = Buffer.alloc(readSize);
    fs.readSync(fd, buf, 0, readSize, chunkOffset);
    for (let i = readSize - 4; i >= 0; i--) {
      if (buf.readUInt32LE(i) === EOCD_SIGNATURE) {
        const eocdOffset = chunkOffset + i;
        const eocdSize = Math.min(EOCD_MIN_SIZE + EOCD_MAX_COMMENT, fileSize - eocdOffset);
        const eocdBuf = Buffer.alloc(eocdSize);
        fs.readSync(fd, eocdBuf, 0, eocdSize, eocdOffset);
        return { offset: eocdOffset, buf: eocdBuf };
      }
    }
  }
  throw new Error("Not a valid ZIP file: EOCD signature not found");
}
function parseCentralDirectory(fd, eocdBuf) {
  const centralDirOffset = readU32LE(eocdBuf, 16);
  const totalEntries = readU16LE(eocdBuf, 10);
  const entries = [];
  let offset = centralDirOffset;
  for (let i = 0; i < totalEntries; i++) {
    const headerBuf = Buffer.alloc(46);
    fs.readSync(fd, headerBuf, 0, 46, offset);
    if (readU32LE(headerBuf, 0) !== CENTRAL_DIR_SIGNATURE) {
      throw new Error(`Corrupt central directory at offset ${offset}`);
    }
    const compressionMethod = readU16LE(headerBuf, 10);
    const compressedSize = readU32LE(headerBuf, 20);
    const uncompressedSize = readU32LE(headerBuf, 24);
    const fileNameLen = readU16LE(headerBuf, 28);
    const extraLen = readU16LE(headerBuf, 30);
    const commentLen = readU16LE(headerBuf, 32);
    const localHeaderOffset = readU32LE(headerBuf, 42);
    const nameBuf = Buffer.alloc(fileNameLen);
    fs.readSync(fd, nameBuf, 0, fileNameLen, offset + 46);
    const fileName = nameBuf.toString("utf8");
    entries.push({
      fileName,
      compressionMethod,
      compressedSize,
      uncompressedSize,
      localHeaderOffset
    });
    offset += 46 + fileNameLen + extraLen + commentLen;
  }
  return entries;
}
function readJarEntry(jarPath, entryName) {
  const fd = fs.openSync(jarPath, "r");
  try {
    const stat = fs.fstatSync(fd);
    const fileSize = stat.size;
    const eocd = findEOCD(fd, fileSize);
    const entries = parseCentralDirectory(fd, eocd.buf);
    const target = entries.find((e) => e.fileName === entryName);
    if (!target) return null;
    const localHeaderBuf = Buffer.alloc(30);
    fs.readSync(fd, localHeaderBuf, 0, 30, target.localHeaderOffset);
    if (readU32LE(localHeaderBuf, 0) !== LOCAL_FILE_SIGNATURE) {
      throw new Error(`Corrupt local file header at offset ${target.localHeaderOffset}`);
    }
    const localFileNameLen = readU16LE(localHeaderBuf, 26);
    const localExtraLen = readU16LE(localHeaderBuf, 28);
    const dataOffset = target.localHeaderOffset + 30 + localFileNameLen + localExtraLen;
    const compressedBuf = Buffer.alloc(target.compressedSize);
    fs.readSync(fd, compressedBuf, 0, target.compressedSize, dataOffset);
    let data;
    if (target.compressionMethod === COMPRESSION_STORED) {
      data = compressedBuf;
    } else if (target.compressionMethod === COMPRESSION_DEFLATED) {
      data = zlib.inflateRawSync(compressedBuf);
    } else {
      throw new Error(
        `Unsupported compression method ${target.compressionMethod} for entry "${entryName}"`
      );
    }
    return { fileName: target.fileName, data };
  } finally {
    fs.closeSync(fd);
  }
}

// src/java/class-source-finder.ts
var ClassSourceFinder = class _ClassSourceFinder {
  projectRoot;
  repoPaths;
  javapCommand;
  maxJarScan;
  signal;
  static defaultRepoPaths() {
    const home = os.homedir();
    const candidates = [path.join(home, ".m2", "repository"), path.join(home, ".gradle", "caches")];
    return candidates.filter((p) => fs2.existsSync(p));
  }
  constructor(options) {
    this.projectRoot = path.resolve(options.projectRoot);
    this.repoPaths = options.repoPaths && options.repoPaths.length > 0 ? options.repoPaths.map((p) => path.resolve(p)) : _ClassSourceFinder.defaultRepoPaths();
    this.javapCommand = options.javapCommand ?? "javap";
    this.maxJarScan = options.maxJarScan ?? 2e3;
    this.signal = options.signal;
  }
  async findSource(fullyQualifiedName, options) {
    this.throwIfAborted();
    const projectResult = await this.searchProject(fullyQualifiedName);
    if (projectResult) return projectResult;
    return this.searchRepositories(fullyQualifiedName, options?.jarKeyword);
  }
  async findSourceInJar(fullyQualifiedName, jarPath) {
    this.throwIfAborted();
    const resolvedJarPath = path.resolve(jarPath);
    if (!fs2.existsSync(resolvedJarPath)) {
      return { found: false, method: "not-found" };
    }
    const classEntry = `${fullyQualifiedName.replace(/\./g, "/")}.class`;
    try {
      const content = readJarEntry(resolvedJarPath, classEntry);
      if (!content) return { found: false, method: "not-found" };
      const source = await this.decompileFromJar(resolvedJarPath, content.data, fullyQualifiedName);
      return { found: true, source, method: "jar", sourcePath: resolvedJarPath };
    } catch (err) {
      return { found: false, method: "not-found" };
    }
  }
  async searchProject(fqn) {
    const simpleName = this.simpleClassName(fqn);
    const suffixes = [`${simpleName}.java`, `${simpleName}.java.txt`];
    const queue = [this.projectRoot];
    while (queue.length > 0) {
      this.throwIfAborted();
      const dir = queue.shift();
      let entries;
      try {
        entries = await fsp.readdir(dir, { withFileTypes: true });
      } catch {
        continue;
      }
      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === "node_modules" || entry.name === ".git" || entry.name === "target" || entry.name === "build" || entry.name === "dist" || entry.name === ".idea" || entry.name === ".vscode" || entry.name === ".gradle") {
            continue;
          }
          queue.push(fullPath);
        } else if (entry.isFile()) {
          if (suffixes.includes(entry.name)) {
            const source = await fsp.readFile(fullPath, "utf-8");
            return { found: true, source, method: "project", sourcePath: fullPath };
          }
        }
      }
    }
    return null;
  }
  async searchRepositories(fqn, jarKeyword) {
    const javaEntry = `${fqn.replace(/\./g, "/")}.java`;
    const classEntry = `${fqn.replace(/\./g, "/")}.class`;
    const sourceJars = [];
    const regularJars = [];
    for (const repoDir of this.repoPaths) {
      await this.walkForJars(repoDir, sourceJars, regularJars, jarKeyword);
    }
    for (const jarPath of sourceJars) {
      this.throwIfAborted();
      try {
        const content = readJarEntry(jarPath, javaEntry);
        if (content) {
          return {
            found: true,
            source: content.data.toString("utf-8"),
            method: "m2-source-jar",
            sourcePath: jarPath
          };
        }
      } catch {
      }
    }
    let scanned = 0;
    for (const jarPath of regularJars) {
      this.throwIfAborted();
      if (scanned >= this.maxJarScan) break;
      scanned++;
      try {
        const content = readJarEntry(jarPath, classEntry);
        if (content) {
          const source = await this.decompileFromJar(jarPath, content.data, fqn);
          return { found: true, source, method: "m2-jar", sourcePath: jarPath };
        }
      } catch {
      }
    }
    return { found: false, method: "not-found" };
  }
  static MAX_WALK_DEPTH = 64;
  async walkForJars(dir, sourceJars, regularJars, keyword, depth = 0) {
    if (depth >= _ClassSourceFinder.MAX_WALK_DEPTH) return;
    let entries;
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      this.throwIfAborted();
      if (sourceJars.length + regularJars.length >= this.maxJarScan) return;
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await this.walkForJars(fullPath, sourceJars, regularJars, keyword, depth + 1);
      } else if (entry.isFile() && entry.name.endsWith(".jar")) {
        if (!keyword || fullPath.toLowerCase().includes(keyword.toLowerCase())) {
          if (entry.name.endsWith("-sources.jar") || entry.name.includes("-sources-")) {
            sourceJars.push(fullPath);
          } else {
            regularJars.push(fullPath);
          }
        }
      }
    }
  }
  async decompileFromJar(jarPath, classBytes, fqn) {
    const tmpDir = await fsp.mkdtemp(path.join(os.tmpdir(), "reasonix-java-src-"));
    try {
      const pkgPath = fqn.replace(/\./g, path.sep);
      const classDir = path.join(tmpDir, path.dirname(pkgPath));
      await fsp.mkdir(classDir, { recursive: true });
      const classFile = path.join(tmpDir, `${pkgPath}.class`);
      await fsp.writeFile(classFile, classBytes);
      const raw = await this.runJavap(fqn, tmpDir);
      return _ClassSourceFinder.compressJavapOutput(raw);
    } finally {
      await fsp.rm(tmpDir, { recursive: true, force: true }).catch(() => {
      });
    }
  }
  // Strip constant pool, debug tables (LineNumberTable / LocalVariableTable /
  // StackMapTable), and "Compiled from …" from javap output — cuts ~60-80% of
  // tokens for AI consumption while keeping method sigs + bytecode.
  static compressJavapOutput(raw) {
    const lines = raw.split("\n");
    const out = [];
    let skipUntilIndent = null;
    for (const line of lines) {
      if (/^\s+#\d+\s*=/.test(line)) continue;
      if (skipUntilIndent !== null) {
        const m = line.match(/^(\s*)/);
        const indent = m?.[1]?.length ?? 0;
        if (indent > skipUntilIndent) continue;
        skipUntilIndent = null;
        if (line.trim() === "") continue;
      }
      const debugMatch = line.match(/^(\s+)(LineNumberTable|LocalVariableTable|StackMapTable):/);
      if (debugMatch) {
        skipUntilIndent = debugMatch[1].length;
        continue;
      }
      if (line.startsWith("Compiled from ")) continue;
      out.push(line);
    }
    return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  runJavap(className, classPath) {
    return new Promise((resolve2, reject) => {
      execFile(
        this.javapCommand,
        ["-c", "-p", "-cp", classPath, className],
        {
          maxBuffer: 15 * 1024 * 1024,
          timeout: 3e4,
          signal: this.signal
        },
        (err, stdout, stderr) => {
          if (err) {
            const msg = [stdout, stderr].filter(Boolean).join("\n") || err.message;
            reject(new Error(`javap failed: ${msg}`));
            return;
          }
          resolve2(stdout);
        }
      );
    });
  }
  simpleClassName(fqn) {
    const lastDot = fqn.lastIndexOf(".");
    return lastDot === -1 ? fqn : fqn.slice(lastDot + 1);
  }
  throwIfAborted() {
    if (this.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
  }
};

// src/tools/java-source.ts
function registerJavaSourceTool(registry, opts = {}) {
  registry.register({
    name: "java_source",
    description: [
      "Find and return Java source code by fully-qualified class name.",
      "",
      "Search mode: walk the project tree for a `.java` file, then scan `~/.m2/repository` jars whose filename or path contains `jarKeyword`.",
      "",
      "Returns the source text (or decompiled bytecode) on success, or a clear 'not found' message.",
      "Only call this tool once per class name \u2014 it's I/O heavy."
    ].join("\n"),
    readOnly: true,
    parameters: {
      type: "object",
      properties: {
        className: {
          type: "string",
          description: 'Fully qualified Java class name, e.g. "com.google.common.collect.Lists" or "org.springframework.web.servlet.DispatcherServlet".'
        },
        jarKeyword: {
          type: "string",
          description: 'Only search jars whose filename or path contains this keyword (case-insensitive). Keep it short \u2014 a narrow substring like "spring-core", "guava", or "mycompany-utils" scans faster and matches more precisely than a long fragment.'
        }
      },
      required: ["className", "jarKeyword"]
    },
    parallelSafe: true,
    fn: async (args) => {
      const className = (args?.className ?? "").trim();
      if (!className) {
        throw new Error("java_source: `className` is required");
      }
      if (!/^[a-zA-Z_$][\w$]*(\.[a-zA-Z_$][\w$]*)*$/.test(className)) {
        throw new Error(
          `java_source: "${className}" is not a valid fully qualified Java class name. Expected format: \`com.example.MyClass\``
        );
      }
      const jarKeyword = args.jarKeyword.trim();
      if (!jarKeyword) {
        throw new Error("java_source: `jarKeyword` must not be empty");
      }
      const projectRoot = opts.projectRoot || process.cwd();
      const finder = new ClassSourceFinder({ projectRoot });
      const result = await finder.findSource(className, { jarKeyword });
      if (!result.found) {
        const keywordLine = `  \u2022 Maven .m2 / Gradle cache for jars containing keyword "${jarKeyword}"`;
        const tip = "Try a different keyword, or check if the class is in a different library.";
        return JSON.stringify({
          status: "not-found",
          className,
          message: `No source found for "${className}". Searched:
  \u2022 ${projectRoot}/ for matching .java files
  ${keywordLine}

${tip}`
        });
      }
      return JSON.stringify({
        status: "found",
        className,
        method: result.method,
        sourcePath: result.sourcePath,
        source: result.source
      });
    }
  });
  return registry;
}

// src/tools/scaffold.ts
var VALID_SKILL_NAME = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/;
var VALID_SERVER_NAME = /^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$/;
var VALID_TOOL_NAME = /^[a-zA-Z_][a-zA-Z0-9_-]*$/;
function registerScaffoldTools(registry, opts = {}) {
  const configPath = opts.configPath ?? defaultConfigPath();
  registry.register({
    name: "create_skill",
    description: 'Scaffold a SKILL.md the user can later invoke via `/skill <name>`. Frontmatter (description / allowed_tools / run_as / model) is filled from structured args here. Use `run_as: "subagent"` for read-and-synthesize playbooks; default inline appends body to parent log. Refuses to overwrite existing skills.',
    parameters: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Identifier \u2014 letters/digits/`_`/`-`/`.`, 1\u201364 chars. Becomes filename + frontmatter `name`."
        },
        description: {
          type: "string",
          description: 'One-liner for the skills index. Lead with the verb ("Run X and \u2026").'
        },
        body: {
          type: "string",
          description: "Markdown playbook. Reference tools by name."
        },
        scope: {
          type: "string",
          enum: ["project", "global"],
          description: "`project` (default) = workspace .reasonix/skills/; `global` = ~/.reasonix/skills/."
        },
        allowed_tools: {
          type: "array",
          items: { type: "string" },
          description: "Optional tool allowlist for `run_as: subagent`. Omit for full inherited toolset."
        },
        run_as: {
          type: "string",
          enum: ["inline", "subagent"],
          description: "inline (default) appends body to parent log. subagent spawns isolated child; only final answer returns."
        },
        model: {
          type: "string",
          enum: ["deepseek-v4-flash", "deepseek-v4-pro"],
          description: "Subagent model override. Default flash; use pro only when the playbook needs it."
        }
      },
      required: ["name", "description", "body"]
    },
    fn: async (args) => {
      const name = typeof args.name === "string" ? args.name.trim() : "";
      if (!VALID_SKILL_NAME.test(name)) {
        return JSON.stringify({
          error: `invalid skill name: ${JSON.stringify(name)} \u2014 use letters, digits, _, -, .`
        });
      }
      const description = typeof args.description === "string" ? args.description.trim().replace(/\n+/g, " ") : "";
      if (!description) {
        return JSON.stringify({
          error: "create_skill requires a non-empty 'description'"
        });
      }
      const body = typeof args.body === "string" ? args.body : "";
      if (!body.trim()) {
        return JSON.stringify({ error: "create_skill requires a non-empty 'body'" });
      }
      const scope = args.scope === "global" ? "global" : opts.projectRoot ? "project" : "global";
      const runAs = args.run_as === "subagent" ? "subagent" : "inline";
      const allowedTools = parseAllowedTools(args.allowed_tools);
      if (allowedTools && "error" in allowedTools) {
        return JSON.stringify({ error: allowedTools.error });
      }
      const model = typeof args.model === "string" && args.model.startsWith("deepseek-") ? args.model : void 0;
      const content = serializeSkill({
        name,
        description,
        runAs,
        allowedTools: allowedTools ?? void 0,
        model,
        body
      });
      const store = new SkillStore({
        homeDir: opts.homeDir,
        projectRoot: opts.projectRoot,
        customSkillPaths: opts.projectRoot ? loadResolvedSkillPaths(opts.projectRoot, configPath) : []
      });
      const result = store.createWithContent(name, scope, content);
      if ("error" in result) {
        return JSON.stringify({ error: result.error });
      }
      return JSON.stringify({
        success: true,
        path: result.path,
        scope,
        name,
        run_as: runAs
      });
    }
  });
  registry.register({
    name: "add_mcp_server",
    description: 'Register a new MCP server in the user\'s config (`mcp` array). Takes effect next session. Use stdio for local commands, sse/streamable-http for remote. Pass `from_catalog` (e.g. "filesystem", "github") to auto-fill command+args from the bundled catalog. Refuses name collisions.',
    parameters: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Namespace prefix on every tool. Letters/digits/`_`/`-`, must start with letter or `_`."
        },
        transport: {
          type: "string",
          enum: ["stdio", "sse", "streamable-http"],
          description: "stdio = local command via stdin/stdout; sse / streamable-http = remote. Required unless `from_catalog` is set."
        },
        command: {
          type: "string",
          description: "Argv[0] for stdio \u2014 typically `npx` or a binary path."
        },
        args: {
          type: "array",
          items: { type: "string" },
          description: 'Remaining argv for stdio \u2014 e.g. `["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]`.'
        },
        url: {
          type: "string",
          description: "Endpoint URL for sse / streamable-http \u2014 must be http(s)://."
        },
        from_catalog: {
          type: "string",
          description: "Bundled catalog shortcut: filesystem / memory / github / puppeteer / everything. Fills command+args; user supplies user-args via `args`."
        }
      },
      required: ["name"]
    },
    fn: async (args) => {
      const name = typeof args.name === "string" ? args.name.trim() : "";
      if (!VALID_SERVER_NAME.test(name)) {
        return JSON.stringify({
          error: `invalid server name: ${JSON.stringify(name)} \u2014 must match [a-zA-Z_][a-zA-Z0-9_-]*`
        });
      }
      const specStr = buildSpecString({
        name,
        transport: typeof args.transport === "string" ? args.transport : void 0,
        command: typeof args.command === "string" ? args.command : void 0,
        argv: Array.isArray(args.args) ? args.args.filter((a) => typeof a === "string") : void 0,
        url: typeof args.url === "string" ? args.url : void 0,
        fromCatalog: typeof args.from_catalog === "string" ? args.from_catalog : void 0
      });
      if ("error" in specStr) {
        return JSON.stringify({ error: specStr.error });
      }
      let parsed;
      try {
        parsed = parseMcpSpec(specStr.spec);
      } catch (err) {
        return JSON.stringify({ error: err.message });
      }
      if (parsed.transport === "stdio") {
        try {
          preflightStdioSpec(parsed);
        } catch (err) {
          return JSON.stringify({ error: err.message });
        }
      }
      const cfg = readConfig(configPath);
      const existing = cfg.mcp ?? [];
      const collision = existing.find((s) => parseSpecName(s) === name);
      if (collision) {
        return JSON.stringify({
          error: `MCP server ${JSON.stringify(name)} already registered: ${collision}`
        });
      }
      cfg.mcp = [...existing, specStr.spec];
      writeConfig(cfg, configPath);
      return JSON.stringify({
        success: true,
        name,
        transport: parsed.transport,
        spec: specStr.spec,
        config_path: configPath,
        active_on_next_launch: true
      });
    }
  });
  return registry;
}
function serializeSkill(args) {
  const lines = ["---", `name: ${args.name}`, `description: ${args.description}`];
  if (args.runAs === "subagent") {
    lines.push("runAs: subagent");
  }
  if (args.allowedTools && args.allowedTools.length > 0) {
    lines.push(`allowed-tools: ${args.allowedTools.join(", ")}`);
  }
  if (args.model) {
    lines.push(`model: ${args.model}`);
  }
  lines.push("---", "");
  return `${lines.join("\n")}
${args.body.trim()}
`;
}
function parseAllowedTools(raw) {
  if (raw === void 0 || raw === null) return void 0;
  if (!Array.isArray(raw)) {
    return { error: "'allowed_tools' must be an array of tool-name strings" };
  }
  const out = [];
  for (const v of raw) {
    if (typeof v !== "string") {
      return { error: "'allowed_tools' entries must be strings" };
    }
    const trimmed = v.trim();
    if (!trimmed) continue;
    if (!VALID_TOOL_NAME.test(trimmed)) {
      return { error: `invalid tool name in allowed_tools: ${JSON.stringify(trimmed)}` };
    }
    out.push(trimmed);
  }
  return out.length > 0 ? out : void 0;
}
function buildSpecString(input) {
  if (input.fromCatalog) {
    const entry = MCP_CATALOG.find((e) => e.name === input.fromCatalog);
    if (!entry) {
      const known = MCP_CATALOG.map((e) => e.name).join(", ");
      return {
        error: `unknown catalog entry: ${JSON.stringify(input.fromCatalog)} \u2014 known: ${known}`
      };
    }
    const userArgs = input.argv ?? [];
    if (entry.userArgs && userArgs.length === 0) {
      return {
        error: `catalog entry "${entry.name}" needs ${entry.userArgs} \u2014 pass it via the 'args' parameter`
      };
    }
    const tail = userArgs.map(quoteIfNeeded).join(" ");
    const body = `npx -y ${entry.package}${tail ? ` ${tail}` : ""}`;
    return { spec: `${input.name}=${body}` };
  }
  const transport = input.transport;
  if (!transport) {
    return { error: "add_mcp_server requires 'transport' (or 'from_catalog')" };
  }
  if (transport === "stdio") {
    if (!input.command || !input.command.trim()) {
      return { error: "stdio transport requires 'command'" };
    }
    const tail = (input.argv ?? []).map(quoteIfNeeded).join(" ");
    const body = `${quoteIfNeeded(input.command.trim())}${tail ? ` ${tail}` : ""}`;
    return { spec: `${input.name}=${body}` };
  }
  if (transport === "sse" || transport === "streamable-http") {
    if (!input.url || !/^https?:\/\//i.test(input.url)) {
      return { error: `${transport} transport requires an http(s):// 'url'` };
    }
    const prefix = transport === "streamable-http" ? "streamable+" : "";
    return { spec: `${input.name}=${prefix}${input.url.trim()}` };
  }
  return { error: `unknown transport: ${JSON.stringify(transport)}` };
}
function parseSpecName(spec) {
  const m = spec.trim().match(/^([a-zA-Z_][a-zA-Z0-9_-]*)=/);
  return m ? m[1] ?? null : null;
}
function quoteIfNeeded(s) {
  return /\s|"/.test(s) ? `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"` : s;
}

// src/code/setup.ts
function applyPlanMode(tools, editMode) {
  tools.setPlanMode(editMode === "plan");
}
async function buildCodeToolset(opts) {
  const tools = new ToolRegistry({ rateLimit: loadToolRateLimit() });
  applyPlanMode(tools, loadEditMode(opts.configPath));
  const jobs = new JobRegistry();
  const outlineThresholdBytes = loadFilesystemOutlineThresholdBytes();
  const registerRooted = (root) => {
    registerFilesystemTools(tools, { rootDir: root, outlineThresholdBytes });
    const cfg = readConfig();
    registerShellTools(tools, {
      rootDir: root,
      extraAllowed: () => loadProjectShellAllowed(root),
      allowAll: () => loadEditMode() === "yolo",
      jobs,
      onJobsChanged: opts.onJobsChanged,
      sensitivePaths: cfg.sensitivePaths
    });
    registerMemoryTools(tools, { projectRoot: root });
    registerCodeQueryTools(tools, { rootDir: root });
  };
  const reBootstrapSemantic = async (root) => {
    const result = await bootstrapSemanticSearchInCodeMode(tools, root);
    if (!result.enabled) tools.unregister("semantic_search");
    return result;
  };
  registerRooted(opts.rootDir);
  registerPlanTool(tools);
  registerChoiceTool(tools);
  registerTodoTool(tools);
  registerScaffoldTools(tools, { projectRoot: opts.rootDir });
  if (searchEnabled()) {
    registerWebTools(tools);
  }
  if (loadJavaSourceEnabled()) {
    registerJavaSourceTool(tools, { projectRoot: opts.rootDir });
  }
  let subagentClient = null;
  registerSkillTools(tools, {
    projectRoot: opts.rootDir,
    customSkillPaths: loadResolvedSkillPaths(opts.rootDir),
    subagentModels: loadSubagentModels(),
    onSkillInstalled: opts.onSkillInstalled,
    subagentRunner: async (skill, task, signal) => {
      if (!subagentClient) {
        const ep = loadEndpoint();
        subagentClient = new DeepSeekClient({ apiKey: ep.apiKey, baseUrl: ep.baseUrl });
      }
      const result = await spawnSubagent({
        client: subagentClient,
        parentRegistry: tools,
        parentSignal: signal,
        system: skill.body,
        task,
        model: skill.model,
        allowedTools: skill.allowedTools,
        skillName: skill.name,
        // Late-bound: the TUI's `useSubagent` writes the live callback into
        // SHARED_SUBAGENT_SINK after mount. Until then `.current` is null
        // and the events are silently dropped — that's fine for non-TUI
        // callers (`reasonix chat --transcript`, library use).
        sink: opts.subagentSink ?? SHARED_SUBAGENT_SINK
      });
      return formatSubagentResult(result);
    }
  });
  const semantic = await reBootstrapSemantic(opts.rootDir);
  return { tools, jobs, registerRooted, reBootstrapSemantic, semantic };
}

export {
  applyPlanMode,
  buildCodeToolset
};
//# sourceMappingURL=chunk-2WZT27GR.js.map