# Paperclip Runbook Access Decision

Date: 2026-05-03

## Decision

Runtime access to future `paperclips/fragments/lessons/` files is not proven
yet. Until a live Paperclip agent explicitly verifies that it can read those
paths during an assigned run, runbook references are background only.

## Rule

Every runbook-backed safety rule must keep its mandatory executable instruction
inline in the generated agent bundle.

A generated bundle may link to a runbook for incident history, examples, or
maintainer context, but the link cannot be the only copy of the operational
rule.

## Current Status

- No `paperclips/fragments/lessons/` profile split has been implemented yet.
- `paperclips/instruction-profiles.yaml` currently maps profiles to inline
  fragments only.
- The validator treats any future profile `runbooks:` entry as invalid unless
  that profile also sets `inline_rule_required: true`.

## How To Change This Decision

Before allowing runbook-only rules, create a bounded live Paperclip probe that
asks a representative Claude agent and a representative Codex agent to read a
specific `paperclips/fragments/lessons/...` path from their assigned runtime
checkout and report the absolute path and command evidence.

Only after that probe passes may the validator allow `inline_rule_required:
false` for a runbook-backed profile.
