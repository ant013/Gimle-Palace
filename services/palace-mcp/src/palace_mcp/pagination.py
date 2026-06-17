from __future__ import annotations

from typing import Any

PAGE_LIMIT_REASON = "page_limit"


def pagination_envelope(
    *,
    total: int,
    returned: int,
    offset: int = 0,
    truncated_reason: str | None = None,
) -> dict[str, Any]:
    safe_total = max(total, 0)
    safe_returned = max(returned, 0)
    safe_offset = max(offset, 0)
    has_more = safe_offset + safe_returned < safe_total
    reason = truncated_reason or (PAGE_LIMIT_REASON if has_more else None)
    payload: dict[str, Any] = {
        "total": safe_total,
        "returned": safe_returned,
        "offset": safe_offset,
        "has_more": has_more,
        "truncated": reason is not None,
    }
    if has_more and safe_returned > 0:
        payload["next_offset"] = safe_offset + safe_returned
    if reason is not None:
        payload["truncated_reason"] = reason
    return payload
