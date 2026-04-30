package io.horizontalsystems.uwmini.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.horizontalsystems.uwmini.chartview.ChartView
import io.horizontalsystems.uwmini.icons.WalletIcons

@Composable
fun MainScreen(viewModel: MainViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.uiState.collectAsState()
    Column(modifier = modifier.padding(16.dp)) {
        // Reference WalletIcons from :components:icons-mini (cross-module USE)
        val sendIconName = WalletIcons.Send.name
        Text("Icon ready: $sendIconName")
        when (val s = state) {
            is UiState.Loading -> Text("Loading wallets...")
            is UiState.Success -> {
                Text("Wallets: ${s.wallets.size}")
                // Reference ChartView from :components:chartview-mini (cross-module USE)
                ChartView(values = s.wallets.map { it.balance.toFloat() })
            }
            is UiState.Error -> Text("Error: ${s.message}")
        }
    }
}
