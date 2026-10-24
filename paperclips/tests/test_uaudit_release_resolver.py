from __future__ import annotations

import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projects/uaudit/runtime"))
from uaudit_delivery_contract import _validate_source_ref  # noqa: E402
from uaudit_release_resolver import ResolutionError, Segment, resolve_json, resolve_release_history, valid_branch_name  # noqa: E402


def sha(char: str) -> str:
    return char * 40


class ReleaseResolverTests(unittest.TestCase):
    def test_normal_delta_and_no_change(self) -> None:
        normal = resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=sha("b"), master_anchor_sha=sha("a"), master_head=sha("c"), cursor_is_ancestor_of_release=True, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=True)
        self.assertEqual(normal.kind, "daily")
        self.assertEqual(normal.segments[0].from_sha, sha("a"))
        no_change = resolve_release_history(cursor_sha=sha("b"), release_branch="version/0.50", release_head=sha("b"), master_anchor_sha=sha("a"), master_head=sha("c"), cursor_is_ancestor_of_release=True, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=True)
        self.assertEqual(no_change.kind, "no_change")

    def test_next_release_transition_and_split_history(self) -> None:
        transition = resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=None, master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=None, next_release_branch="version/0.51", next_release_head=sha("c"), master_is_ancestor_of_next_release=True)
        self.assertEqual(transition.kind, "transition")
        self.assertFalse(transition.requires_full_audit)
        split = resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=sha("c"), master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=False, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=False, next_release_branch="version/0.51", next_release_head=sha("d"), master_is_ancestor_of_next_release=False)
        self.assertEqual(split.kind, "blocked_recovery")
        self.assertEqual(split.segments, ())

    def test_absent_base_successor_at_cursor_is_no_change_even_if_master_is_behind(self) -> None:
        result = resolve_release_history(
            cursor_sha=sha("c"), release_branch="version/0.50", release_head=None,
            master_anchor_sha=sha("a"), master_head=sha("b"),
            cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=False,
            master_is_ancestor_of_release=None, next_release_branch="version/0.51",
            next_release_head=sha("c"), master_is_ancestor_of_next_release=False,
        )
        self.assertEqual(result.kind, "no_change")
        self.assertEqual(result.selected_branch, "version/0.51")
        self.assertEqual(result.segments, ())

    def test_absent_base_recovers_from_master_to_successor(self) -> None:
        result = resolve_release_history(
            cursor_sha="3e9a7f427e1f5878738ef21a5b100c56b333ffaa",
            release_branch="version/0.50", release_head=None,
            master_anchor_sha="17144d20e352743f3fde74af4abab8d10f57494a",
            master_head="17144d20e352743f3fde74af4abab8d10f57494a",
            cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=False,
            master_is_ancestor_of_release=None, next_release_branch="version/0.51",
            next_release_head="f5284d8761890a788d33fc3bbeb7702d45e5df61",
            master_is_ancestor_of_next_release=True,
        )
        self.assertEqual(result.kind, "full_recovery")
        self.assertEqual(result.selected_branch, "version/0.51")
        self.assertEqual(
            result.segments,
            (
                Segment(
                    "release", "version/0.51",
                    "17144d20e352743f3fde74af4abab8d10f57494a",
                    "f5284d8761890a788d33fc3bbeb7702d45e5df61",
                ),
            ),
        )
        segment = result.segments[0]
        source_ref = _validate_source_ref({
            "routine_id": "daily-android-version-0.50", "branch": segment.branch,
            "from_sha": segment.from_sha, "to_sha": segment.to_sha,
        }, "forced_full")
        self.assertNotEqual(source_ref["from_sha"], source_ref["to_sha"])

    def test_json_adapter_rejects_unknown_input_and_returns_plain_resolution(self) -> None:
        with self.assertRaises(ResolutionError):
            resolve_json({"unexpected": True})
        result = resolve_json({
            "cursor_sha": sha("a"), "release_branch": "version/0.50", "release_head": sha("b"),
            "master_anchor_sha": sha("a"), "master_head": sha("c"),
            "cursor_is_ancestor_of_release": True, "cursor_is_ancestor_of_master": True,
            "master_is_ancestor_of_release": True,
        })
        self.assertEqual(result["kind"], "daily")
        self.assertEqual(result["segments"][0]["from_sha"], sha("a"))

    def test_json_adapter_rejects_truthy_non_boolean_ancestry(self) -> None:
        value = {
            "cursor_sha": sha("a"), "release_branch": "version/0.50", "release_head": sha("b"),
            "master_anchor_sha": sha("a"), "master_head": sha("c"),
            "cursor_is_ancestor_of_release": True, "cursor_is_ancestor_of_master": "false",
            "master_is_ancestor_of_release": True,
        }
        with self.assertRaisesRegex(ResolutionError, "cursor_is_ancestor_of_master must be boolean"):
            resolve_json(value)
        value["cursor_is_ancestor_of_master"] = True
        value["cursor_is_ancestor_of_release"] = 1
        with self.assertRaisesRegex(ResolutionError, "cursor_is_ancestor_of_release must be boolean or null"):
            resolve_json(value)

    def test_ambiguous_rebase_is_full_recovery(self) -> None:
        result = resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=sha("d"), master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=False, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=True, old_series_equivalence="ambiguous")
        self.assertEqual(result.kind, "full_recovery")
        self.assertTrue(result.requires_full_audit)

    def test_non_ancestor_release_blocks_instead_of_reverse_full_recovery(self) -> None:
        result = resolve_release_history(
            cursor_sha=sha("d"),
            release_branch="version/0.52",
            release_head=sha("b"),
            master_anchor_sha=None,
            master_head=sha("c"),
            cursor_is_ancestor_of_release=False,
            cursor_is_ancestor_of_master=False,
            master_is_ancestor_of_release=False,
            next_release_branch="version/0.53",
            next_release_head=sha("e"),
            master_is_ancestor_of_next_release=True,
            cursor_is_ancestor_of_next_release=True,
        )

        self.assertEqual(result.kind, "blocked_recovery")
        self.assertEqual(result.selected_branch, "version/0.52")
        self.assertEqual(result.selected_head, sha("b"))
        self.assertEqual(result.segments, ())
        self.assertFalse(result.requires_full_audit)

    def test_split_recovery_never_emits_unproven_segments(self) -> None:
        result = resolve_release_history(
            cursor_sha=sha("a"),
            release_branch="version/0.52",
            release_head=sha("b"),
            master_anchor_sha=None,
            master_head=sha("c"),
            cursor_is_ancestor_of_release=False,
            cursor_is_ancestor_of_master=False,
            master_is_ancestor_of_release=False,
            next_release_branch="version/0.53",
            next_release_head=sha("d"),
            master_is_ancestor_of_next_release=False,
            cursor_is_ancestor_of_next_release=False,
        )

        self.assertEqual(result.kind, "blocked_recovery")
        self.assertEqual(result.segments, ())

    def test_rejects_skipping_release_line(self) -> None:
        with self.assertRaises(ResolutionError):
            resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=None, master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=None, next_release_branch="version/0.52", next_release_head=sha("c"), master_is_ancestor_of_next_release=True)


