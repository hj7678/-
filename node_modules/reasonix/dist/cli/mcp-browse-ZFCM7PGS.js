#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  loadOverlay
} from "./chunk-JMBMLOBP.js";
import {
  loadMorePages,
  openRegistry,
  specStringFor
} from "./chunk-XJXDHAES.js";
import {
  Box_default,
  Text,
  renderSync,
  require_react,
  use_app_default,
  use_input_default
} from "./chunk-U25OJR4Y.js";
import "./chunk-PLHAZOLZ.js";
import {
  loadDotenv
} from "./chunk-2UQP6H6T.js";
import {
  readConfig,
  writeConfig
} from "./chunk-GCNBIWK7.js";
import {
  __toESM
} from "./chunk-TUK7OWJA.js";

// src/cli/commands/mcp-browse.tsx
var import_react = __toESM(require_react(), 1);
var VISIBLE_ROWS = 12;
function rankAndFilter(entries, query) {
  const q = query.trim().toLowerCase();
  const list = q ? entries.filter((e) => `${e.name} ${e.title} ${e.description}`.toLowerCase().includes(q)) : entries;
  return [...list].sort((a, b) => {
    const ap = a.popularity ?? -1;
    const bp = b.popularity ?? -1;
    if (ap !== bp) return bp - ap;
    return a.name.localeCompare(b.name);
  });
}
function McpBrowseApp() {
  const app = use_app_default();
  const [state, setState] = (0, import_react.useState)({
    handle: null,
    loading: true,
    query: "",
    selected: 0,
    status: "opening registry\u2026"
  });
  const setStatus = (0, import_react.useCallback)((status) => {
    setState((s) => ({ ...s, status }));
  }, []);
  (0, import_react.useEffect)(() => {
    let cancelled = false;
    (async () => {
      try {
        const handle = await openRegistry({});
        if (cancelled) return;
        const ageMs = Date.now() - handle.fetchedAt;
        const ageStr = ageMs < 6e4 ? `${Math.floor(ageMs / 1e3)}s` : `${Math.floor(ageMs / 6e4)}m`;
        setState((s) => ({
          ...s,
          handle,
          loading: false,
          status: `${handle.source} \xB7 ${handle.cache.entries.length} entries${handle.fromCache ? ` \xB7 cached ${ageStr} ago` : ""}`
        }));
      } catch (err) {
        if (cancelled) return;
        setState((s) => ({ ...s, loading: false, status: `error: ${err.message}` }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  const filtered = (0, import_react.useMemo)(() => {
    if (!state.handle) return [];
    return rankAndFilter(state.handle.cache.entries, state.query);
  }, [state.handle, state.query]);
  const selected = filtered[state.selected];
  const fetchMore = (0, import_react.useCallback)(async () => {
    if (!state.handle || state.loading) return;
    if (state.handle.cache.pagination.nextCursor === null) {
      setStatus("no more pages \u2014 registry exhausted");
      return;
    }
    setState((s) => ({ ...s, loading: true, status: "loading more\u2026" }));
    try {
      const r = await loadMorePages(state.handle, { pages: 5 });
      setState((s) => ({
        ...s,
        loading: false,
        status: `+${r.newEntries} entries (${state.handle?.cache.entries.length ?? 0} total)${r.exhausted ? " \xB7 exhausted" : ""}`
      }));
    } catch (err) {
      setState((s) => ({ ...s, loading: false, status: `error: ${err.message}` }));
    }
  }, [state.handle, state.loading, setStatus]);
  const install = (0, import_react.useCallback)(
    (entry) => {
      if (!entry.install) {
        setStatus(`${entry.name} has no install info (smithery listing)`);
        return;
      }
      try {
        const spec = specStringFor(entry.name, entry.install);
        const cfg = readConfig();
        const existing = cfg.mcp ?? [];
        if (existing.includes(spec)) {
          setStatus(`already installed: ${spec}`);
          return;
        }
        writeConfig({ ...cfg, mcp: [...existing, spec] });
        setStatus(`installed \u2192 ${spec}`);
      } catch (err) {
        setStatus(`install failed: ${err.message}`);
      }
    },
    [setStatus]
  );
  use_input_default((input, key) => {
    if (key.escape || key.ctrl && input === "c") {
      app.exit();
      return;
    }
    if (key.upArrow) {
      setState((s) => ({ ...s, selected: Math.max(0, s.selected - 1) }));
      return;
    }
    if (key.downArrow) {
      setState((s) => ({ ...s, selected: Math.min(filtered.length - 1, s.selected + 1) }));
      return;
    }
    if (key.return) {
      if (selected) install(selected);
      return;
    }
    if (key.tab || key.ctrl && input === "n") {
      void fetchMore();
      return;
    }
    if (key.backspace || key.delete) {
      setState((s) => ({ ...s, query: s.query.slice(0, -1), selected: 0 }));
      return;
    }
    if (input && !key.ctrl && !key.meta) {
      setState((s) => ({ ...s, query: s.query + input, selected: 0 }));
    }
  });
  const overlay = (0, import_react.useMemo)(() => loadOverlay("zh-CN"), []);
  const start = Math.max(
    0,
    Math.min(state.selected - Math.floor(VISIBLE_ROWS / 2), filtered.length - VISIBLE_ROWS)
  );
  const window = filtered.slice(Math.max(0, start), Math.max(0, start) + VISIBLE_ROWS);
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:cyan" }, "\u25C8 MCP marketplace"), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, `  \xB7  ${state.status}`)), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, null, "search: "), /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:white" }, state.query || "(type to filter)"), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, `  ${filtered.length} match${filtered.length === 1 ? "" : "es"}`)), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, flexDirection: "column" }, window.length === 0 ? /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, state.loading ? "loading\u2026" : "no entries") : window.map((e, i) => {
    const idx = (start || 0) + i;
    const active = idx === state.selected;
    const tag = e.source === "official" ? "[off]" : e.source === "smithery" ? "[smt]" : "[loc]";
    const pop = e.popularity !== void 0 ? ` \xB7 ${e.popularity.toLocaleString()}` : "";
    return /* @__PURE__ */ import_react.default.createElement(Box_default, { key: e.name }, /* @__PURE__ */ import_react.default.createElement(Text, { color: active ? "ansi:cyan" : void 0 }, active ? "\u25B8 " : "  "), /* @__PURE__ */ import_react.default.createElement(Text, { bold: active }, e.name.padEnd(40).slice(0, 40)), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, ` ${tag}${pop}`));
  })), selected ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, flexDirection: "column" }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:white" }, overlay?.[selected.name]?.title ?? selected.title, overlay?.[selected.name] ? /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, `  \xB7  ${selected.title}`) : null), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, overlay?.[selected.name]?.description ?? selected.description?.slice(0, 160) ?? null), selected.install ? /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, `spec: ${selected.install.runtime} ${selected.install.packageId ?? selected.install.url ?? "\u2014"} \xB7 ${selected.install.transport}`) : /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "(smithery listing \u2014 install info not exposed)"), selected.install?.requiredEnv?.length ? /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:yellow" }, `needs: ${selected.install.requiredEnv.join(", ")}`) : null) : null, /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "type to filter \xB7 \u2191\u2193 pick \xB7 enter install \xB7 tab load more \xB7 esc quit")));
}
async function mcpBrowseCommand(_opts = {}) {
  loadDotenv();
  const { waitUntilExit } = renderSync(/* @__PURE__ */ import_react.default.createElement(McpBrowseApp, null), {
    exitOnCtrlC: true,
    patchConsole: false
  });
  await waitUntilExit();
}
export {
  mcpBrowseCommand
};
//# sourceMappingURL=mcp-browse-ZFCM7PGS.js.map