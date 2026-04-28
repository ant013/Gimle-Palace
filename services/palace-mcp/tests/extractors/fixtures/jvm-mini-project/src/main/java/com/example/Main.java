package com.example;

public class Main {
    public static void main(String[] args) {
        User user = new User("Alice", 30);
        Cache<String, User> cache = new Cache<>();
        cache.put(user.getName(), user);

        Inner inner = new Inner.Builder().value(42).build();
        System.out.println(user.getName() + " age=" + user.getAge() + " inner=" + inner.getValue());
    }
}
