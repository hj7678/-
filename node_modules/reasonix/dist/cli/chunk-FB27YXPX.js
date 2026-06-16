#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  sanitizeName,
  sessionsDir
} from "./chunk-P5SUHDUQ.js";

// src/adapters/event-sink-jsonl.ts
import { chmodSync, createWriteStream, mkdirSync } from "fs";
import { dirname, join } from "path";
function eventLogPath(sessionName) {
  return join(sessionsDir(), `${sanitizeName(sessionName)}.events.jsonl`);
}
var JsonlEventSink = class {
  constructor(stream) {
    this.stream = stream;
  }
  stream;
  buffered = 0;
  append(ev) {
    if (ev.type === "model.delta") return;
    this.stream.write(`${JSON.stringify(ev)}
`);
    this.buffered++;
  }
  flush() {
    return new Promise((resolve) => {
      if (this.buffered === 0) return resolve();
      this.stream.uncork();
      this.buffered = 0;
      resolve();
    });
  }
  close() {
    return new Promise((resolve) => {
      this.stream.end(() => resolve());
    });
  }
};
function openEventSink(path) {
  mkdirSync(dirname(path), { recursive: true });
  const stream = createWriteStream(path, { flags: "a" });
  try {
    chmodSync(path, 384);
  } catch {
  }
  return new JsonlEventSink(stream);
}

export {
  eventLogPath,
  openEventSink
};
//# sourceMappingURL=chunk-FB27YXPX.js.map