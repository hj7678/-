#!/usr/bin/env node
import { createRequire as __cr } from 'node:module'; if (typeof globalThis.require === 'undefined') { globalThis.require = __cr(import.meta.url); }
import {
  Query,
  getParser
} from "./chunk-FP7IOWBQ.js";
import {
  grammarForPath
} from "./chunk-L3VPEESB.js";
import "./chunk-TUK7OWJA.js";

// src/code-query/symbols.ts
var TS_QUERY = `
(function_declaration name: (identifier) @name) @function
(class_declaration name: (type_identifier) @name) @class
(interface_declaration name: (type_identifier) @name) @interface
(type_alias_declaration name: (type_identifier) @name) @type
(enum_declaration name: (identifier) @name) @enum
(method_definition name: (property_identifier) @name) @method
(public_field_definition name: (property_identifier) @name) @property
(variable_declarator name: (identifier) @name value: [(arrow_function) (function_expression)]) @function
(internal_module name: (identifier) @name) @namespace
`;
var JS_QUERY = `
(function_declaration name: (identifier) @name) @function
(class_declaration name: (identifier) @name) @class
(method_definition name: (property_identifier) @name) @method
(field_definition property: (property_identifier) @name) @property
(variable_declarator name: (identifier) @name value: [(arrow_function) (function_expression)]) @function
`;
var PYTHON_QUERY = `
(function_definition name: (identifier) @name) @function
(class_definition name: (identifier) @name) @class
`;
var GO_QUERY = `
(function_declaration name: (identifier) @name) @function
(method_declaration name: (field_identifier) @name) @method
(type_spec name: (type_identifier) @name type: (struct_type)) @class
(type_spec name: (type_identifier) @name type: (interface_type)) @interface
(type_spec name: (type_identifier) @name) @type
`;
var RUST_QUERY = `
(function_item name: (identifier) @name) @function
(struct_item name: (type_identifier) @name) @class
(enum_item name: (type_identifier) @name) @enum
(trait_item name: (type_identifier) @name) @interface
(type_item name: (type_identifier) @name) @type
(mod_item name: (identifier) @name) @namespace
(const_item name: (identifier) @name) @property
(static_item name: (identifier) @name) @property
`;
var JAVA_QUERY = `
(class_declaration name: (identifier) @name) @class
(interface_declaration name: (identifier) @name) @interface
(enum_declaration name: (identifier) @name) @enum
(method_declaration name: (identifier) @name) @method
(constructor_declaration name: (identifier) @name) @method
(field_declaration declarator: (variable_declarator name: (identifier) @name)) @property
`;
var QUERIES = {
  typescript: TS_QUERY,
  tsx: TS_QUERY,
  javascript: JS_QUERY,
  python: PYTHON_QUERY,
  go: GO_QUERY,
  rust: RUST_QUERY,
  java: JAVA_QUERY
};
var KIND_CAPTURE_NAMES = /* @__PURE__ */ new Set([
  "function",
  "class",
  "interface",
  "type",
  "enum",
  "method",
  "property",
  "namespace"
]);
var PARENT_CONTAINER_TYPES = /* @__PURE__ */ new Set([
  "class_declaration",
  "interface_declaration",
  "internal_module",
  "class_definition",
  "impl_item",
  "trait_item",
  "mod_item"
]);
var METHOD_PROMOTING_CONTAINER_TYPES = /* @__PURE__ */ new Set([
  "class_declaration",
  "class_definition",
  "interface_declaration",
  "impl_item",
  "trait_item"
]);
async function extractSymbols(filePath, source) {
  const grammar = grammarForPath(filePath);
  if (!grammar) return [];
  const parser = await getParser(grammar);
  try {
    const tree = parser.parse(source);
    if (!tree) return [];
    const language = parser.language;
    if (!language) return [];
    const query = new Query(language, QUERIES[grammar]);
    try {
      const matches = query.matches(tree.rootNode);
      return matchesToSymbols(matches);
    } finally {
      query.delete();
      tree.delete();
    }
  } finally {
    parser.delete();
  }
}
function matchesToSymbols(matches) {
  const out = [];
  for (const match of matches) {
    let nameNode = null;
    let containerNode = null;
    let kind = null;
    for (const cap of match.captures) {
      if (cap.name === "name") {
        nameNode = cap.node;
      } else if (KIND_CAPTURE_NAMES.has(cap.name)) {
        containerNode = cap.node;
        kind = cap.name;
      }
    }
    if (!nameNode || !containerNode || !kind) continue;
    const enclosing = findEnclosingContainer(containerNode);
    if (kind === "function" && enclosing && METHOD_PROMOTING_CONTAINER_TYPES.has(enclosing.type)) {
      kind = "method";
    }
    out.push({
      name: nameNode.text,
      kind,
      line: containerNode.startPosition.row + 1,
      column: containerNode.startPosition.column + 1,
      endLine: containerNode.endPosition.row + 1,
      endColumn: containerNode.endPosition.column + 1,
      parent: enclosing ? containerNameOf(enclosing) : void 0
    });
  }
  out.sort((a, b) => a.line - b.line || a.column - b.column);
  return out;
}
function findEnclosingContainer(node) {
  let current = node.parent;
  while (current) {
    if (PARENT_CONTAINER_TYPES.has(current.type)) return current;
    current = current.parent;
  }
  return null;
}
function containerNameOf(container) {
  if (container.type === "impl_item") {
    const typeField = container.childForFieldName("type");
    if (typeField) return typeField.text;
  }
  const nameField = container.childForFieldName("name");
  return nameField?.text;
}
export {
  extractSymbols
};
//# sourceMappingURL=symbols-UQ274IOB.js.map