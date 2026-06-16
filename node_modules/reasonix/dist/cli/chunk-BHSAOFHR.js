#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  require_react
} from "./chunk-U25OJR4Y.js";
import {
  CARD,
  DEFAULT_THEME_NAME,
  FG,
  MESSAGE_BG,
  SURFACE,
  THEMES,
  TONE,
  TONE_ACTIVE,
  resolveThemeName,
  setActiveTheme
} from "./chunk-GCNBIWK7.js";
import {
  __toESM
} from "./chunk-TUK7OWJA.js";

// src/cli/ui/theme/context.tsx
var import_react = __toESM(require_react(), 1);
var ThemeContext = import_react.default.createContext(THEMES[DEFAULT_THEME_NAME]);
function ThemeProvider({
  children,
  name
}) {
  const theme = THEMES[resolveThemeName(name)];
  const restoreActiveTheme = setActiveTheme(theme);
  import_react.default.useLayoutEffect(() => restoreActiveTheme, [restoreActiveTheme]);
  return /* @__PURE__ */ import_react.default.createElement(ThemeContext.Provider, { value: theme }, children);
}
function useThemeTokens() {
  return import_react.default.useContext(ThemeContext);
}
function useTheme() {
  return useThemeTokens();
}

// src/cli/ui/theme.ts
var import_react2 = __toESM(require_react(), 1);
function gradientFromTheme(theme) {
  return [
    theme.tone.ok,
    theme.tone.brand,
    theme.tone.info,
    theme.toneActive.brand,
    theme.toneActive.violet,
    theme.tone.accent,
    theme.toneActive.accent,
    theme.tone.err
  ];
}
function colorFromTheme(theme) {
  return {
    primary: theme.tone.brand,
    accent: theme.tone.accent,
    brand: theme.tone.ok,
    user: theme.tone.brand,
    assistant: theme.tone.ok,
    tool: theme.tone.warn,
    toolErr: theme.tone.err,
    info: theme.fg.sub,
    warn: theme.tone.warn,
    err: theme.tone.err,
    ok: theme.tone.ok
  };
}
function surfaceFromTheme(theme) {
  return {
    canvas: theme.surface.bg,
    shell: theme.surface.bgInput,
    card: theme.surface.bgElev,
    elev: theme.surface.bgElev,
    sel: theme.surface.bgInput,
    line: theme.fg.faint,
    lineSoft: theme.fg.meta
  };
}
function fgFromTheme(theme) {
  return {
    strong: theme.fg.strong,
    default: theme.fg.body,
    dim: theme.fg.sub,
    faint: theme.fg.meta,
    ghost: theme.fg.faint
  };
}
function proxyThemeValue(build) {
  const target = build();
  return new Proxy(target, {
    get(_target, prop) {
      return build()[prop];
    },
    getOwnPropertyDescriptor(_target, prop) {
      return Reflect.getOwnPropertyDescriptor(build(), prop);
    },
    has(_target, prop) {
      return prop in build();
    },
    ownKeys() {
      return Reflect.ownKeys(build());
    }
  });
}
function currentTheme() {
  return {
    fg: FG,
    tone: TONE,
    toneActive: TONE_ACTIVE,
    surface: SURFACE,
    messageBg: MESSAGE_BG,
    card: CARD
  };
}
function useColor() {
  const theme = useThemeTokens();
  return import_react2.default.useMemo(() => colorFromTheme(theme), [theme]);
}
var GRADIENT = proxyThemeValue(() => gradientFromTheme(currentTheme()));
var COLOR = proxyThemeValue(() => colorFromTheme(currentTheme()));
var GLYPH = {
  brand: "\u25CF",
  user: "\u25CF",
  assistant: "\u25CF",
  toolOk: "\u2713",
  toolErr: "\u2717",
  warn: "\u26A0",
  err: "\u2717",
  arrow: "\u25B8",
  bullet: "\xB7",
  bar: "\u2502",
  thinBar: "\u2502",
  block: "\u2588",
  shade1: "\u2591",
  shade2: "\u2592",
  shade3: "\u2593",
  done: "\u2713",
  cur: "\u25B8",
  pending: "\u25CB",
  fail: "\u2717",
  running: "\u25CF",
  branch: "\u251C",
  branchEnd: "\u2514",
  branchStub: "\u2502",
  rule: "\u2500",
  spinFrames: ["\u280B", "\u2819", "\u2839", "\u2838", "\u283C", "\u2834", "\u2826", "\u2827"]
};
var SURFACE2 = proxyThemeValue(() => surfaceFromTheme(currentTheme()));
var FG2 = proxyThemeValue(() => fgFromTheme(currentTheme()));

export {
  ThemeProvider,
  useThemeTokens,
  useTheme,
  useColor,
  GRADIENT,
  COLOR,
  GLYPH
};
//# sourceMappingURL=chunk-BHSAOFHR.js.map