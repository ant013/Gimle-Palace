package io.horizontalsystems.uwmini.icons

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathNode
import androidx.compose.ui.unit.dp

/**
 * Synthesized in UW style (Phase 1.0 trial 2026-04-30).
 * UW upstream :components:icons is XML-resources-only; no Kotlin Compose icons object.
 * This file represents what a Compose-icons module SHOULD look like, following
 * androidx.compose.material.icons.Icons conventions (PathNode-based ImageVectors).
 */
object WalletIcons {
    val Send: ImageVector = simpleIcon("Send", listOf(0f to 0f, 24f to 12f, 0f to 24f))
    val Receive: ImageVector = simpleIcon("Receive", listOf(24f to 0f, 0f to 12f, 24f to 24f))
    val Swap: ImageVector = simpleIcon("Swap", listOf(2f to 8f, 22f to 8f, 2f to 16f, 22f to 16f))
    val Wallet: ImageVector = simpleIcon("Wallet", listOf(2f to 4f, 22f to 4f, 22f to 20f, 2f to 20f))

    private fun simpleIcon(name: String, points: List<Pair<Float, Float>>): ImageVector {
        val nodes = mutableListOf<PathNode>()
        if (points.isNotEmpty()) {
            nodes.add(PathNode.MoveTo(points[0].first, points[0].second))
            points.drop(1).forEach { (x, y) -> nodes.add(PathNode.LineTo(x, y)) }
            nodes.add(PathNode.Close)
        }
        return ImageVector.Builder(
            name = name,
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).addPath(
            pathData = nodes,
            pathFillType = PathFillType.NonZero,
            fill = SolidColor(Color.Black),
        ).build()
    }
}
