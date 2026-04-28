package com.example;

public class Inner {
    private int value;

    public Inner(int value) {
        this.value = value;
    }

    public static class Builder {
        private int value;

        public Builder value(int v) {
            this.value = v;
            return this;
        }

        public Inner build() {
            return new Inner(value);
        }
    }

    public int getValue() {
        return value;
    }
}
