from __future__ import annotations

import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projects/uaudit/runtime"))
from uaudit_delivery_contract import _validate_source_ref  # noqa: E402
from uaudit_release_resolver import ResolutionError, Segment, resolve_json, resolve_release_history  # noqa: E402


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
        self.assertEqual(split.kind, "split_recovery")
        self.assertEqual(len(split.segments), 2)

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

    def test_ambiguous_rebase_is_full_recovery(self) -> None:
        result = resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=sha("d"), master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=False, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=True, old_series_equivalence="ambiguous")
        self.assertEqual(result.kind, "full_recovery")
        self.assertTrue(result.requires_full_audit)

    def test_rejects_skipping_release_line(self) -> None:
        with self.assertRaises(ResolutionError):
            resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=None, master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=None, next_release_branch="version/0.52", next_release_head=sha("c"), master_is_ancestor_of_next_release=True)


if __name__ == "__main__":
    unittest.main()
