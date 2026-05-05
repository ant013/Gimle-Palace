#!/usr/bin/env python3
"""
Phase 0.5 — Per-role deep audit.

For each of 20 paperclip role files:
1. Extract inline content (everything except @include directives + frontmatter).
2. Identify H2/H3 sections in inline.
3. For each shared fragment that role includes, check if same heading exists in fragment
   → flag as INLINE-DUPLICATE candidate.
4. Cross-reference MCP/Subagents/Skills section against actual usage data.
5. Output structured report.
"""
import os
import re
import json
import collections
from pathlib import Path

REPO = Path("/Users/ant013/Android/Gimle-Palace")
ROLES_CLAUDE = REPO / "paperclips" / "roles"
ROLES_CODEX = REPO / "paperclips" / "roles-codex"
FRAGMENTS_ROOT = REPO / "paperclips" / "fragments"

INC_RE = re.compile(r"<!-- @include (fragments/[^ ]+\.md) -->")
H_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.MULTILINE)


def parse_role_file(path):
    """Return dict with frontmatter, includes (list of fragment paths), inline_text."""
    text = path.read_text()
    # strip frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 4)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    includes = []
    inline_lines = []
    for ln in text.split("\n"):
        m = INC_RE.search(ln)
        if m:
            includes.append(m.group(1))
        else:
            inline_lines.append(ln)
    return {"includes": includes, "inline": "\n".join(inline_lines)}


def load_fragment(rel):
    """Load a fragment's text from paperclips/<rel>."""
    p = REPO / "paperclips" / rel
    if not p.exists():
        return None
    return p.read_text()


def extract_headings(text):
    """Return list of (level, title) tuples for H1-H4 in text."""
    out = []
    for m in H_RE.finditer(text):
        level = len(m.group(1))
        title = m.group(2).strip()
        out.append((level, title))
    return out


