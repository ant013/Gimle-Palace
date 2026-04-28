plugins {
    kotlin("jvm") version "1.9.23"
    java
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

kotlin {
    jvmToolchain(17)
}
