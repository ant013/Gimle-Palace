#!/usr/bin/env python3
import json, os, re, glob, collections

PROJ_DIR = "/Users/anton/.claude/projects/-Users-anton--paperclip-instances-default-projects-9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64-e0cd7a7a-910d-4893-8b73-bfa1124ccb8f--default"

ROLE_MARKERS = [
    ("# CTO — Gimle", "CTO"),
    ("# CodeReviewer — Gimle", "CodeReviewer"),
    ("# PythonEngineer — Gimle", "PythonEngineer"),
    ("# MCPEngineer — Gimle", "MCPEngineer"),
    ("# InfraEngineer — Gimle", "InfraEngineer"),
    ("# QAEngineer — Gimle", "QAEngineer"),
    ("# TechnicalWriter — Gimle", "TechnicalWriter"),
    ("# OpusArchitectReviewer — Gimle", "OpusArchitectReviewer"),
    ("# SecurityAuditor — Gimle", "SecurityAuditor"),
    ("# ResearchAgent", "ResearchAgent"),
    ("# BlockchainEngineer", "BlockchainEngineer"),
    ("# CXCodeReviewer", "cx-CodeReviewer"),
    ("# CXCTO", "cx-CTO"),
    ("# CXPythonEngineer", "cx-PythonEngineer"),
    ("# CXMCPEngineer", "cx-MCPEngineer"),
    ("# CXInfraEngineer", "cx-InfraEngineer"),
    ("# CXQAEngineer", "cx-QAEngineer"),
    ("# CXTechnicalWriter", "cx-TechnicalWriter"),
    ("# CXResearchAgent", "cx-ResearchAgent"),
    ("# CodexArchitectReviewer", "codex-ArchitectReviewer"),
]


def detect_role(text):
    scores = collections.Counter()
    for marker, role in ROLE_MARKERS:
        scores[role] += text.count(marker) * 100
        scores[role] += text.count(role)
    if not scores:
        return None
    role, score = scores.most_common(1)[0]
    return role if score > 0 else None


agents_subagent = collections.defaultdict(collections.Counter)
agents_skill = collections.defaultdict(collections.Counter)
agents_session_count = collections.Counter()
agents_tool_total = collections.Counter()
unattributed = []

session_files = sorted(glob.glob(os.path.join(PROJ_DIR, "*.jsonl")))
print(f"Scanning {len(session_files)} sessions...")

for sf in session_files:
    with open(sf) as f:
        text = f.read()
    role = detect_role(text)
    if not role:
        unattributed.append(os.path.basename(sf))
        continue
    agents_session_count[role] += 1
    for ln in text.split("\n"):
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        msg = d.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "tool_use":
                continue
            tn = item.get("name", "")
            inp = item.get("input", {}) or {}
            agents_tool_total[role] += 1
            if tn in ("Agent", "Task"):
                sub = inp.get("subagent_type") or "(default)"
                agents_subagent[role][sub] += 1
            elif tn == "Skill":
                sk = inp.get("skill", "")
                agents_skill[role][sk] += 1

print(f"\nAttributed: {sum(agents_session_count.values())} / {len(session_files)}  (unattributed {len(unattributed)})")
print()
print(f"{'Role':25s}  sessions  tools  uniq_sub  uniq_skill")
print("-" * 70)
for role in sorted(agents_session_count, key=lambda r: -agents_session_count[r]):
    print(f"  {role:23s}  {agents_session_count[role]:>8d}  {agents_tool_total[role]:>5d}  "
          f"{len(agents_subagent[role]):>8d}  {len(agents_skill[role]):>10d}")

print("\n=== SUBAGENT total across fleet ===")
ts = collections.Counter()
for c in agents_subagent.values():
    ts.update(c)
for sa, n in ts.most_common():
    print(f"  {n:>4d}  {sa}")

print("\n=== SKILL total across fleet ===")
tk = collections.Counter()
for c in agents_skill.values():
    tk.update(c)
for sk, n in tk.most_common():
    print(f"  {n:>4d}  {sk}")

print("\n=== Per-role SUBAGENT detail ===")
for role in sorted(agents_subagent, key=lambda r: -agents_session_count[r]):
    if not agents_subagent[role]:
        continue
    print(f"\n  {role}:")
    for sa, n in agents_subagent[role].most_common():
        print(f"    {n:>4d}  {sa}")

print("\n=== Per-role SKILL detail ===")
for role in sorted(agents_skill, key=lambda r: -agents_session_count[r]):
    if not agents_skill[role]:
        continue
    print(f"\n  {role}:")
    for sk, n in agents_skill[role].most_common():
        print(f"    {n:>4d}  {sk}")
