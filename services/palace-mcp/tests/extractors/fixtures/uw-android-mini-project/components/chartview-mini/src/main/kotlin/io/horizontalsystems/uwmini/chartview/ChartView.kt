package io.horizontalsystems.uwmini.chartview

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import io.horizontalsystems.uwmini.chartview.models.ChartPointF

/**
 * Synthesized in UW style (Phase 1.0 trial 2026-04-30).
 * Wraps vendored ChartViewType + ChartPointF + ChartDraw types in a Compose Canvas.
 * UW upstream `:components:chartview/ChartView.kt` is a `View` (extends android.view.View),
 * not a Compose function; this synthesized version is what a modern Compose chart would look like.
 */
@Composable
fun ChartView(
    values: List<Float>,
    type: ChartViewType = ChartViewType.Line,
    modifier: Modifier = Modifier,
    color: Color = Color.Cyan,
) {
    Canvas(modifier = modifier.fillMaxWidth().height(120.dp)) {
        if (values.isEmpty()) return@Canvas
        val minV = values.min()
        val maxV = values.max()
        val range = (maxV - minV).coerceAtLeast(0.0001f)

        val points: List<ChartPointF> = values.mapIndexed { idx, v ->
            val x = idx.toFloat() / (values.size - 1).coerceAtLeast(1) * size.width
            val y = size.height - ((v - minV) / range) * size.height
            ChartPointF(x, y)
        }

        val path = Path()
        path.moveTo(points.first().x, points.first().y)
        points.drop(1).forEach { path.lineTo(it.x, it.y) }

        when (type) {
            ChartViewType.Line -> drawPath(path, color, style = Stroke(width = 4f))
            ChartViewType.Bar -> {
                val barWidth = size.width / points.size
                points.forEach { p ->
                    drawRect(color, topLeft = Offset(p.x, p.y), size = androidx.compose.ui.geometry.Size(barWidth - 2, size.height - p.y))
                }
            }
        }
    }
}
