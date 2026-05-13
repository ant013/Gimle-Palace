# Watchdog Age-Gate Coverage Map (Spec §7)

## (a) Mechanical recovery age gate (`recover_max_age_min`)
- `tests/test_detection.py::test_scan_died_skips_issue_older_than_recover_max_age`
- `tests/e2e/test_gim255_cohort_isolation.py::test_cohort_isolation_recovery_path`

## (b) Legacy handoff detectors age gate (`handoff_recent_window_min`)
- `tests/e2e/test_no_spam_on_stale_issues.py::test_no_spam_on_stale_or_recovery_issues`

## (c) Tier issue-bound detectors age gate (`handoff_recent_window_min`)
- `tests/e2e/test_gim255_cohort_isolation.py::test_cohort_isolation_per_detector_flag`
