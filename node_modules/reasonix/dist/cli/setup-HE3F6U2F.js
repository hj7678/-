#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  MultiSelect,
  SingleSelect
} from "./chunk-ANYWFUKM.js";
import {
  ThemeProvider,
  useTheme
} from "./chunk-BHSAOFHR.js";
import {
  Box_default,
  Text,
  TextInput,
  renderSync,
  require_react,
  use_app_default,
  use_input_default
} from "./chunk-U25OJR4Y.js";
import {
  MCP_CATALOG
} from "./chunk-PLHAZOLZ.js";
import {
  loadDotenv
} from "./chunk-2UQP6H6T.js";
import {
  detectSystemLanguage,
  getLanguage,
  getSupportedLanguages,
  notifyLanguageChange,
  onLanguageChange,
  setLanguage,
  t
} from "./chunk-U7G72DHQ.js";
import {
  defaultConfigPath,
  isPlausibleKey,
  listThemeNames,
  loadApiKey,
  loadBaseUrl,
  loadTheme,
  readConfig,
  redactKey,
  resolveThemePreference,
  writeConfig
} from "./chunk-GCNBIWK7.js";
import {
  __toESM
} from "./chunk-TUK7OWJA.js";

// src/cli/commands/setup.tsx
var import_react2 = __toESM(require_react(), 1);

