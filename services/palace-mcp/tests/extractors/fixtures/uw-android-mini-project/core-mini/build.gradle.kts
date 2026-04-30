plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.ksp)
}

android {
    namespace = "io.horizontalsystems.uwmini.core"
    compileSdk = libs.versions.compileSdk.get().toInt()
    defaultConfig { minSdk = libs.versions.minSdk.get().toInt() }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    api(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)
    implementation(libs.kotlinx.coroutines.android)
}

dependencies {
    kotlinCompilerPluginClasspath(libs.sourcegraph.semanticdb.kotlinc)
}

val semanticdbTargetRoot = rootProject.layout.buildDirectory.dir("semanticdb-targetroot")
tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask<*>>().configureEach {
    compilerOptions.freeCompilerArgs.addAll(
        "-P=plugin:semanticdb-kotlinc:sourceroot=${rootProject.projectDir.absolutePath}",
        "-P=plugin:semanticdb-kotlinc:targetroot=${semanticdbTargetRoot.get().asFile.absolutePath}",
    )
}
