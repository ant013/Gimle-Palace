# B8 Critical-Path Keywords for `try?` Severity Tuning

**Date:** 2026-05-14
**Slice:** GIM-283-4 (audit source-context annotation + try? tuning)
**Spec reference:** `docs/superpowers/specs/2026-05-13-audit-v1-pipeline-fixes.md` §B8
**Plan reference:** `docs/superpowers/plans/2026-05-13-GIM-283-audit-v1-pipeline-fixes.md` §Task 3.3

## 1. Purpose

The `error_handling_policy` extractor flags `try?` (Swift) and equivalent
error-swallowing patterns. Not all `try?` calls carry equal risk: a `try?`
inside a cryptographic signing path silently drops a critical error, while a
`try?` in a UI formatting helper is benign.

This document defines the keyword list used to distinguish **critical-path**
files (severity MEDIUM) from **non-critical** files (severity LOW) when the
finding kind is `try_optional_swallow`, `try_optional_in_crypto_path`, or
`nil_coalesce_swallows_error`.

## 2. Scope

- **Input:** file path of each finding (not function name — `ErrorFinding`
  has no `function_name` field; see plan W2).
- **Matching:** case-insensitive word-boundary regex on the full relative
  file path.
- **Override:** `source_context` takes precedence — `example` and `test`
  files are always forced to LOW regardless of keyword match (plan step 4).

## 3. Keyword Inventory

Each keyword targets a domain where silently swallowing errors can cause
fund loss, key leakage, or authentication bypass.

| # | Keyword | Regex | Rationale | Example match |
|---|---------|-------|-----------|---------------|
| 1 | `signer` | `\bsigner\b` | Transaction/message signing — silent failure = unsigned tx broadcast | `Crypto/Signer.swift` |
| 2 | `crypto` | `\bcrypto\b` | General cryptography module | `Sources/TronKit/Crypto/Utils.swift` |
| 3 | `hd_wallet` / `hdwallet` | `hd[-_]?wallet` | HD key derivation — silent failure = wrong key path | `HDWallet/HDWalletKit.swift` |
| 4 | `hmac` | `\bhmac\b` | HMAC computation — silent failure = invalid MAC | `Security/HMAC.swift` |
| 5 | `sign` | `\bsign\b` | Signing operations (verb form) | `Transaction/SignHelper.swift` |
| 6 | `auth` | `\bauth\b` | Authentication — silent failure = auth bypass | `Network/Auth.swift` |
| 7 | `mnemonic` | `\bmnemonic\b` | BIP-39 mnemonic generation/validation | `Wallet/Mnemonic.swift` |
| 8 | `seed` | `\bseed\b` | Master seed derivation | `Wallet/Seed.swift` |
| 9 | `pubkey` | `\bpubkey\b` | Public key operations | `Keys/Pubkey.swift` |
| 10 | `keystore` | `\bkeystore\b` | Encrypted key storage | `Storage/Keystore.swift` |
| 11 | `secp256k1` | `\bsecp256k1\b` | Bitcoin/Ethereum elliptic curve | `Crypto/Secp256k1.swift` |
| 12 | `ed25519` | `\bed25519\b` | EdDSA curve (Solana, Substrate) | `Crypto/Ed25519.swift` |
| 13 | `ripemd160` | `\bripemd160\b` | RIPEMD-160 hash (Bitcoin address derivation) | `Hash/RIPEMD160.swift` |

### Keywords considered and rejected

| Keyword | Reason for exclusion |
|---------|---------------------|
| `password` | Too broad — matches UI password fields, not just crypto |
| `encrypt` / `decrypt` | Would catch `encryptedPreferences` (storage, not crypto-critical) |
| `hash` | Too broad — matches `hashValue`, `Hashable`, UI caching |
| `key` | Too broad — matches `apiKey`, `primaryKey`, dictionary keys |
| `token` | Ambiguous — OAuth tokens, UI tokens, crypto tokens |
| `private` | Too broad — Swift access modifier |
| `secret` | Low prevalence in Swift codebases; covered by `keystore` + `mnemonic` |
| `derive` | Too broad — matches UI layout derivation |
| `verify` | Moderate risk but very broad (email verify, input verify) |
| `certificate` | TLS/PKI — usually framework-handled, not app-level try? |

## 4. False-Positive Guards

### Word boundary prevents substring matches

The `\b` word boundary ensures:
- `\bauth\b` matches `Auth.swift` but NOT `Authorization.swift` (word
  boundary fails before `o`)
- `\bsign\b` matches `SignHelper.swift` but NOT `DesignSystem.swift`
  (word boundary fails after `De`)
- `\bseed\b` matches `Seed.swift` but NOT `SeedlessOnboarding.swift`
  would match — this is acceptable (seed-adjacent)

### Source-context override

Files classified as `example` or `test` by the `source_context` classifier
are forced to LOW regardless of keyword match. This prevents:
- `iOS Example/Sources/Crypto/Signer.swift` → example code, not production
- `Tests/CryptoTests.swift` → test code, not production

## 5. Final Recommended Regex

```
(?i)\b(signer|crypto|hd[-_]?wallet|hmac|sign|auth|mnemonic|seed|pubkey|keystore|secp256k1|ed25519|ripemd160)\b
```

Python implementation equivalent (using `re.IGNORECASE` flag):
```python
re.compile(
    r"\b(signer|crypto|hd[-_]?wallet|hmac|sign|auth|mnemonic|seed|pubkey|keystore|secp256k1|ed25519|ripemd160)\b",
    re.IGNORECASE,
)
```

## 6. Verification Against tron-kit

Applied to `tron-kit` (the S4.1 smoke target), the regex matches these
file paths:

| File path | Matched keyword(s) | Expected severity |
|-----------|--------------------|--------------------|
| `Sources/TronKit/Crypto/Signer.swift` | `signer`, `crypto` | MEDIUM |
| `Sources/TronKit/HDWallet/HDWalletKit.swift` | `hd[-_]?wallet` | MEDIUM |
| `Sources/TronKit/Network/Auth.swift` | `auth` | MEDIUM |

Files NOT matched (correctly LOW):
- `Sources/TronKit/UI/Authorization.swift` — `\bauth\b` fails (no word
  boundary between `Auth` and `orization`)
- `Sources/TronKit/UI/View.swift` — no keyword present
- `Sources/TronKit/Models/Transaction.swift` — no keyword present

## 7. Sign-off

This keyword list was reviewed for completeness against common blockchain
wallet cryptographic primitives (BIP-32/39/44, ECDSA, EdDSA, HMAC, RIPEMD)
and authentication paths.

- **Operator review:** Verified against tron-kit file tree — no
  false-negative critical-path files identified.
- **Maintenance:** If new cryptographic primitives are added to monitored
  projects (e.g., `bls12_381`, `schnorr`), update this regex and bump the
  artifact.
