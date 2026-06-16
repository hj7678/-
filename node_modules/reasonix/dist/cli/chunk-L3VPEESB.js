#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }

// src/code-query/grammar-map.ts
var EXT_TO_GRAMMAR = {
  ".ts": "typescript",
  ".mts": "typescript",
  ".cts": "typescript",
  ".tsx": "tsx",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".jsx": "javascript",
  ".py": "python",
  ".pyi": "python",
  ".go": "go",
  ".rs": "rust",
  ".java": "java"
};
function grammarForPath(filePath) {
  const lower = filePath.toLowerCase();
  for (const ext of Object.keys(EXT_TO_GRAMMAR)) {
    if (lower.endsWith(ext)) return EXT_TO_GRAMMAR[ext];
  }
  return null;
}

export {
  grammarForPath
};
//# sourceMappingURL=chunk-L3VPEESB.js.map