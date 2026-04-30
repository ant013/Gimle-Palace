// VENDORED VERBATIM from horizontalsystems/unstoppable-wallet-android@c0489d5a3
// Original: components/chartview/src/main/java/io/horizontalsystems/chartview/ChartDraw.kt
package io.horizontalsystems.uwmini.chartview

import android.graphics.Canvas

interface ChartDraw {
    var isVisible: Boolean
    fun draw(canvas: Canvas)
}
