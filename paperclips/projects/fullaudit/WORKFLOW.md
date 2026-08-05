# fullAudit workflow

CEO reads `bin/next_kit.py` and creates at most one child. Existing completed reports are never repeated. The initial child resumes blocked `bitcoin-core-swift`, preserving its saved domain JSON and finishing only required verification/report work. CTO coordinates one kit; auditors and verifier are read-only; Publisher validates and publishes; QA independently checks the same output. Every handoff comments evidence, assigns next owner, verifies once, then stops.
