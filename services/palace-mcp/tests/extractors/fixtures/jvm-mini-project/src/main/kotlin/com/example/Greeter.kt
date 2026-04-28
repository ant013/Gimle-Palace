package com.example

interface Greeting {
    val message: String
}

class Greeter(private val name: String) {
    fun greet(greeting: String = "Hello"): Greeting = object : Greeting {
        override val message: String get() = "$greeting, $name!"
    }

    fun greetAll(names: List<String>): List<Greeting> =
        names.map { Greeter(it).greet() }

    suspend fun fetchGreeting(): Greeting = greet()
}

fun String.toGreeting(): Greeting = object : Greeting {
    override val message: String get() = this@toGreeting
}
