package com.example.good

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource

@Composable
fun LocalizedScreen() {
    // Properly localised via stringResource
    Text(stringResource(R.string.hello_world))
    Text(text = stringResource(R.string.sign_in))
    Text(text = stringResource(id = R.string.welcome))
}
