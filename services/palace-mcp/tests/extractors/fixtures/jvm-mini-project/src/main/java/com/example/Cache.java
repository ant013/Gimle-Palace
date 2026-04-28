package com.example;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class Cache<K, V> {
    private final Map<K, V> store = new HashMap<>();

    public void put(K key, V value) {
        store.put(key, value);
    }

    public Optional<V> get(K key) {
        return Optional.ofNullable(store.get(key));
    }

    public boolean contains(K key) {
        return store.containsKey(key);
    }

    public void evict(K key) {
        store.remove(key);
    }
}
