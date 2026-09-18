// The seed page's download form: finish the seed on the server, patch the player's stored
// ROM with the IPS that comes back, and hand the result to the browser as a download.
//
// The article carries what the script needs as data, so no name or URL is assembled here:
//   data-required-roms  space-separated catalog ids of the ROMs this seed is built from
//   data-filename       the name the patched ROM downloads as
// and #download-roms maps each id to {title, sha1}. The form posts to its action; the
// script adds a rom_<id> field holding each stored ROM's SHA-1, which the server checks
// against the seed's required ROMs. The patched file is always the US ROM, nes_open_us.
//
// The article's look is driven by its data-state (server/static/site.css):
//   checking     reading the ROM store
//   missing      a required ROM is not stored; the link to ROM setup shows
//   ready        every required ROM is stored; the form can be submitted
//   building     waiting for the server, or patching
//   done         the patched ROM was handed to the browser
//   error        the server refused, or patching failed; the form can be submitted again
//   unavailable  this browser has no ROM store
//
// Strings are embedded in #download-strings; see romstore.js for t().
"use strict";

const t = makeT("download-strings");

const BASE_ROM = "nes_open_us";

function setState(article, state, html) {
  article.dataset.state = state;
  article.querySelector(".download-status").innerHTML = html;
  const button = article.querySelector("button[type=submit]");
  button.disabled = !["ready", "done", "error"].includes(state);
  if (state === "building") {
    button.setAttribute("aria-busy", "true");
  } else {
    button.removeAttribute("aria-busy");
  }
}

// -- IPS ------------------------------------------------------------------------------------

// Apply an IPS patch to a copy of base. Mirrors golf/core/ips.py: records of a 3-byte
// offset and a 2-byte size then the bytes, or a zero size then a 2-byte run length and the
// value; "EOF"; then an optional 3-byte truncation length.
function applyIps(base, patch) {
  const header = [0x50, 0x41, 0x54, 0x43, 0x48]; // PATCH
  if (patch.length < header.length || header.some((byte, i) => patch[i] !== byte)) {
    throw new Error("not an IPS patch: missing PATCH header");
  }
  let out = new Uint8Array(base);
  const grow = (length) => {
    if (length > out.length) {
      const bigger = new Uint8Array(length);
      bigger.set(out);
      out = bigger;
    }
  };
  const read = (pos, width) => {
    if (pos + width > patch.length) throw new Error("truncated IPS patch");
    let value = 0;
    for (let i = 0; i < width; i++) value = value * 256 + patch[pos + i];
    return value;
  };
  let pos = header.length;
  for (;;) {
    if (pos + 3 > patch.length) throw new Error("truncated IPS patch: no EOF marker");
    if (patch[pos] === 0x45 && patch[pos + 1] === 0x4f && patch[pos + 2] === 0x46) {
      pos += 3;
      break;
    }
    const offset = read(pos, 3);
    const size = read(pos + 3, 2);
    pos += 5;
    if (size) {
      if (pos + size > patch.length) throw new Error("truncated IPS record");
      grow(offset + size);
      out.set(patch.subarray(pos, pos + size), offset);
      pos += size;
    } else {
      const length = read(pos, 2);
      const value = read(pos + 2, 1);
      pos += 3;
      grow(offset + length);
      out.fill(value, offset, offset + length);
    }
  }
  const trailer = patch.length - pos;
  if (trailer === 3) {
    out = out.slice(0, Math.min(read(pos, 3), out.length));
  } else if (trailer) {
    throw new Error(`${trailer} unexpected bytes after EOF marker`);
  }
  return out;
}

// -- The form -------------------------------------------------------------------------------

// The stored ROMs among ids: id -> record, for those whose hash is the expected one.
async function storedRoms(ids, roms) {
  const found = {};
  for (const id of ids) {
    const record = await getRom(id);
    if (record && record.sha1 === roms[id].sha1) found[id] = record;
  }
  return found;
}

function missingTitles(ids, roms, stored) {
  return ids
    .filter((id) => !(id in stored))
    .map((id) => roms[id].title)
    .join(", ");
}

// The notice for a refusal the server answered with {error, values}.
function refusal(body, status) {
  const reason = body?.error;
  const values = body?.values || {};
  if (reason === "invalid_name")
    return t("seed.download.status.refused.invalid_name", {
      chars: values.chars ?? "",
    });
  if (reason === "invalid")
    return t("seed.download.status.refused.invalid", { field: values.field ?? "" });
  if (reason === "clubs_banned")
    return t("seed.download.status.refused.clubs_banned", {
      clubs: values.clubs ?? "",
    });
  if (reason === "clubs_over_max") {
    return t("seed.download.status.refused.clubs_over_max", {
      count: values.count ?? "",
      max: values.max ?? "",
    });
  }
  if (reason === "roms_missing")
    return t("seed.download.status.refused.roms_missing", { roms: values.roms ?? "" });
  if (reason === "unavailable") return t("seed.download.status.refused.unavailable");
  return t("seed.download.status.failed", { status });
}

function download(bytes, filename) {
  const url = URL.createObjectURL(
    new Blob([bytes], { type: "application/octet-stream" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function setupDownload(article) {
  const form = article.querySelector("form");
  const ids = article.dataset.requiredRoms.split(/\s+/).filter(Boolean);
  const roms = JSON.parse(document.getElementById("download-roms").textContent);
  const filename = article.dataset.filename;

  async function refresh() {
    const stored = await storedRoms(ids, roms);
    const missing = missingTitles(ids, roms, stored);
    if (missing) {
      setState(
        article,
        "missing",
        t("seed.download.status.missing", { roms: missing }),
      );
    } else {
      setState(article, "ready", t("seed.download.status.ready"));
    }
    return stored;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    let stored;
    try {
      stored = await refresh();
    } catch (error) {
      setState(article, "error", t("seed.download.status.storage_failed", { error }));
      return;
    }
    if (article.dataset.state === "missing") return;

    setState(article, "building", t("seed.download.status.building"));
    const data = new FormData(form);
    for (const [id, record] of Object.entries(stored))
      data.append(`rom_${id}`, record.sha1);

    let response;
    try {
      response = await fetch(form.action, { method: "POST", body: data });
    } catch (error) {
      setState(article, "error", t("seed.download.status.failed", { status: error }));
      return;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      setState(article, "error", refusal(body, response.status));
      return;
    }

    try {
      const patch = new Uint8Array(await response.arrayBuffer());
      const rom = applyIps(new Uint8Array(stored[BASE_ROM].bytes), patch);
      download(rom, filename);
      setState(article, "done", t("seed.download.status.done", { file: filename }));
    } catch (error) {
      setState(article, "error", t("seed.download.status.patch_failed", { error }));
    }
  });

  return refresh();
}

document.addEventListener("DOMContentLoaded", () => {
  const article = document.querySelector("article.download");
  if (!article) return;
  if (!window.indexedDB) {
    setState(article, "unavailable", t("seed.download.status.unavailable"));
    return;
  }
  setState(article, "checking", t("seed.download.status.checking"));
  setupDownload(article).catch((error) => {
    setState(article, "error", t("seed.download.status.storage_failed", { error }));
  });
});
