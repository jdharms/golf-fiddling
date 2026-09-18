// ROM setup: hash each chosen file with SubtleCrypto, compare it with the expected SHA-1,
// and keep verified bytes in the browser's ROM store (romstore.js, loaded first) so players
// choose their ROMs once. The download form on the seed page reads the same store.
//
// Each card's look is driven by its data-state (server/static/site.css):
//   checking     reading the store or hashing a file
//   empty        nothing stored; the file input is offered
//   error        the chosen file did not match; the file input is offered again
//   stored       a verified ROM is stored; only Forget is offered
//   unavailable  this browser cannot hash or store files
//
// Strings are embedded in #rom-strings; see romstore.js for t().
"use strict";

const t = makeT("rom-strings");

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
        setState(
          article,
          "error",
          t("rom.status.mismatch", { file: file.name, sha1: actual }),
        );
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
    for (const article of articles) {
      setState(article, "unavailable", t("rom.status.unavailable"));
    }
    return;
  }
  articles.forEach((article) => {
    setupRom(article).catch((error) =>
      setState(article, "error", t("rom.status.storage_failed", { error })),
    );
  });
});
