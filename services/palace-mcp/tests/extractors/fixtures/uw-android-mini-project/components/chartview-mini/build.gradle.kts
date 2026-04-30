plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "io.horizontalsystems.uwmini.chartview"
    compileSdk = libs.versions.compileSdk.get().toInt()
    defaultConfig { minSdk = libs.versions.minSdk.get().toInt() }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
}

dependencies {
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.compose.runtime)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.foundation)
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
