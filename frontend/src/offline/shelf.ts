/**
 * Where kept answers are stored: IndexedDB, which holds far more than localStorage
 * and is read without holding up the page. One record per person (keep.ts's
 * `recordKey`). Where IndexedDB is missing or refuses (a private window), nothing
 * is kept and the app works online as ever.
 */
export type Shelf = {
  get<T>(key: string): Promise<T | undefined>;
  put(key: string, value: unknown): Promise<void>;
  remove(key: string): Promise<void>;
};

const DB = "horatio-offline";
const STORE = "kept";

let opening: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  opening ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  }).catch((error: unknown) => {
    opening = null;
    throw error;
  });
  return opening;
}

async function run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise<T>((resolve, reject) => {
    const request = work(db.transaction(STORE, mode).objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export const indexedShelf: Shelf = {
  async get<T>(key: string) {
    if (typeof indexedDB === "undefined") return undefined;
    try {
      return (await run("readonly", (s) => s.get(key))) as T | undefined;
    } catch {
      return undefined;
    }
  },
  async put(key, value) {
    if (typeof indexedDB === "undefined") return;
    try {
      await run("readwrite", (s) => s.put(value, key));
    } catch {
      // Full or refused: what is on screen still works; it just isn't kept.
    }
  },
  async remove(key) {
    if (typeof indexedDB === "undefined") return;
    try {
      await run("readwrite", (s) => s.delete(key));
    } catch {
      // Nothing there to remove.
    }
  },
};

/** A shelf in memory, for tests. */
export function memoryShelf(): Shelf & { items: Map<string, unknown> } {
  const items = new Map<string, unknown>();
  return {
    items,
    get: async <T,>(key: string) => structuredClone(items.get(key)) as T | undefined,
    put: async (key, value) => void items.set(key, structuredClone(value)),
    remove: async (key) => void items.delete(key),
  };
}