if __name__ == "__main__":
    unittest.main()


class FixedBranchResolverTests(unittest.TestCase):
    def facts(self, **updates):
        value = {
            "tracking_mode": "fixed_branch",
            "cursor_sha": sha("a"), "release_branch": "develop",
            "release_head": sha("b"), "master_anchor_sha": None,
            "master_head": sha("c"), "cursor_is_ancestor_of_release": True,
            "cursor_is_ancestor_of_master": False,
            "master_is_ancestor_of_release": False,
        }
        return {**value, **updates}

    def test_fixed_delta_ignores_master_divergence_and_release_merges(self):
        for master in (sha("c"), sha("b")):
            result = resolve_release_history(**self.facts(master_head=master))
            self.assertEqual(result.kind, "daily")
            self.assertEqual(result.segments, (Segment("release", "develop", sha("a"), sha("b")),))
        result = resolve_release_history(**self.facts(cursor_sha=sha("b"), master_head=sha("d")))
        self.assertEqual(result.kind, "no_change")
        self.assertEqual(result.segments, ())
        later = resolve_release_history(**self.facts(cursor_sha=sha("b"), release_head=sha("d")))
        self.assertEqual(later.segments[0].from_sha, sha("b"))

    def test_fixed_deleted_branch_keeps_safe_master_bridge(self):
        bridge = resolve_release_history(**self.facts(
            release_head=None, cursor_is_ancestor_of_release=None,
            cursor_is_ancestor_of_master=True,
        ))
        self.assertEqual(bridge.kind, "bridge")
        self.assertEqual(bridge.selected_branch, None)
        self.assertEqual(bridge.segments, (Segment("master", "master", sha("a"), sha("c")),))
        equal = resolve_release_history(**self.facts(
            release_head=None, master_head=sha("a"), cursor_is_ancestor_of_release=None,
        ))
        self.assertEqual(equal.kind, "no_change")
        self.assertEqual(equal.segments, ())
        self.assertIn("waiting", equal.reason)
        for ancestry in (False, None):
            blocked = resolve_release_history(**self.facts(
                release_head=None, cursor_is_ancestor_of_release=None,
                cursor_is_ancestor_of_master=ancestry,
            ))
            self.assertEqual(blocked.kind, "blocked_recovery")
            self.assertEqual(blocked.segments, ())

    def test_rewritten_fixed_history_needs_independent_forward_recovery(self):
        recovered = resolve_release_history(**self.facts(
            cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=None,
            master_is_ancestor_of_release=True,
        ))
        self.assertEqual(recovered.kind, "full_recovery")
        self.assertTrue(recovered.requires_full_audit)
        self.assertEqual(recovered.segments, (Segment("release", "develop", sha("c"), sha("b")),))
        for master_relation, head in ((False, sha("b")), (None, sha("b")), (True, sha("c"))):
            blocked = resolve_release_history(**self.facts(
                cursor_is_ancestor_of_release=False,
                master_is_ancestor_of_release=master_relation, release_head=head,
            ))
            self.assertEqual(blocked.kind, "blocked_recovery")
            self.assertEqual(blocked.segments, ())

    def test_fixed_rejects_every_successor_field_including_null(self):
        for field, nonnull in (
            ("next_release_branch", "version/0.54"),
            ("next_release_head", sha("d")),
            ("master_is_ancestor_of_next_release", False),
            ("cursor_is_ancestor_of_next_release", True),
        ):
            for supplied in (nonnull, None):
                with self.subTest(field=field, supplied=supplied):
                    with self.assertRaisesRegex(ResolutionError, "successor"):
                        resolve_json(self.facts(**{field: supplied}))
                    with self.assertRaisesRegex(ResolutionError, "successor"):
                        resolve_release_history(**self.facts(**{field: supplied}))

    def test_unknown_ancestry_is_nullable_but_truthy_values_are_rejected(self):
        facts = self.facts(cursor_is_ancestor_of_master=None)
        self.assertEqual(resolve_json(facts)["kind"], "daily")
        for field in ("cursor_is_ancestor_of_release", "cursor_is_ancestor_of_master", "master_is_ancestor_of_release"):
            for bad in ("false", 1, [], {}):
                with self.subTest(field=field, bad=bad):
                    with self.assertRaisesRegex(ResolutionError, "boolean"):
                        resolve_json(self.facts(**{field: bad}))

    def test_fixed_branch_names_are_safe_and_legacy_stays_version_only(self):
        for branch in ("develop", "dev", "feature/a.b", "version/0.53", "_dev", "a" * 64):
            self.assertTrue(valid_branch_name(branch), branch)
            self.assertEqual(resolve_json(self.facts(release_branch=branch))["selected_branch"], branch)
        for branch in ("", "HEAD", "refs/heads/dev", "-dev", "dev..old", "a//b", "a/.b", "a/b.lock", "a/", "dev.", "a" * 65, "a@{1}", "a\n", "a b", "a~1", "a:b"):
            self.assertFalse(valid_branch_name(branch), branch)
            with self.assertRaises(ResolutionError):
                resolve_json(self.facts(release_branch=branch))
        with self.assertRaises(ResolutionError):
            resolve_json(self.facts(tracking_mode="release_line"))
        for mode in ("auto", None, 1, [], {}):
            with self.assertRaisesRegex(ResolutionError, "tracking_mode"):
                resolve_json(self.facts(tracking_mode=mode))
