// The browser's ROM store and page strings, shared by the ROM setup page (rom.js) and the
// seed page's download form (download.js). Load this script before either.
//
// The store is database "golf-randomizer", object store "roms", one record per ROM keyed
// by its catalog id: {id, sha1, bytes}. It holds only files whose SHA-1 matched.
//
// Player-visible text comes from server/strings/, which each page embeds as JSON in a
// <script type="application/json"> element: key to text, or null while unwritten. A page
// script gets its t() from makeT(elementId), and calls it with keys written out literally
// so tests can check them against the catalog. The text may hold inline HTML, such as
// <code>, and t() returns HTML: values (file names, hashes, browser errors) are escaped
// before they are inserted.
"use strict";

const ROM_DB_NAME = "golf-randomizer";
const ROM_DB_VERSION = 1;
const ROM_STORE = "roms";

function openRomDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(ROM_DB_NAME, ROM_DB_VERSION);
    request.onupgradeneeded = () =>
      request.result.createObjectStore(ROM_STORE, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withRomStore(mode, action) {
  const db = await openRomDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(ROM_STORE, mode);
      const request = action(tx.objectStore(ROM_STORE));
      let result;
      request.onsuccess = () => {
        result = request.result;
      };
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

const getRom = (id) => withRomStore("readonly", (store) => store.get(id));
const putRom = (record) => withRomStore("readwrite", (store) => store.put(record));
const deleteRom = (id) => withRomStore("readwrite", (store) => store.delete(id));

async function sha1Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-1", buffer);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

const HTML_ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};
const escapeHtml = (value) =>
  String(value).replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);

// The t() for the strings a page embeds in the element with this id.
function makeT(elementId) {
  let strings;
  return function (key, values = {}) {
    strings ??= JSON.parse(document.getElementById(elementId).textContent);
    if (!(key in strings)) throw new Error(`no string ${key} on this page`);
    const text = strings[key];
    if (text === null) {
      const parts = [
        key,
        ...Object.entries(values).map(([name, value]) => `${name}=${value}`),
      ];
      return escapeHtml(`⟦${parts.join(" ")}⟧`);
    }
    return text.replace(/\{\{|\}\}|\{(\w+)\}/g, (match, name) => {
      if (match === "{{") return "{";
      if (match === "}}") return "}";
      if (!(name in values))
        throw new Error(`${key} uses {${name}}, which the script does not pass`);
      return escapeHtml(values[name]);
    });
  };
}
