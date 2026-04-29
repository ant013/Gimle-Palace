"""ABI 4-byte selector computation via pycryptodome keccak-256 (GIM-124).

Input: canonical function signature, already normalized by slither
  (uint → uint256, int → int256, spaces stripped from type lists).
Output: lowercase hex string "0x" + first 4 bytes of keccak256 digest.
"""

from __future__ import annotations

from Crypto.Hash import keccak


def compute_abi_selector(canonical_signature: str) -> str:
    """Return the 4-byte ABI selector for *canonical_signature*.

    Expects a pre-normalized signature (slither's Function.canonical_name):
      "transfer(address,uint256)"  → "0xa9059cbb"
      "owner()"                   → "0x8da5cb5b"
    """
    k = keccak.new(digest_bits=256)
    k.update(canonical_signature.encode("utf-8"))
    digest = k.hexdigest()
    return "0x" + digest[:8]
