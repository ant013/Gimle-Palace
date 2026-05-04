plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

dependencies {
    implementation(libs.androidx.appcompat)
    testImplementation(libs.retrofit2)
}