def normalize_title(t):
    """Normalize for comparison — strip emojis, lowercase, collapse whitespace, drop trailing colon."""
    t = re.sub(r"[^\w\s\-/]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.lower().strip()


def find_inline_duplicates(role_id, role_data):
    """Return list of (heading_in_role, matching_fragment_path, fragment_heading)."""
    role_headings = extract_headings(role_data["inline"])
    role_h_normalized = {normalize_title(t): (lvl, t) for lvl, t in role_headings}
    duplicates = []
    for inc_rel in role_data["includes"]:
        frag_text = load_fragment(inc_rel)
        if frag_text is None:
            continue
        for lvl, title in extract_headings(frag_text):
            n = normalize_title(title)
            if n in role_h_normalized:
                role_lvl, role_title = role_h_normalized[n]
                duplicates.append({
                    "role_heading": role_title,
                    "role_level": role_lvl,
                    "fragment": inc_rel,
                    "fragment_heading": title,
                    "fragment_level": lvl,
                })
    return duplicates


def find_inline_only_sections(role_data):
    """Return inline H2 sections that DO NOT appear in any included fragment.
    These are role-specific content (likely keep)."""
    role_h2_h3 = [
        (lvl, t) for lvl, t in extract_headings(role_data["inline"])
        if lvl in (2, 3)
    ]
    fragment_headings_normalized = set()
    for inc_rel in role_data["includes"]:
        frag_text = load_fragment(inc_rel)
        if frag_text is None:
            continue
        for lvl, t in extract_headings(frag_text):
            fragment_headings_normalized.add(normalize_title(t))
    inline_only = []
    for lvl, t in role_h2_h3:
        if normalize_title(t) not in fragment_headings_normalized:
            inline_only.append({"level": lvl, "title": t})
    return inline_only


def find_subagent_references(text):
    """Find all subagent mentions in text (heuristic: voltagent-* / pr-review-toolkit:* / etc.)."""
    refs = set()
    # voltagent-<plugin>:<name>
    for m in re.finditer(r"`?(voltagent-[a-z\-]+:[a-z\-]+)`?", text):
        refs.add(m.group(1))
    # pr-review-toolkit:<name>
    for m in re.finditer(r"`?(pr-review-toolkit:[a-z\-]+)`?", text):
        refs.add(m.group(1))
    # superpowers:<name>
    for m in re.finditer(r"`?(superpowers:[a-z\-]+)`?", text):
        refs.add(m.group(1))
    # codex-review:<name>
    for m in re.finditer(r"`?(codex-review:[a-z\-]+)`?", text):
        refs.add(m.group(1))
    return sorted(refs)


def main():
    # Actually invoked subagents (from /tmp/agent-tool-audit.py output earlier)
    USED_SUBAGENTS = {
        "voltagent-qa-sec:code-reviewer": 4,
        "voltagent-research:search-specialist": 1,
        "pr-review-toolkit:pr-test-analyzer": 1,
    }

    roles_processed = []
    role_files = sorted(list(ROLES_CLAUDE.glob("*.md"))) + sorted(list(ROLES_CODEX.glob("*.md")))

    for rf in role_files:
        role_id = f"{'claude' if 'roles-codex' not in str(rf) else 'codex'}:{rf.stem}"
        if "roles-codex" in str(rf):
            role_id = f"codex:{rf.stem}"
        else:
            role_id = f"claude:{rf.stem}"
        rd = parse_role_file(rf)
        dups = find_inline_duplicates(role_id, rd)
        inline_only = find_inline_only_sections(rd)
        sub_refs = find_subagent_references(rd["inline"])

        # Classify subagent refs
        sub_status = {}
        for sr in sub_refs:
            if sr in USED_SUBAGENTS:
                sub_status[sr] = f"USED ({USED_SUBAGENTS[sr]} calls)"
            else:
                sub_status[sr] = "REFERENCED-NEVER-CALLED"

        roles_processed.append({
            "role_id": role_id,
            "source": str(rf.relative_to(REPO)),
            "includes_count": len(rd["includes"]),
            "inline_chars": len(rd["inline"]),
            "inline_duplicates": dups,
            "inline_only_sections": inline_only,
            "subagent_refs": sub_status,
        })

    # ---- REPORT ----
    print("=" * 100)
    print("PHASE 0.5 — PER-ROLE DEEP AUDIT REPORT")
    print("=" * 100)
    print(f"Total roles: {len(roles_processed)}")

    # Section A: inline duplicates summary
    print("\n\n## A. INLINE DUPLICATIONS (heading appears both in inline role text AND in included fragment)\n")
    print(f"{'Role':40s}  {'Dup count':>10s}  Top duplicates")
    print("-" * 100)
    for r in sorted(roles_processed, key=lambda x: -len(x["inline_duplicates"])):
        if not r["inline_duplicates"]:
            continue
        top = ", ".join(d["role_heading"] for d in r["inline_duplicates"][:3])
        print(f"  {r['role_id']:38s}  {len(r['inline_duplicates']):>10d}  {top[:60]}")

    print("\n\n## B. PER-ROLE DETAIL (only roles WITH issues)\n")
    for r in sorted(roles_processed, key=lambda x: -len(x["inline_duplicates"])):
        has_issues = r["inline_duplicates"] or any(s == "REFERENCED-NEVER-CALLED" for s in r["subagent_refs"].values())
        if not has_issues:
            continue
        print(f"\n### {r['role_id']}")
        print(f"  source: {r['source']}")
        print(f"  inline chars: {r['inline_chars']}  ({r['inline_chars']//4} t)")
        print(f"  includes: {r['includes_count']}")

        if r["inline_duplicates"]:
            print(f"  **INLINE DUPLICATES** ({len(r['inline_duplicates'])}):")
            for d in r["inline_duplicates"]:
                print(f"    - inline `{d['role_heading']}` (H{d['role_level']}) "
                      f"=== fragment {d['fragment']} `{d['fragment_heading']}` (H{d['fragment_level']})")

        dead_refs = [s for s, st in r["subagent_refs"].items() if st == "REFERENCED-NEVER-CALLED"]
        if dead_refs:
            print(f"  **DEAD SUBAGENT REFS** ({len(dead_refs)}):  " + ", ".join(dead_refs[:8]))
            if len(dead_refs) > 8:
                print(f"     ... + {len(dead_refs) - 8} more")

        used_refs = [s for s, st in r["subagent_refs"].items() if st.startswith("USED")]
        if used_refs:
            print(f"  USED SUBAGENT REFS: {used_refs}")

    # Section C: cross-team comparison
    print("\n\n## C. CROSS-TEAM PARITY (claude:X vs codex:X)\n")
    pairs = [
        ("code-reviewer", "cx-code-reviewer"),
        ("cto", "cx-cto"),
        ("python-engineer", "cx-python-engineer"),
        ("mcp-engineer", "cx-mcp-engineer"),
        ("infra-engineer", "cx-infra-engineer"),
        ("qa-engineer", "cx-qa-engineer"),
        ("technical-writer", "cx-technical-writer"),
        ("research-agent", "cx-research-agent"),
        ("opus-architect-reviewer", "codex-architect-reviewer"),
    ]
    by_id = {r["role_id"]: r for r in roles_processed}
    for cl, cx in pairs:
        c_id = f"claude:{cl}"
        x_id = f"codex:{cx}"
        if c_id not in by_id or x_id not in by_id:
            print(f"  {c_id:40s}  vs  {x_id:35s}  ⚠ missing")
            continue
        c = by_id[c_id]
        x = by_id[x_id]
        diff = c["includes_count"] - x["includes_count"]
        print(f"  {c_id:40s}  inc={c['includes_count']:2d}  vs  {x_id:35s}  inc={x['includes_count']:2d}  Δ={diff:+d} fragments")

    # Section D: fleet-wide subagent reference count
    print("\n\n## D. SUBAGENT REFERENCES — fleet-wide count\n")
    fleet_ref = collections.Counter()
    for r in roles_processed:
        for sr in r["subagent_refs"]:
            fleet_ref[sr] += 1
    for sr, n in fleet_ref.most_common():
        status = ""
        if sr in USED_SUBAGENTS:
            status = f"USED {USED_SUBAGENTS[sr]} calls"
        else:
            status = "DEAD ref"
        print(f"  {n:>2d} roles  {sr:50s}  ({status})")

    # Save full data as JSON
    out_path = "/tmp/role-deep-audit.json"
    with open(out_path, "w") as f:
        json.dump(roles_processed, f, indent=2, default=str)
    print(f"\n\n=== Full data saved to {out_path} ===")


if __name__ == "__main__":
    main()
