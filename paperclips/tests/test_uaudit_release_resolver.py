from __future__ import annotations

import unittest
import json
import subprocess
import tempfile
from types import SimpleNamespace
from unittest import mock

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "projects/uaudit/runtime"))
from uaudit_delivery_contract import _validate_source_ref  # noqa: E402
import uaudit_release_resolver as release_resolver  # noqa: E402
from uaudit_release_resolver import (  # noqa: E402
    ResolutionError,
    Segment,
    discover_release_selection,
    parse_release_branch,
    plan_release_selection,
    resolve_json,
    resolve_release_history,
    verify_selection,
)


def sha(char: str) -> str:
    return char * 40


class ReleaseResolverTests(unittest.TestCase):
    def cursor(self, branch: str = "version/0.52", value: str = "a") -> dict:
        return {
            "schema_version": "uaudit-daily-cursor/v2",
            "active_release_branch": branch,
            "last_successfully_audited_sha": sha(value),
            "last_successful_issue": None,
            "last_successful_at": None,
            "last_delivery_summary_sha256": None,
            "last_telegram_message_id": None,
        }

    def test_canonical_release_parser_rejects_aliases(self) -> None:
        self.assertEqual(parse_release_branch("version/0.52"), (0, 52))
        for invalid in ("version/00.52", "version/0.052", "version/0.52.0", "Version/0.52"):
            with self.subTest(invalid=invalid), self.assertRaises(ResolutionError):
                parse_release_branch(invalid)

    def test_active_branch_has_priority_over_higher_release(self) -> None:
        result = plan_release_selection(
            cursor=self.cursor(),
            release_major=0,
            release_heads={"version/0.52": sha("b"), "version/0.53": sha("c")},
            master_head=sha("d"),
            ancestry={"version/0.52": True, "master": True},
            routine_key="uaudit-daily-android",
            platform="android",
        )
        self.assertEqual(result["resolution_kind"], "daily")
        self.assertEqual(result["selected_branch"], "version/0.52")
        self.assertEqual(result["segment"]["from_sha"], sha("a"))
        self.assertEqual(result["segment"]["to_sha"], sha("b"))

    def test_absent_active_selects_lowest_existing_gap(self) -> None:
        result = plan_release_selection(
            cursor=self.cursor(),
            release_major=0,
            release_heads={"version/0.54": sha("c"), "version/0.55": sha("d")},
            master_head=sha("e"),
            ancestry={"version/0.54": True, "master": True},
            routine_key="uaudit-daily-ios",
            platform="ios",
        )
        self.assertEqual(result["resolution_kind"], "transition")
        self.assertEqual(result["selected_branch"], "version/0.54")
        self.assertEqual(result["missing_versions"], ["version/0.53"])
        self.assertEqual(result["segment"]["from_sha"], sha("a"))
        self.assertEqual(result["segment"]["to_sha"], sha("c"))

    def test_divergent_lowest_existing_successor_blocks_without_skip(self) -> None:
        result = plan_release_selection(
            cursor=self.cursor(),
            release_major=0,
            release_heads={"version/0.53": sha("b"), "version/0.54": sha("c")},
            master_head=sha("d"),
            ancestry={"version/0.53": False, "version/0.54": True, "master": True},
            routine_key="uaudit-daily-android",
            platform="android",
        )
        self.assertEqual(result["resolution_kind"], "blocked_divergent_successor")
        self.assertEqual(result["selected_branch"], "version/0.53")
        self.assertIsNone(result["segment"])

    def test_absent_release_at_master_is_waiting_not_empty_bridge(self) -> None:
        result = plan_release_selection(
            cursor=self.cursor(value="f"),
            release_major=0,
            release_heads={},
            master_head=sha("f"),
            ancestry={"master": True},
            routine_key="uaudit-daily-ios",
            platform="ios",
        )
        self.assertEqual(result["resolution_kind"], "no_change_waiting_release")
        self.assertIsNone(result["segment"])

    def test_legacy_absent_release_at_master_is_no_change(self) -> None:
        result = resolve_release_history(
            cursor_sha=sha("c"), release_branch="version/0.50", release_head=None,
            master_anchor_sha=sha("a"), master_head=sha("c"),
            cursor_is_ancestor_of_release=None, cursor_is_ancestor_of_master=True,
            master_is_ancestor_of_release=None,
        )
        self.assertEqual(result.kind, "no_change")
        self.assertEqual(result.segments, ())

    def test_selection_rejects_unbounded_numeric_gap_and_malformed_ancestry(self) -> None:
        with self.assertRaisesRegex(ResolutionError, "bounded proof limit"):
            plan_release_selection(
                cursor=self.cursor(), release_major=0,
                release_heads={"version/0.999999999": sha("b")}, master_head=sha("c"),
                ancestry={"version/0.999999999": True, "master": True},
                routine_key="uaudit-daily-android", platform="android",
            )
        with self.assertRaisesRegex(ResolutionError, "ancestry must be an object"):
            plan_release_selection(
                cursor=self.cursor(), release_major=0,
                release_heads={}, master_head=sha("c"), ancestry=[],
                routine_key="uaudit-daily-android", platform="android",
            )

    def test_discovery_and_fencing_use_authoritative_remote_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            repo = root / "repo"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "init", "-b", "master", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "uaudit@example.test"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "UAudit Test"], check=True)
            (repo / "value.txt").write_text("base\n")
            subprocess.run(["git", "-C", str(repo), "add", "value.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "base"], check=True, capture_output=True)
            base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "branch", "version/0.52"], check=True)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
            subprocess.run(["git", "-C", str(repo), "push", "origin", "master", "version/0.52"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "checkout", "-b", "version/0.54"], check=True, capture_output=True)
            (repo / "value.txt").write_text("next\n")
            subprocess.run(["git", "-C", str(repo), "commit", "-am", "next"], check=True, capture_output=True)
            successor = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "push", "origin", "version/0.54"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "push", "origin", ":version/0.52"], check=True, capture_output=True)

            cursor = root / "cursor.json"
            cursor.write_text(json.dumps(self.cursor(value=base[0]).copy() | {"last_successfully_audited_sha": base}))
            output = root / "selection.json"
            selection = discover_release_selection(
                repo_path=repo,
                remote_url=str(remote),
                cursor_path=cursor,
                routine_key="uaudit-daily-android",
                platform="android",
                release_major=0,
                output_path=output,
            )
            self.assertEqual(selection["selected_branch"], "version/0.54")
            self.assertEqual(selection["selected_head"], successor)
            self.assertEqual(selection["missing_versions"], ["version/0.53"])
            capability = verify_selection(repo_path=repo, remote_url=str(remote), selection_path=output)
            self.assertEqual(capability.selected_head, successor)

            subprocess.run(["git", "-C", str(repo), "push", "origin", f"{base}:refs/heads/version/0.53"], check=True, capture_output=True)
            with self.assertRaisesRegex(ResolutionError, "lowest same-major successor"):
                verify_selection(repo_path=repo, remote_url=str(remote), selection_path=output)
            subprocess.run(["git", "-C", str(repo), "push", "origin", ":version/0.53"], check=True, capture_output=True)

            subprocess.run(["git", "-C", str(repo), "push", "origin", f"{base}:refs/heads/version/0.52"], check=True, capture_output=True)
            with self.assertRaisesRegex(ResolutionError, "active branch was restored"):
                verify_selection(repo_path=repo, remote_url=str(remote), selection_path=output)

    def test_completed_daily_recovery_precedes_fresh_remote_fencing(self) -> None:
        selection = plan_release_selection(
            cursor=self.cursor(), release_major=0,
            release_heads={"version/0.52": sha("b")}, master_head=sha("c"),
            ancestry={"version/0.52": True, "master": True},
            routine_key="uaudit-daily-android", platform="android",
        )
        with tempfile.TemporaryDirectory() as directory:
            selection_path = Path(directory) / "selection.json"
            selection_path.write_text(
                json.dumps(selection, sort_keys=True, separators=(",", ":")) + "\n"
            )

            class FakeDelivery:
                ContractError = RuntimeError

                @staticmethod
                def _verified_release_capability(**values):
                    return values

                @staticmethod
                def recover_daily_without_fence(_args, capability):
                    self.assertEqual(capability["selected_head"], sha("b"))
                    return {"status": "already_applied"}

                @staticmethod
                def reconcile_daily_verified(_args, _capability):
                    raise AssertionError("completed recovery must not mutate again")

            args = SimpleNamespace(
                helper_manifest=Path(directory) / "helper.manifest.json",
                selection=selection_path,
                repo=Path(directory),
                remote_url="unused-after-completed-recovery",
            )
            with mock.patch.object(release_resolver, "_delivery_module", return_value=FakeDelivery), \
                    mock.patch.object(
                        release_resolver,
                        "verify_selection",
                        side_effect=AssertionError("fresh remote fence must not block exact recovery"),
                    ):
                result = release_resolver.finalize_daily(args)
            self.assertEqual(result, {"status": "already_applied"})

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
