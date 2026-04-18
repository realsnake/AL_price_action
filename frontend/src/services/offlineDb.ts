import type { Bar, Account, Position } from "../types";

const DB_NAME = "stock-trader-offline";
const DB_VERSION = 2;
const META_STORE = "metadata";

let dbInstance: IDBDatabase | null = null;

interface SnapshotMeta {
  id: string;
  cached_at: string;
}

function openDb(): Promise<IDBDatabase> {
  if (dbInstance) return Promise.resolve(dbInstance);

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);

    request.onsuccess = () => {
      dbInstance = request.result;
      resolve(request.result);
    };

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      if (!db.objectStoreNames.contains("bars")) {
        db.createObjectStore("bars", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("account")) {
        db.createObjectStore("account", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("positions")) {
        db.createObjectStore("positions", { keyPath: "symbol" });
      }
      if (!db.objectStoreNames.contains(META_STORE)) {
        db.createObjectStore(META_STORE, { keyPath: "id" });
      }
    };
  });
}

function barsId(symbol: string, timeframe: string): string {
  return `${symbol}_${timeframe}`;
}

function barsMetaId(symbol: string, timeframe: string): string {
  return `bars:${symbol}_${timeframe}`;
}

function accountMetaId(): string {
  return "account:current";
}

function positionsMetaId(): string {
  return "positions:all";
}

export interface CachedSnapshot<T> {
  data: T;
  cachedAt: string | null;
}

// --- Bars ---

export async function saveBars(
  symbol: string,
  timeframe: string,
  bars: Bar[],
): Promise<void> {
  const db = await openDb();
  const cachedAt = new Date().toISOString();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(["bars", META_STORE], "readwrite");
    const store = tx.objectStore("bars");
    store.put({
      id: barsId(symbol, timeframe),
      symbol,
      timeframe,
      bars,
    });
    tx.objectStore(META_STORE).put({
      id: barsMetaId(symbol, timeframe),
      cached_at: cachedAt,
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getBarsSnapshot(
  symbol: string,
  timeframe: string,
): Promise<CachedSnapshot<Bar[]> | null> {
  const db = await openDb();
  const tx = db.transaction(["bars", META_STORE], "readonly");
  return new Promise((resolve, reject) => {
    const dataRequest = tx.objectStore("bars").get(barsId(symbol, timeframe));
    const metaRequest = tx.objectStore(META_STORE).get(
      barsMetaId(symbol, timeframe),
    ) as IDBRequest<SnapshotMeta | undefined>;

    tx.oncomplete = () => {
      const result = dataRequest.result;
      if (!result) {
        resolve(null);
        return;
      }
      resolve({
        data: result.bars ?? [],
        cachedAt: metaRequest.result?.cached_at ?? null,
      });
    };
    tx.onerror = () => reject(tx.error);
  });
}

export async function getBars(
  symbol: string,
  timeframe: string,
): Promise<Bar[] | null> {
  const snapshot = await getBarsSnapshot(symbol, timeframe);
  return snapshot?.data ?? null;
}

// --- Account ---

export async function saveAccount(account: Account): Promise<void> {
  const db = await openDb();
  const cachedAt = new Date().toISOString();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(["account", META_STORE], "readwrite");
    const store = tx.objectStore("account");
    store.put({ id: "current", ...account });
    tx.objectStore(META_STORE).put({
      id: accountMetaId(),
      cached_at: cachedAt,
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAccountSnapshot(): Promise<CachedSnapshot<Account> | null> {
  const db = await openDb();
  const tx = db.transaction(["account", META_STORE], "readonly");
  return new Promise((resolve, reject) => {
    const accountRequest = tx.objectStore("account").get("current");
    const metaRequest = tx.objectStore(META_STORE).get(
      accountMetaId(),
    ) as IDBRequest<SnapshotMeta | undefined>;

    tx.oncomplete = () => {
      const result = accountRequest.result;
      if (!result) {
        resolve(null);
        return;
      }
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { id, ...account } = result;
      resolve({
        data: account as Account,
        cachedAt: metaRequest.result?.cached_at ?? null,
      });
    };
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAccount(): Promise<Account | null> {
  const snapshot = await getAccountSnapshot();
  return snapshot?.data ?? null;
}

// --- Positions ---

export async function savePositions(positions: Position[]): Promise<void> {
  const db = await openDb();
  const cachedAt = new Date().toISOString();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(["positions", META_STORE], "readwrite");
    const store = tx.objectStore("positions");
    store.clear();
    for (const pos of positions) {
      store.put(pos);
    }
    tx.objectStore(META_STORE).put({
      id: positionsMetaId(),
      cached_at: cachedAt,
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getPositionsSnapshot(): Promise<CachedSnapshot<Position[]> | null> {
  const db = await openDb();
  const tx = db.transaction(["positions", META_STORE], "readonly");
  return new Promise((resolve, reject) => {
    const positionsRequest = tx.objectStore("positions").getAll();
    const metaRequest = tx.objectStore(META_STORE).get(
      positionsMetaId(),
    ) as IDBRequest<SnapshotMeta | undefined>;

    tx.oncomplete = () => {
      resolve({
        data: positionsRequest.result,
        cachedAt: metaRequest.result?.cached_at ?? null,
      });
    };
    tx.onerror = () => reject(tx.error);
  });
}

export async function getPositions(): Promise<Position[]> {
  const snapshot = await getPositionsSnapshot();
  return snapshot?.data ?? [];
}
