package com.example.mini

import androidx.compose.foundation.clickable
import androidx.compose.ui.Modifier

// a11y.missing_compose — Modifier.clickable without semantics
fun onClick() {
    Modifier.clickable { /* action */ }
}
