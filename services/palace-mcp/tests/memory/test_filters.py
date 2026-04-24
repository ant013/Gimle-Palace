from palace_mcp.memory.filters import resolve_filters


def test_episode_known_keys_pass_through() -> None:
    where_clauses, params, unknown = resolve_filters(
        "Episode",
        {"kind": "heartbeat", "source": "extractor.heartbeat"},
    )
    assert "n.kind = $kind" in where_clauses
    assert "n.source = $source" in where_clauses
    assert params == {"kind": "heartbeat", "source": "extractor.heartbeat"}
    assert unknown == []


def test_episode_unknown_key_returned_separately() -> None:
    where_clauses, params, unknown = resolve_filters(
        "Episode", {"kind": "heartbeat", "bogus": "x"}
    )
    assert unknown == ["bogus"]
    assert "bogus" not in params


def test_symbol_filter_keys() -> None:
    where_clauses, params, unknown = resolve_filters(
        "Symbol", {"kind": "function", "name": "build_graphiti", "file_path": "src/x.py"}
    )
    assert "n.kind = $kind" in where_clauses
    assert "n.name = $name" in where_clauses
    assert "n.file_path = $file_path" in where_clauses
    assert unknown == []


def test_finding_severity_filter() -> None:
    _, params, unknown = resolve_filters("Finding", {"severity": "high", "foo": "bar"})
    assert "severity" in params
    assert unknown == ["foo"]


def test_model_has_no_filters_all_unknown() -> None:
    _, params, unknown = resolve_filters("Model", {"anything": "x"})
    assert params == {}
    assert unknown == ["anything"]
