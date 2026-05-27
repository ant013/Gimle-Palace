"""Ranking contract tests for palace.code.semantic_search (GIM-919).

Tests the deterministic ranking formula defined in find_semantic.py:

    final_score = W_VECTOR  * vector_score
                + W_SCOPE   * scope_score(source_scope)
                + W_KIND    * kind_score(symbol_kind)
                + W_LEXICAL * lexical_score(query, qualified_name)
                - penalty(symbol_kind, qualified_name)

Tie-breakers: final_score DESC → scope_priority ASC → kind_priority ASC
              → project ASC → qualified_name ASC.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from palace_mcp.code.find_semantic import (
    _ACCESSOR_PENALTY,
    _W_KIND,
    _W_LEXICAL,
    _W_SCOPE,
    _W_VECTOR,
    _accessor_penalty,
    _apply_ranking,
    _compute_score_components,
    _lexical_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    *,
    qualified_name: str,
    vector_score: float,
    source_scope: str = "project",
    kind: str = "function",
    project: str = "my-app",
) -> dict[str, Any]:
    """Build a raw hit dict with the vector score as the initial 'score'."""
    return {
        "qualified_name": qualified_name,
        "score": vector_score,
        "source_scope": source_scope,
        "kind": kind,
        "project": project,
    }


def _rank(hits: list[dict[str, Any]], *, query: str = "unrelated-query-xyz") -> list[dict[str, Any]]:
    """Apply ranking formula and sort.  Uses a neutral query by default."""
    return _apply_ranking(query, [dict(h) for h in hits])


# ---------------------------------------------------------------------------
# _lexical_score
# ---------------------------------------------------------------------------


class TestLexicalScore:
    def test_exact_word_match(self) -> None:
        assert _lexical_score("verify", "Crypto.verify") == 1.0

    def test_case_insensitive(self) -> None:
        assert _lexical_score("Verify", "crypto.verify") == 1.0

    def test_substring_match(self) -> None:
        assert _lexical_score("wallet", "WalletService.refresh") == 1.0

    def test_no_match(self) -> None:
        assert _lexical_score("parse", "Crypto.verify") == 0.0

    def test_short_words_ignored(self) -> None:
        # Words shorter than 3 characters are not matched (noise avoidance)
        assert _lexical_score("go", "Crypto.go") == 0.0

    def test_multi_word_query_first_match_wins(self) -> None:
        assert _lexical_score("wallet balance", "WalletService.refresh") == 1.0

    def test_empty_qualified_name(self) -> None:
        assert _lexical_score("wallet", "") == 0.0


# ---------------------------------------------------------------------------
# _accessor_penalty
# ---------------------------------------------------------------------------


class TestAccessorPenalty:
    def test_accessor_kind(self) -> None:
        assert _accessor_penalty("accessor", "Foo.bar") == _ACCESSOR_PENALTY

    def test_getter_suffix(self) -> None:
        assert _accessor_penalty("property", "Foo.bar.getter") == _ACCESSOR_PENALTY

    def test_setter_suffix(self) -> None:
        assert _accessor_penalty(None, "Foo.bar.setter") == _ACCESSOR_PENALTY

    def test_case_insensitive_suffix(self) -> None:
        assert _accessor_penalty(None, "Foo.bar.Getter") == _ACCESSOR_PENALTY

    def test_no_penalty_for_function(self) -> None:
        assert _accessor_penalty("function", "Crypto.verify") == 0.0

    def test_no_penalty_for_none_kind_clean_name(self) -> None:
        assert _accessor_penalty(None, "Crypto.verify") == 0.0


# ---------------------------------------------------------------------------
# _compute_score_components
# ---------------------------------------------------------------------------


class TestComputeScoreComponents:
    def test_project_function_no_lexical(self) -> None:
        final, comps = _compute_score_components(
            vector_score=0.80,
            query="wallet",
            source_scope="project",
            kind="function",
            qualified_name="Crypto.verify",
        )
        assert comps.vector_score_normalized == pytest.approx(0.80)
        assert comps.source_scope_score == pytest.approx(1.00)
        assert comps.symbol_kind_boost == pytest.approx(1.00)
        assert comps.lexical_match == pytest.approx(0.0)
        assert comps.penalty == pytest.approx(0.0)
        expected = _W_VECTOR * 0.80 + _W_SCOPE * 1.00 + _W_KIND * 1.00
        assert final == pytest.approx(expected)

    def test_dependency_accessor_with_lexical(self) -> None:
        final, comps = _compute_score_components(
            vector_score=0.90,
            query="wallet",
            source_scope="dependency",
            kind="accessor",
            qualified_name="WalletKit.balance.getter",
        )
        assert comps.source_scope_score == pytest.approx(0.50)
        assert comps.symbol_kind_boost == pytest.approx(0.30)
        assert comps.lexical_match == pytest.approx(1.0)
        assert comps.penalty == pytest.approx(_ACCESSOR_PENALTY)
        expected = (
            _W_VECTOR * 0.90
            + _W_SCOPE * 0.50
            + _W_KIND * 0.30
            + _W_LEXICAL * 1.0
            - _ACCESSOR_PENALTY
        )
        assert final == pytest.approx(expected)

    def test_unknown_scope_and_kind_uses_default(self) -> None:
        final, comps = _compute_score_components(
            vector_score=0.70,
            query="foo",
            source_scope="new_scope",
            kind="new_kind",
            qualified_name="Something.bar",
        )
        assert comps.source_scope_score == pytest.approx(0.50)
        assert comps.symbol_kind_boost == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Scope preference overrides vector score gap
# ---------------------------------------------------------------------------


class TestScopePreference:
    def test_project_beats_dependency_at_equal_vector(self) -> None:
        """Equal vector scores → project ranks before dependency."""
        dep = _hit(
            qualified_name="DepLib.verify", vector_score=0.90, source_scope="dependency"
        )
        proj = _hit(
            qualified_name="App.verify", vector_score=0.90, source_scope="project"
        )
        ranked = _rank([dep, proj])
        assert ranked[0]["qualified_name"] == "App.verify"
        assert ranked[1]["qualified_name"] == "DepLib.verify"

    def test_project_beats_dependency_within_scope_tolerance(self) -> None:
        """project wins even when dependency has higher vector score by ≤ 0.20."""
        # vector gap = 0.10; W_VECTOR * 0.10 = 0.075
        # scope gap = W_SCOPE * (1.0 - 0.5) = 0.075  → equal or project wins on tie
        dep = _hit(
            qualified_name="DepLib.verify", vector_score=0.90, source_scope="dependency"
        )
        proj = _hit(
            qualified_name="App.verify", vector_score=0.80, source_scope="project"
        )
        ranked = _rank([dep, proj])
        assert ranked[0]["qualified_name"] == "App.verify"

    def test_project_loses_to_dependency_outside_tolerance(self) -> None:
        """Dependency wins when its vector advantage exceeds the scope compensation."""
        # vector gap = 0.25 → W_VECTOR * 0.25 = 0.1875 > W_SCOPE * 0.5 = 0.075
        dep = _hit(
            qualified_name="DepLib.verify", vector_score=0.95, source_scope="dependency"
        )
        proj = _hit(
            qualified_name="App.verify", vector_score=0.70, source_scope="project"
        )
        ranked = _rank([dep, proj])
        assert ranked[0]["qualified_name"] == "DepLib.verify"

    def test_workspace_package_beats_dependency(self) -> None:
        dep = _hit(
            qualified_name="Dep.fn", vector_score=0.88, source_scope="dependency"
        )
        ws = _hit(
            qualified_name="Kit.fn", vector_score=0.88, source_scope="workspace_package"
        )
        ranked = _rank([dep, ws])
        assert ranked[0]["qualified_name"] == "Kit.fn"


# ---------------------------------------------------------------------------
# Accessor penalty
# ---------------------------------------------------------------------------


class TestAccessorPenaltyRanking:
    def test_accessor_demoted_below_function(self) -> None:
        """function with lower vector score beats accessor with higher vector score."""
        acc = _hit(
            qualified_name="Model.name.getter",
            vector_score=0.90,
            source_scope="project",
            kind="property",  # suffix triggers penalty even if kind != accessor
        )
        fn = _hit(
            qualified_name="Model.validate",
            vector_score=0.78,
            source_scope="project",
            kind="function",
        )
        ranked = _rank([acc, fn])
        assert ranked[0]["qualified_name"] == "Model.validate"

    def test_accessor_kind_demoted(self) -> None:
        acc = _hit(
            qualified_name="Foo.bar",
            vector_score=0.92,
            source_scope="project",
            kind="accessor",
        )
        fn = _hit(
            qualified_name="Foo.process",
            vector_score=0.80,
            source_scope="project",
            kind="function",
        )
        ranked = _rank([acc, fn])
        assert ranked[0]["qualified_name"] == "Foo.process"


# ---------------------------------------------------------------------------
# Lexical boost
# ---------------------------------------------------------------------------


class TestLexicalBoost:
    def test_lexical_match_elevates_over_non_match(self) -> None:
        """Query substring in name gives a small boost that can resolve near ties."""
        no_match = _hit(
            qualified_name="Crypto.process",
            vector_score=0.82,
            source_scope="project",
            kind="function",
        )
        match = _hit(
            qualified_name="Crypto.verify",
            vector_score=0.80,
            source_scope="project",
            kind="function",
        )
        # vector gap is 0.02 → W_VECTOR * 0.02 = 0.015
        # lexical boost = W_LEXICAL * 1.0 = 0.05 > 0.015 → match wins
        ranked = _rank([no_match, match], query="verify")
        assert ranked[0]["qualified_name"] == "Crypto.verify"


# ---------------------------------------------------------------------------
# Tie-breakers
# ---------------------------------------------------------------------------


class TestTieBreakers:
    def test_kind_priority_breaks_equal_score(self) -> None:
        """function ranked before variable at equal final score."""
        var_hit = _hit(
            qualified_name="App.counter", vector_score=0.85, kind="variable"
        )
        fn_hit = _hit(
            qualified_name="App.process", vector_score=0.85, kind="function"
        )
        ranked = _rank([var_hit, fn_hit])
        assert ranked[0]["qualified_name"] == "App.process"

    def test_project_slug_breaks_tie(self) -> None:
        """Earlier project slug wins when all other factors are equal."""
        b = _hit(
            qualified_name="App.fn",
            vector_score=0.85,
            source_scope="project",
            kind="function",
            project="beta-app",
        )
        a = _hit(
            qualified_name="App.fn",
            vector_score=0.85,
            source_scope="project",
            kind="function",
            project="alpha-app",
        )
        ranked = _rank([b, a])
        assert ranked[0]["project"] == "alpha-app"

    def test_qualified_name_breaks_final_tie(self) -> None:
        """Alphabetically earlier qualified_name wins when everything else ties."""
        z = _hit(
            qualified_name="App.zzz",
            vector_score=0.85,
            source_scope="project",
            kind="function",
            project="my-app",
        )
        a = _hit(
            qualified_name="App.aaa",
            vector_score=0.85,
            source_scope="project",
            kind="function",
            project="my-app",
        )
        ranked = _rank([z, a])
        assert ranked[0]["qualified_name"] == "App.aaa"

    def test_full_five_level_total_ordering(self) -> None:
        """All five tie-break levels produce a total ordering."""
        hits = [
            _hit(
                qualified_name="Z.fn",
                vector_score=0.85,
                source_scope="project",
                kind="function",
                project="z-app",
            ),
            _hit(
                qualified_name="A.fn",
                vector_score=0.85,
                source_scope="project",
                kind="function",
                project="a-app",
            ),
            _hit(
                qualified_name="A.fn",
                vector_score=0.85,
                source_scope="dependency",
                kind="function",
                project="a-app",
            ),
        ]
        ranked = _rank(hits)
        # project scope before dependency scope
        assert ranked[0]["source_scope"] == "project"
        assert ranked[1]["source_scope"] == "project"
        assert ranked[2]["source_scope"] == "dependency"
        # within same scope + kind, a-app before z-app
        assert ranked[0]["project"] == "a-app"
        assert ranked[1]["project"] == "z-app"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_inputs_produce_same_ordered_hash(self) -> None:
        """Ranking two copies of the same inputs yields identical qualified_name hash."""
        hits = [
            _hit(
                qualified_name="App.verify",
                vector_score=0.91,
                source_scope="project",
            ),
            _hit(
                qualified_name="DepLib.verify",
                vector_score=0.93,
                source_scope="dependency",
            ),
            _hit(
                qualified_name="App.parse",
                vector_score=0.88,
                source_scope="project",
            ),
            _hit(
                qualified_name="GenModel.name.getter",
                vector_score=0.90,
                source_scope="generated",
                kind="property",
            ),
        ]

        def _hash(results: list[dict[str, Any]]) -> str:
            payload = "|".join(h["qualified_name"] for h in results)
            return hashlib.sha256(payload.encode()).hexdigest()

        ranked1 = _rank(list(hits))
        ranked2 = _rank(list(hits))
        assert _hash(ranked1) == _hash(ranked2)

    def test_ordering_is_stable_across_input_permutations(self) -> None:
        """Different input orderings produce the same ranked output."""
        import itertools

        hits = [
            _hit(
                qualified_name="C.fn", vector_score=0.90, source_scope="project"
            ),
            _hit(
                qualified_name="B.fn", vector_score=0.90, source_scope="workspace_package"
            ),
            _hit(
                qualified_name="A.fn", vector_score=0.90, source_scope="dependency"
            ),
        ]

        expected = _rank(list(hits))
        for perm in itertools.permutations(hits):
            assert _rank(list(perm)) == expected


# ---------------------------------------------------------------------------
# score_components present in full integration path
# ---------------------------------------------------------------------------


class TestScoreComponentsInResponse:
    """Integration: score_components appears in each result hit."""

    @pytest.mark.asyncio
    async def test_score_components_included_in_hit(self) -> None:
        from unittest.mock import patch

        from palace_mcp.code.find_semantic import semantic_search
        from palace_mcp.embeddings import EmbeddingBackendDispatcher

        class _FakeResult:
            def __init__(
                self,
                single: dict[str, Any] | None = None,
                data: list[dict[str, Any]] | None = None,
            ) -> None:
                self._single = single
                self._data = data or []

            async def single(self) -> dict[str, Any] | None:
                return self._single

            async def data(self) -> list[dict[str, Any]]:
                return self._data

        class _FakeSession:
            async def run(self, query: str, **params: Any) -> _FakeResult:
                if "collect(p.slug)" in query:
                    return _FakeResult(single={"found_projects": ["wallet-core"]})
                if "embedded_cnt" in query:
                    return _FakeResult(
                        data=[{"source_scope": "project", "total": 5, "embedded_cnt": 2}]
                    )
                if "queryNodes" in query:
                    return _FakeResult(
                        data=[
                            {
                                "group_id": "project/wallet-core",
                                "qualified_name": "Wallet.verify",
                                "kind": "function",
                                "file_path": "Src/Wallet.swift",
                                "module_name": "Wallet",
                                "source_scope": "project",
                                "embedding_input_hash": "h1",
                                "commit_sha": None,
                                "score": 0.88,
                            }
                        ]
                    )
                raise AssertionError(f"unexpected query: {query[:60]}")

            async def __aenter__(self) -> "_FakeSession":
                return self

            async def __aexit__(self, *_: Any) -> bool:
                return False

        class _FakeDriver:
            def session(self) -> _FakeSession:
                return _FakeSession()

        class _FakeBackend:
            def embed_text(self, _text: str) -> list[float]:
                return [0.1, 0.2]

        dispatcher = EmbeddingBackendDispatcher(
            {"qodo": _FakeBackend()}, default_backend="qodo"
        )

        with patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=dispatcher,
        ), patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ):
            result = await semantic_search(
                driver=_FakeDriver(),
                query="wallet verify",
                project="wallet-core",
                include_context=False,
            )

        assert result["ok"] is True
        assert result["returned_count"] == 1
        hit = result["result"][0]
        assert "score_components" in hit
        sc = hit["score_components"]
        assert "vector_score_normalized" in sc
        assert sc["vector_score_normalized"] == pytest.approx(0.88)
        assert "source_scope_score" in sc
        assert "symbol_kind_boost" in sc
        assert "lexical_match" in sc
        assert sc["lexical_match"] == pytest.approx(1.0)  # "wallet" in "Wallet.verify"
        assert "penalty" in sc
        assert sc["penalty"] == pytest.approx(0.0)
        assert "ranking_spec_version" in result
        assert result["ranking_spec_version"] == "1"
