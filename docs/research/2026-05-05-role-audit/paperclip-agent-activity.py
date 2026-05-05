#!/usr/bin/env python3
"""Read paperclip issues JSON from stdin, count activity per agent UUID."""
import json, sys, collections

data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get('issues', data.get('items', []))

agents = {
    "10a4968e-ff2c-471a-a5a8-98026aeead1b": "CEO",
    "7fb0fdbb-e17f-4487-a4da-16993a907bec": "CTO",
    "bd2d7e20-7ed8-474c-91fc-353d610f4c52": "CodeReviewer",
    "89f8f76b-844b-4d1f-b614-edbe72a91d4b": "InfraEngineer",
    "127068ee-b564-4b37-9370-616c81c63f35": "PythonEngineer",
    "58b68640-1e83-4d5d-978b-51a5ca9080e0": "QAEngineer",
    "0e8222fd-88b9-4593-98f6-847a448b0aab": "TechnicalWriter",
    "274a0b0c-ebe8-4613-ad0e-3e745c817a97": "MCPEngineer",
    "0083815d-78fa-4646-bc2d-fa6a9c10c25c": "ResearchAgent",
    "9874ad7a-dfbc-49b0-b3ed-d0efda6453bb": "BlockchainEngineer",
    "a56f9e4a-ef9c-46d4-a736-1db5e19bbde4": "SecurityAuditor",
    "8d6649e2-2df6-412a-a6bc-2d94bab3b73f": "OpusArchitectReviewer",
}

assigned = collections.Counter()
exec_last = collections.Counter()
created = collections.Counter()
for i in items:
    if i.get('assigneeAgentId'):
        assigned[i['assigneeAgentId']] += 1
    eak = i.get('executionAgentNameKey')
    if eak:
        exec_last[eak] += 1
    if i.get('createdByAgentId'):
        created[i['createdByAgentId']] += 1

# combined
combined = collections.Counter()
for c in (assigned, exec_last, created):
    combined.update(c)

print(f"Total issues sampled: {len(items)}\n")
print(f"{'Agent':25s}  assigned  exec_last  created  total  UUID")
print("-" * 100)
known_uuids = set(agents.keys())
seen = set()
for aid, _ in combined.most_common():
    name = agents.get(aid, "(unknown)")
    print(f"  {name:23s}  {assigned[aid]:>8d}  {exec_last[aid]:>9d}  {created[aid]:>7d}  {combined[aid]:>5d}  {aid}")
    seen.add(aid)

# Roles in known list with ZERO activity
print("\n=== Claude roles with ZERO activity ===")
for aid, name in agents.items():
    if aid not in seen:
        print(f"  {name:25s}  {aid}  ⚠ DEAD?")

# All unknown UUIDs (codex etc.)
unknown = [(aid, combined[aid]) for aid in seen if aid not in known_uuids]
print(f"\n=== Non-claude UUIDs (codex / other) — {len(unknown)} unique ===")
for aid, n in sorted(unknown, key=lambda x: -x[1]):
    print(f"  count={n:3d}  {aid}")
