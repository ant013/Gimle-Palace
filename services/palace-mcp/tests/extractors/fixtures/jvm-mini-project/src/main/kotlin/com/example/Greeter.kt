package com.example

interface Greeting {
    val message: String
}

class Greeter(private val name: String) {
    fun greet(): Greeting = object : Greeting {
        override val message: String get() = "Hello, $name!"
    }

    fun greetAll(names: List<String>): List<Greeting> =
        names.map { Greeter(it).greet() }
}