// src/cli/ui/Wizard.tsx
import { mkdirSync, statSync } from "fs";
var import_react = __toESM(require_react(), 1);
var CATALOG_BY_NAME = new Map(MCP_CATALOG.map((e) => [e.name, e]));
var LANGUAGE_LABELS = {
  EN: "English",
  "zh-CN": "\u7B80\u4F53\u4E2D\u6587",
  de: "Deutsch",
  ru: "\u0420\u0443\u0441\u0441\u043A\u0438\u0439"
};
function Wizard({
  onComplete,
  onCancel,
  existingApiKey,
  forceApiKeyStep = false,
  validateApiKey = validateDeepSeekApiKey,
  initial
}) {
  const { exit } = use_app_default();
  const [, setLanguageVersion] = (0, import_react.useState)(0);
  (0, import_react.useEffect)(() => onLanguageChange(() => setLanguageVersion((v) => v + 1)), []);
  const [previewTheme, setPreviewTheme] = (0, import_react.useState)(
    () => resolveThemePreference(initial?.theme ?? loadTheme(), process.env.REASONIX_THEME)
  );
  const [step, setStep] = (0, import_react.useState)("language");
  const [data, setData] = (0, import_react.useState)(() => ({
    language: getLanguage(),
    theme: resolveThemePreference(initial?.theme ?? loadTheme(), process.env.REASONIX_THEME),
    apiKey: existingApiKey ?? "",
    selectedCatalog: deriveInitialCatalog(initial?.mcp ?? []),
    catalogArgs: {}
  }));
  const [error, setError] = (0, import_react.useState)(null);
  use_input_default((_input, key) => {
    if (key.escape && step !== "saved" && onCancel) onCancel();
  });
  const content = (() => {
    if (step === "language") {
      return /* @__PURE__ */ import_react.default.createElement(
        LanguageStep,
        {
          initialValue: data.language,
          onSubmit: (lang) => {
            setLanguage(lang);
            notifyLanguageChange();
            setData((d) => ({ ...d, language: lang }));
            setStep("theme");
          }
        }
      );
    }
    if (step === "theme") {
      return /* @__PURE__ */ import_react.default.createElement(
        ThemeStep,
        {
          initialValue: data.theme,
          onPreview: setPreviewTheme,
          onSubmit: (theme) => {
            setData((d) => ({ ...d, theme }));
            setStep(existingApiKey && !forceApiKeyStep ? "mcp" : "apiKey");
          }
        }
      );
    }
    if (step === "apiKey") {
      return /* @__PURE__ */ import_react.default.createElement(
        ApiKeyStep,
        {
          initialValue: data.apiKey,
          validateApiKey,
          onSubmit: (key) => {
            setData((d) => ({ ...d, apiKey: key }));
            setError(null);
            setStep("mcp");
          },
          error,
          onError: setError
        }
      );
    }
    if (step === "mcp") {
      return /* @__PURE__ */ import_react.default.createElement(StepFrame, { title: t("wizard.mcpTitle"), step: 1, total: 2 }, /* @__PURE__ */ import_react.default.createElement(
        MultiSelect,
        {
          items: mcpItems(),
          initialSelected: data.selectedCatalog,
          onSubmit: (selected) => {
            setData((d) => ({ ...d, selectedCatalog: selected }));
            const needsArgs = selected.some((name) => CATALOG_BY_NAME.get(name)?.userArgs);
            setStep(needsArgs ? "mcpArgs" : "review");
          },
          footer: t("wizard.mcpFooterMulti")
        }
      ));
    }
    if (step === "mcpArgs") {
      const pending = data.selectedCatalog.filter((name) => {
        const entry2 = CATALOG_BY_NAME.get(name);
        return entry2?.userArgs && !data.catalogArgs[name];
      });
      if (pending.length === 0) {
        setStep("review");
        return null;
      }
      const currentName = pending[0];
      const entry = CATALOG_BY_NAME.get(currentName);
      return /* @__PURE__ */ import_react.default.createElement(
        McpArgsStep,
        {
          entry,
          error,
          onSubmit: (value) => {
            setData((d) => ({
              ...d,
              catalogArgs: { ...d.catalogArgs, [currentName]: value }
            }));
            setError(null);
          },
          onError: setError
        }
      );
    }
    if (step === "review") {
      const specs = data.selectedCatalog.map((name) => buildSpec(name, data.catalogArgs));
      return /* @__PURE__ */ import_react.default.createElement(StepFrame, { title: t("wizard.reviewTitle"), step: 2, total: 2 }, /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column" }, /* @__PURE__ */ import_react.default.createElement(
        SummaryLine,
        {
          label: t("wizard.reviewLabelLanguage"),
          value: LANGUAGE_LABELS[data.language]
        }
      ), /* @__PURE__ */ import_react.default.createElement(SummaryLine, { label: t("wizard.reviewLabelApiKey"), value: redactKey(data.apiKey) }), /* @__PURE__ */ import_react.default.createElement(SummaryLine, { label: t("wizard.reviewLabelTheme"), value: data.theme }), /* @__PURE__ */ import_react.default.createElement(
        SummaryLine,
        {
          label: t("wizard.reviewLabelMcp"),
          value: specs.length === 0 ? t("wizard.reviewMcpNone") : t("wizard.reviewMcpServers", { count: specs.length })
        }
      ), specs.map((spec, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: review-only render, order fixed
        /* @__PURE__ */ import_react.default.createElement(Box_default, { key: i, paddingLeft: 14 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, "\xB7 ", spec))
      )), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, null, t("wizard.reviewSavesTo", { path: defaultConfigPath() }))), error ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:red" }, error)) : null, /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.reviewFooter")))), /* @__PURE__ */ import_react.default.createElement(
        ReviewConfirm,
        {
          onConfirm: () => {
            try {
              const specsNow = data.selectedCatalog.map(
                (name) => buildSpec(name, data.catalogArgs)
              );
              const prev = readConfig();
              const next = {
                ...prev,
                apiKey: data.apiKey,
                theme: data.theme,
                mcp: specsNow,
                setupCompleted: true
              };
              writeConfig(next);
              setStep("saved");
              onComplete(next);
            } catch (e) {
              setError(t("wizard.reviewSaveError", { message: e.message }));
            }
          }
        }
      ));
    }
    return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", borderStyle: "round", borderColor: "ansi:green", paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:green" }, t("wizard.savedTitle")), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, null, t("ui.welcome"))), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.savedShellHint"))), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.savedFooter"))), /* @__PURE__ */ import_react.default.createElement(ExitOnEnter, { onExit: exit }));
  })();
  return /* @__PURE__ */ import_react.default.createElement(ThemeProvider, { name: previewTheme }, content);
}
var THEME_NAMES = listThemeNames();
function ThemeStep({
  initialValue,
  onPreview,
  onSubmit
}) {
  const initialIndex = Math.max(0, THEME_NAMES.indexOf(initialValue));
  const [index, setIndex] = (0, import_react.useState)(initialIndex);
  const theme = useTheme();
  use_input_default((_input, key) => {
    if (key.upArrow) {
      const next = (index - 1 + THEME_NAMES.length) % THEME_NAMES.length;
      setIndex(next);
      onPreview(THEME_NAMES[next]);
    } else if (key.downArrow) {
      const next = (index + 1) % THEME_NAMES.length;
      setIndex(next);
      onPreview(THEME_NAMES[next]);
    } else if (key.return) {
      onSubmit(THEME_NAMES[index]);
    }
  });
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", borderStyle: "round", borderColor: theme.tone.brand, paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: theme.tone.brand }, t("wizard.themeTitle")), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.themeSubtitle"))), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, flexDirection: "column" }, THEME_NAMES.map((name, i) => /* @__PURE__ */ import_react.default.createElement(Box_default, { key: name }, /* @__PURE__ */ import_react.default.createElement(Text, { color: i === index ? theme.tone.brand : void 0 }, i === index ? "\u25B8 " : "  "), /* @__PURE__ */ import_react.default.createElement(Text, { bold: i === index, color: i === index ? theme.fg.strong : theme.fg.body }, name), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.meta }, " \u2014 "), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.meta }, t(`wizard.themeCaption.${name}`))))), /* @__PURE__ */ import_react.default.createElement(
    Box_default,
    {
      marginTop: 1,
      flexDirection: "column",
      borderStyle: "round",
      borderColor: theme.fg.faint,
      paddingX: 1
    },
    /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.meta }, t("wizard.themeSampleHeading")),
    /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.tone.accent }, "\u25C6 "), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.tone.accent }, t("wizard.themeSampleReasoning"))),
    /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.tone.info }, "\u25A3 "), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.body }, "fs.readFile("), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.tone.ok }, '"main.ts"'), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.body }, ")")),
    /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.meta }, "~/project/main.ts:42")),
    /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.tone.ok }, "ok"), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.faint }, " \xB7 "), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.tone.warn }, "warn"), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.fg.faint }, " \xB7 "), /* @__PURE__ */ import_react.default.createElement(Text, { color: theme.tone.err }, "err"))
  ), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.themeFooter"))));
}
function LanguageStep({
  initialValue,
  onSubmit
}) {
  const items = getSupportedLanguages().map((code) => ({
    value: code,
    label: LANGUAGE_LABELS[code],
    hint: code === detectSystemLanguage() ? "(detected)" : void 0
  }));
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", borderStyle: "round", borderColor: "ansi:cyan", paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:cyan" }, t("wizard.languageTitle")), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.languageSubtitle"))), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(
    SingleSelect,
    {
      items,
      initialValue,
      onSubmit,
      footer: t("wizard.selectFooter")
    }
  )));
}
function ApiKeyStep({
  initialValue,
  validateApiKey,
  onSubmit,
  error,
  onError
}) {
  const [value, setValue] = (0, import_react.useState)("");
  const [checking, setChecking] = (0, import_react.useState)(false);
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", borderStyle: "round", borderColor: "ansi:cyan", paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:cyan" }, t("wizard.welcomeTitle")), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, null, t("wizard.apiKeyPrompt"))), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.apiKeyGetOne")), /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.apiKeySavedLocally", { path: defaultConfigPath() })), initialValue ? /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.apiKeyPreview", { redacted: redactKey(initialValue) })) : null, /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:cyan" }, t("wizard.apiKeyInputLabel")), /* @__PURE__ */ import_react.default.createElement(
    TextInput,
    {
      value,
      onChange: setValue,
      onSubmit: (raw) => {
        const trimmed = raw.trim() || initialValue?.trim() || "";
        if (!isPlausibleKey(trimmed)) {
          onError(t("wizard.apiKeyInvalid"));
          setValue("");
          return;
        }
        setChecking(true);
        onError(null);
        void validateApiKey(trimmed).then((result) => {
          setChecking(false);
          if (!result.ok) {
            onError(
              result.reason === "rejected" ? t("wizard.apiKeyRejected") : t("wizard.apiKeyCheckFailed", { message: result.message ?? "unknown" })
            );
            setValue("");
            return;
          }
          onSubmit(trimmed);
        });
      },
      mask: "\u2022",
      placeholder: "sk-..."
    }
  )), checking ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:yellow" }, t("wizard.apiKeyChecking"))) : error ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:red" }, error)) : value ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.apiKeyPreview", { redacted: redactKey(value) }))) : null);
}
async function validateDeepSeekApiKey(apiKey, opts = {}) {
  const fetchImpl = opts.fetch ?? globalThis.fetch.bind(globalThis);
  let baseUrl = opts.baseUrl ?? loadBaseUrl() ?? "https://api.deepseek.com";
  while (baseUrl.endsWith("/")) baseUrl = baseUrl.slice(0, -1);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 1e4);
  try {
    const resp = await fetchImpl(`${baseUrl}/models`, {
      method: "GET",
      headers: { Authorization: `Bearer ${apiKey}` },
      signal: ctrl.signal
    });
    if (resp.ok) return { ok: true };
    if (resp.status === 401 || resp.status === 403) return { ok: false, reason: "rejected" };
    return { ok: false, reason: "failed", message: `HTTP ${resp.status}` };
  } catch (e) {
    return { ok: false, reason: "failed", message: e.message };
  } finally {
    clearTimeout(timer);
  }
}
function McpArgsStep({
  entry,
  error,
  onSubmit,
  onError
}) {
  const [value, setValue] = (0, import_react.useState)("");
  const [pendingCreate, setPendingCreate] = (0, import_react.useState)(null);
  use_input_default((input, key) => {
    if (!pendingCreate) return;
    const ch = input.toLowerCase();
    if (ch === "y" || key.return) {
      try {
        mkdirSync(pendingCreate, { recursive: true });
        const created = pendingCreate;
        setPendingCreate(null);
        setValue("");
        onError(null);
        onSubmit(created);
      } catch (e) {
        onError(
          t("wizard.mcpArgsDirCreateFailed", {
            path: pendingCreate,
            message: e.message
          })
        );
        setPendingCreate(null);
      }
    } else if (ch === "n" || key.escape) {
      setPendingCreate(null);
      onError(null);
    }
  });
  if (pendingCreate) {
    return /* @__PURE__ */ import_react.default.createElement(StepFrame, { title: t("wizard.mcpArgsTitle", { name: entry.name }), step: 2, total: 3 }, /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column" }, /* @__PURE__ */ import_react.default.createElement(Text, null, t("wizard.mcpArgsDirMissing", { path: pendingCreate })), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.mcpArgsDirCreateHint"))), error ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:red" }, error)) : null));
  }
  return /* @__PURE__ */ import_react.default.createElement(StepFrame, { title: t("wizard.mcpArgsTitle", { name: entry.name }), step: 2, total: 3 }, /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column" }, /* @__PURE__ */ import_react.default.createElement(Text, null, entry.summary), entry.note ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, entry.note)) : null, /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, null, t("wizard.mcpArgsRequiredParam")), /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, entry.userArgs)), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:cyan" }, entry.userArgs, " \u203A "), /* @__PURE__ */ import_react.default.createElement(
    TextInput,
    {
      value,
      onChange: setValue,
      onSubmit: (raw) => {
        const trimmed = raw.trim();
        if (!trimmed) {
          onError(t("wizard.mcpArgsEmpty", { name: entry.name }));
          return;
        }
        if (entry.name === "filesystem") {
          const check = checkFilesystemPath(trimmed);
          if (check.kind === "missing") {
            setPendingCreate(trimmed);
            return;
          }
          if (check.kind === "not-a-dir") {
            onError(t("wizard.mcpArgsNotADir", { path: trimmed }));
            return;
          }
        }
        onSubmit(trimmed);
        setValue("");
      },
      placeholder: placeholderFor(entry)
    }
  )), error ? /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1 }, /* @__PURE__ */ import_react.default.createElement(Text, { color: "ansi:red" }, error)) : null));
}
function checkFilesystemPath(p) {
  try {
    return { kind: statSync(p).isDirectory() ? "ok" : "not-a-dir" };
  } catch {
    return { kind: "missing" };
  }
}
function ReviewConfirm({ onConfirm }) {
  use_input_default((_i, key) => {
    if (key.return) onConfirm();
  });
  return null;
}
function ExitOnEnter({ onExit }) {
  use_input_default((_i, key) => {
    if (key.return) onExit();
  });
  return null;
}
function StepFrame({
  title,
  step,
  total,
  children
}) {
  return /* @__PURE__ */ import_react.default.createElement(Box_default, { flexDirection: "column", borderStyle: "round", borderColor: "ansi:cyan", paddingX: 1 }, /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, { dim: true }, t("wizard.stepCounter", { step, total })), /* @__PURE__ */ import_react.default.createElement(Text, { bold: true, color: "ansi:cyan" }, title)), /* @__PURE__ */ import_react.default.createElement(Box_default, { marginTop: 1, flexDirection: "column" }, children));
}
function SummaryLine({ label, value }) {
  return /* @__PURE__ */ import_react.default.createElement(Box_default, null, /* @__PURE__ */ import_react.default.createElement(Text, null, label.padEnd(12)), /* @__PURE__ */ import_react.default.createElement(Text, { bold: true }, value));
}
function mcpItems() {
  return MCP_CATALOG.map((entry) => {
    const hintParts = [entry.summary];
    if (entry.userArgs) hintParts.push(t("wizard.mcpUserArgsHint", { arg: entry.userArgs }));
    if (entry.note) hintParts.push(entry.note);
    return {
      value: entry.name,
      label: entry.name,
      hint: hintParts.join(" \xB7 ")
    };
  });
}
function placeholderFor(entry) {
  if (entry.name === "filesystem") return "e.g. /tmp/reasonix-sandbox";
  if (entry.name === "sqlite") return "e.g. ./notes.sqlite";
  return entry.userArgs ?? "";
}
function deriveInitialCatalog(existingSpecs) {
  const packageToName = new Map(MCP_CATALOG.map((e) => [e.package, e.name]));
  const out = [];
  for (const spec of existingSpecs) {
    for (const [pkg, name] of packageToName) {
      if (spec.includes(pkg)) {
        out.push(name);
        break;
      }
    }
  }
  return out;
}
function buildSpec(name, argsByName) {
  const entry = CATALOG_BY_NAME.get(name);
  if (!entry) return name;
  const userArg = entry.userArgs ? argsByName[name] : void 0;
  const tail = userArg ? ` ${quoteIfNeeded(userArg)}` : "";
  return `${entry.name}=npx -y ${entry.package}${tail}`;
}
function quoteIfNeeded(s) {
  return /\s|"/.test(s) ? `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"` : s;
}

// src/cli/commands/setup.tsx
async function setupCommand(opts = {}) {
  loadDotenv();
  const existingKey = loadApiKey();
  const existing = readConfig();
  const { waitUntilExit, unmount } = renderSync(
    /* @__PURE__ */ import_react2.default.createElement(
      Wizard,
      {
        existingApiKey: existingKey,
        initial: { mcp: existing.mcp, theme: existing.theme },
        forceApiKeyStep: opts.forceKeyStep,
        onComplete: () => void 0,
        onCancel: () => {
          unmount();
        }
      }
    ),
    { exitOnCtrlC: true, patchConsole: false }
  );
  await waitUntilExit();
}
export {
  setupCommand
};
//# sourceMappingURL=setup-HE3F6U2F.js.map