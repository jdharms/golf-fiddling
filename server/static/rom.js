// ROM setup: hash each chosen file with SubtleCrypto, compare it with the expected SHA-1,
// and keep verified bytes in IndexedDB so players choose their ROMs once.
//
// The store is database "golf-randomizer", object store "roms", one record per ROM keyed
// by its catalog id: {id, sha1, bytes}. The download form reads the same store.
//
// Each card's look is driven by its data-state (server/static/site.css):
//   checking     reading the store or hashing a file
//   empty        nothing stored; the file input is offered
//   error        the chosen file did not match; the file input is offered again
//   stored       a verified ROM is stored; only Forget is offered
//   unavailable  this browser cannot hash or store files
//
// Player-visible text comes from server/strings/, which the page embeds as JSON in
// #rom-strings: key to text, or null while unwritten. Keys are written out literally in
// t() calls so tests can check them against the catalog. The text may hold inline HTML,
// such as <code>, and t() returns HTML: values (file names, hashes, browser errors) are
// escaped before they are inserted.
"use strict";

const ROM_DB_NAME = "golf-randomizer";
const ROM_DB_VERSION = 1;
const ROM_STORE = "roms";

function openRomDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(ROM_DB_NAME, ROM_DB_VERSION);
    request.onupgradeneeded = () => request.result.createObjectStore(ROM_STORE, { keyPath: "id" });
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
      request.onsuccess = () => { result = request.result; };
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
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

let romStrings;

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);

function t(key, values = {}) {
  romStrings ??= JSON.parse(document.getElementById("rom-strings").textContent);
  if (!(key in romStrings)) throw new Error(`no string ${key} on this page`);
  const text = romStrings[key];
  if (text === null) {
    const parts = [key, ...Object.entries(values).map(([name, value]) => `${name}=${value}`)];
    return escapeHtml(`⟦${parts.join(" ")}⟧`);
  }
  return text.replace(/\{\{|\}\}|\{(\w+)\}/g, (match, name) => {
    if (match === "{{") return "{";
    if (match === "}}") return "}";
    if (!(name in values)) throw new Error(`${key} uses {${name}}, which the script does not pass`);
    return escapeHtml(values[name]);
  });
}

function setState(article, state, html) {
  article.dataset.state = state;
  article.querySelector(".rom-status").innerHTML = html;
}

function setupRom(article) {
  const id = article.dataset.romId;
  const expected = article.dataset.sha1.toLowerCase();
  const input = article.querySelector("input[type=file]");
  const forget = article.querySelector(".rom-forget");

  async function refresh() {
    const record = await getRom(id);
    if (record && record.sha1 === expected) {
      setState(article, "stored", t("rom.status.stored"));
    } else {
      setState(article, "empty", t("rom.status.empty"));
    }
  }

  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    setState(article, "checking", t("rom.status.checking"));
    try {
      const bytes = await file.arrayBuffer();
      const actual = await sha1Hex(bytes);
      if (actual !== expected) {
        setState(article, "error", t("rom.status.mismatch", { file: file.name, sha1: actual }));
        return;
      }
      await putRom({ id, sha1: actual, bytes });
      setState(article, "stored", t("rom.status.stored"));
      forget.focus();
    } catch (error) {
      setState(article, "error", t("rom.status.check_failed", { error }));
    } finally {
      input.value = "";
    }
  });

  forget.addEventListener("click", async () => {
    setState(article, "checking", t("rom.status.forgetting"));
    try {
      await deleteRom(id);
      await refresh();
      input.focus();
    } catch (error) {
      setState(article, "error", t("rom.status.forget_failed", { error }));
    }
  });

  input.disabled = false;
  return refresh();
}

document.addEventListener("DOMContentLoaded", () => {
  const articles = document.querySelectorAll("article.rom");
  if (!window.isSecureContext || !window.crypto?.subtle || !window.indexedDB) {
    document.getElementById("rom-unsupported").hidden = false;
    articles.forEach((article) => setState(article, "unavailable", t("rom.status.unavailable")));
    return;
  }
  articles.forEach((article) => {
    setupRom(article).catch((error) => setState(article, "error", t("rom.status.storage_failed", { error })));
  });
});
