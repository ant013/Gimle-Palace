package com.example.bad

import androidx.compose.foundation.clickable
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun MissingSemantics() {
    // Clickable without semantics — TalkBack can't describe this
    Modifier.clickable { /* action */ }
    Modifier.clickable(onClick = { /* action */ })
}
