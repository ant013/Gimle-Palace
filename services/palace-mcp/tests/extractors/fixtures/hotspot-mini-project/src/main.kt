fun route(code: Int): String {
    return when (code) {
        200 -> "ok"
        404 -> "missing"
        500 -> "boom"
        else -> "other"
    }
}
