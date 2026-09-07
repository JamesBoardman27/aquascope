// A study lives in the browser between visits: the workspace without its
// bytes, the PNG figures as blobs, and the site it was made at, in IndexedDB,
// saved after every reply and kept to the last five. Nothing leaves the
// machine. Every call here is wrapped: no IndexedDB (a private window, a
// browser set to block site data, a quota), and the study is simply not
// saved; the page never shows an error for it.

const DB_NAME = "aquascope-study";
const STORE = "studies";
export const KEEP = 5;

let opening = null;

function idb() {
  try {
    return globalThis.indexedDB || null;
  } catch {
    return null;
  }
}

function open() {
  if (opening) return opening;
  opening = new Promise((resolve) => {
    const factory = idb();
    if (!factory) { resolve(null); return; }
    let req;
    try {
      req = factory.open(DB_NAME, 1);
    } catch {
      resolve(null);
      return;
    }
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("at", "at");
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
    req.onblocked = () => resolve(null);
  });
  opening.then((db) => { if (!db) opening = null; });
  return opening;
}

function done(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("storage error"));
  });
}

function settle(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error || new Error("storage error"));
    tx.onabort = () => reject(tx.error || new Error("storage aborted"));
  });
}

async function all() {
  const db = await open();
  if (!db) return [];
  try {
    const rows = await done(db.transaction(STORE, "readonly").objectStore(STORE).getAll());
    return (rows || []).filter((r) => r && r.id).sort((a, b) => (b.at || 0) - (a.at || 0));
  } catch (err) {
    console.info("study store unreadable:", err && err.message);
    return [];
  }
}

/**
 * Save one study: { id, at, site: {key, lat, lon, text}, ws (without bytes),
 * figures: {id: {blob, caption, step}}, lines }. Keeps the last KEEP by `at`.
 * Resolves true when written, false when it could not be.
 */
export async function saveStudy(rec) {
  if (!rec || !rec.id) return false;
  const db = await open();
  if (!db) return false;
  try {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    store.put({ ...rec, at: rec.at || Date.now() });
    await settle(tx);
  } catch (err) {
    console.info("study not saved:", err && err.message);
    return false;
  }
  try {
    const rows = await all();
    for (const old of rows.slice(KEEP)) {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(old.id);
      await settle(tx);
    }
  } catch { /* the newest is saved; pruning can wait */ }
  return true;
}

/** The studies saved here, newest first, without their figures' bytes: {id, at, site, status}. */
export async function listStudies() {
  const rows = await all();
  return rows.map((r) => ({ id: r.id, at: r.at, site: r.site, status: r.ws ? r.ws.status : null }));
}

/** The most recent study at a site (by its key), or anywhere when no key is given; null when none. */
export async function latestStudy(siteKey = null) {
  const rows = await all();
  const hit = rows.find((r) => !siteKey || (r.site && r.site.key === siteKey));
  return hit ? { id: hit.id, at: hit.at, site: hit.site, status: hit.ws ? hit.ws.status : null } : null;
}

/** One saved study in full, or null. */
export async function loadStudy(id) {
  const db = await open();
  if (!db || !id) return null;
  try {
    const rec = await done(db.transaction(STORE, "readonly").objectStore(STORE).get(id));
    return rec || null;
  } catch (err) {
    console.info("study not loaded:", err && err.message);
    return null;
  }
}

export async function forgetStudy(id) {
  const db = await open();
  if (!db || !id) return false;
  try {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    await settle(tx);
    return true;
  } catch {
    return false;
  }
}

// "2 h ago", "yesterday", "on 3 Sep": when a saved study was last touched, for the chip that offers it.
export function agoWords(at, now = Date.now()) {
  const s = Math.max(0, Math.round((now - Number(at || 0)) / 1000));
  if (s < 90) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  if (d === 1) return "yesterday";
  if (d < 7) return `${d} days ago`;
  try {
    return `on ${new Date(Number(at)).toLocaleDateString(undefined, { day: "numeric", month: "short" })}`;
  } catch {
    return `${d} days ago`;
  }
}
