package com.example.good

import androidx.compose.foundation.clickable
import androidx.compose.foundation.semantics.contentDescription
import androidx.compose.foundation.semantics.semantics
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun AccessibleModifier() {
    // Has semantics before clickable — should NOT trigger rule
    Modifier.semantics { contentDescription = "Send button" }.clickable { }
}
