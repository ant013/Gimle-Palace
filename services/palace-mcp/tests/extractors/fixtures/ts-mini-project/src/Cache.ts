export class Cache<K, V> {
  private store: Map<K, V>;

  constructor() {
    this.store = new Map<K, V>();
  }

  put(key: K, value: V): void {
    this.store.set(key, value);
  }

  get(key: K): V | undefined {
    return this.store.get(key);
  }
}
