from __future__ import annotations

import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projects/uaudit/runtime"))
from uaudit_release_resolver import ResolutionError, resolve_release_history  # noqa: E402


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

    def test_ambiguous_rebase_is_full_recovery(self) -> None:
        result = resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=sha("d"), master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=False, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=True, old_series_equivalence="ambiguous")
        self.assertEqual(result.kind, "full_recovery")
        self.assertTrue(result.requires_full_audit)

    def test_rejects_skipping_release_line(self) -> None:
        with self.assertRaises(ResolutionError):
            resolve_release_history(cursor_sha=sha("a"), release_branch="version/0.50", release_head=None, master_anchor_sha=sha("a"), master_head=sha("b"), cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=True, master_is_ancestor_of_release=None, next_release_branch="version/0.52", next_release_head=sha("c"), master_is_ancestor_of_next_release=True)


if __name__ == "__main__":
    unittest.main()
