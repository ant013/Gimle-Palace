package com.example

class Logger(private val tag: String) {
    fun info(msg: String) {
        println("[$tag] INFO: $msg")
    }

    fun warn(msg: String) {
        println("[$tag] WARN: $msg")
    }

    companion object {
        fun forClass(cls: Class<*>): Logger = Logger(cls.simpleName)
    }
}
