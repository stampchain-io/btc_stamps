# SIP-0110 — Test Vectors (supporting material)

> Non-normative supporting material for **SIP-0110: Ordinals Provenance Preservation (PRESERVE)**. Illustrative JSON test vectors (TV-01–TV-15). See the SIP issue for the normative specification. An accepted SIP MUST ship concrete testnet vectors per SIP-0000.

> **Revision note (2026-07 — applies the #878 code-grounded technical review).** Vectors updated
> for: the **2-tx reference model** (full-mode content is a separate, ordinary OLGA stamp
> referenced by `stamp_tx`; rule 3 hashes its **raw on-wire OLGA payload bytes**); the reduced
> **v1.10 scope — Method B (`utxo-spend`) only** (Method A / BIP-322 vectors are retained but
> marked **DEFERRED** to the follow-up SIP and are NOT part of the v1.10 activation vector set);
> failed PRESERVE = **dropped**, identical to pre-activation handling (§3.4 rule 7 as corrected —
> there is no ordinary-stamp fallback on the no-`cpid` substrate); the codified
> `PRESERVE_MAX_FULL_CONTENT_BYTES = 65_535` cap; a corrected TV-04 (its previous
> `inscription_id` was 67 chars and failed the SIP's own rule-2 regex, so it could not isolate
> the rule-3 case); and new vectors TV-11–TV-15.

## Test Vectors

All vectors are illustrative (hashes/signatures/txids are placeholders); an accepted SIP MUST
ship concrete testnet vectors per SIP-0000. Each vector states the expected consensus-layer
outcome.

**Vector conventions (2-tx model).**

- Full-mode vectors involve **two transactions**: a `content_tx` (an **ordinary OLGA stamp**
  carrying the raw content bytes) and the `PRESERVE` sidecar (the JSON envelope shown), whose
  `stamp_tx` field references `content_tx`. Anchor-mode vectors are a single transaction with no
  `stamp_tx`.
- `content_stamp_payload_sha256_recomputed` is the indexer's SHA-256 over the content stamp's
  **raw on-wire OLGA payload bytes** — the reassembled length-prefixed chunk data
  (`chunk[2:2+len]`) minus the 6-byte `stamp:` marker — the §3.4 rule-3 input. No MIME
  normalization, svgz decompression, or base64 decoding is applied before hashing.
- **In every full-mode vector the content stamp is indexed and numbered as an ordinary stamp by
  every indexer (upgraded or not), regardless of the PRESERVE outcome.** The `expected` block
  describes the PRESERVE sidecar.
- A **dropped** PRESERVE produces no stamp, no stamp number, and no `stamp_migrations` row —
  byte-identical to how a pre-activation (or non-upgraded) indexer handles the same transaction.
- Method B proofs carry `proof.utxo` (`"<txid>:<vout>"`, the claimed inscription-holding UTXO);
  verification is pure input-set matching. `msg_block` and the acceptance window apply to
  Method A only.

**TV-01 — Valid full-mode, BIP-322 proof (Method A — DEFERRED; not in the v1.10 activation set).**
```json
{
  "input": {
    "content_tx": "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
    "src": {
      "inscription_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaai0",
      "genesis_txid": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "bip322", "address": "bc1qexampleaddr...", "signature": "AkcwRAIg...==", "msg_block": 900000 },
    "content_stamp_payload_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 900050
  },
  "expected": { "v110_scope": "DEFERRED — Method A ships in a follow-up SIP; under v1.10 rules this op is dropped (unknown proof.type)", "if_method_a_active": { "indexed_as": "migration_stamp", "content_verified": true, "canonical_flag": true }, "reason": "well-formed; declared hash matches the content stamp's raw on-wire payload bytes; valid BIP-322 sig over canonical message; 0 <= 900050-900000 <= 144" }
}
```

**TV-02 — Valid full-mode, UTXO-spend proof (ACCEPTED, canonical — the flagship v1.10 vector).**
```json
{
  "input": {
    "content_tx": "b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2",
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2",
    "src": {
      "inscription_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbi0",
      "genesis_txid": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "content_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
      "content_type": "text/plain", "content_length": 5
    },
    "proof": { "type": "utxo-spend", "address": "bc1qowneraddr...", "utxo": "e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5:0" },
    "tx_spends_proof_utxo": true,
    "inscribed_sat_returned_to_owner": true,
    "content_stamp_payload_sha256_recomputed": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
  },
  "expected": { "indexed_as": "migration_stamp", "content_verified": true, "canonical_flag": true, "reason": "well-formed; declared hash matches the content stamp's raw on-wire payload bytes; the PRESERVE tx spends the claimed proof.utxo (pure input-set match, §3.4 rule 5); inscribed sat preserved to owner output; no window applies to Method B" }
}
```

**TV-03 — Valid anchor-mode, UTXO-spend proof (ACCEPTED, verification pending).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "anchor",
    "src": {
      "inscription_id": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccci3",
      "genesis_txid": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "content_sha256": "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
      "content_type": "video/mp4", "content_length": 8388608
    },
    "proof": { "type": "utxo-spend", "address": "bc1qanchoraddr...", "utxo": "c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3:1" },
    "tx_spends_proof_utxo": true,
    "stamp_confirmation_block": 901010
  },
  "expected": { "indexed_as": "migration_stamp", "content_verified": false, "canonical_flag": true, "reason": "anchor mode: no content stamp and no stamp_tx; hash recorded as unverified claim; proof.utxo spent by this tx; verification-layer must confirm against ord" }
}
```

**TV-04 — Hash mismatch, full mode (PRESERVE DROPPED; content stamp unaffected).**
```json
{
  "input": {
    "content_tx": "d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4",
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4",
    "src": {
      "inscription_id": "ddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddi0",
      "genesis_txid": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "utxo-spend", "address": "bc1qexampleaddr...", "utxo": "d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0:0" },
    "tx_spends_proof_utxo": true,
    "content_stamp_payload_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 902005
  },
  "expected": { "preserve_op": "dropped", "migration_status": "rejected", "content_stamp": "indexed as ordinary stamp (separate tx, unaffected on all indexers)", "reason": "inscription_id now VALID (66 chars, passes §3.4 rule 2) so this vector isolates rule 3: declared content_sha256 != SHA-256 of the content stamp's raw on-wire OLGA payload bytes; §3.4 rule 7 (corrected): failed PRESERVE is dropped — no ordinary-stamp fallback exists on the no-cpid substrate" }
}
```

**TV-05 — Malformed inscription_id (PRESERVE DROPPED).**
```json
{
  "input": {
    "content_tx": "e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5",
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5",
    "src": {
      "inscription_id": "NOT-A-VALID-ID",
      "genesis_txid": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "utxo-spend", "address": "bc1qexampleaddr...", "utxo": "e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0:0" },
    "tx_spends_proof_utxo": true
  },
  "expected": { "preserve_op": "dropped", "migration_status": "rejected", "content_stamp": "indexed as ordinary stamp (separate tx, unaffected)", "reason": "inscription_id does not match ^[0-9a-f]{64}i[0-9]+$ (§3.4 rule 2); §3.4 rule 7 (corrected): dropped, identical to pre-activation handling" }
}
```

**TV-06 — Stale signature outside window (Method A — DEFERRED; PRESERVE DROPPED either way).**
```json
{
  "input": {
    "content_tx": "f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6",
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6",
    "src": {
      "inscription_id": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffi0",
      "genesis_txid": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "bip322", "address": "bc1qprevowner...", "signature": "AkcwRAIg...==", "msg_block": 900000 },
    "content_stamp_payload_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 900500
  },
  "expected": { "preserve_op": "dropped", "migration_status": "rejected", "content_stamp": "indexed as ordinary stamp (separate tx, unaffected)", "reason": "v1.10: proof.type bip322 is out of scope (Method A deferred) — dropped. Under the follow-up SIP's rules: delta = 900500-900000 = 500 > N=144, violating 0 <= delta <= N — dropped (§3.8 edges 4/5; previous-owner replay defense). Not an ordinary-stamp fallback in either case (§3.4 rule 7, corrected)" }
}
```

**TV-07 — Duplicate migration, same inscription same owner (BOTH recorded; first canonical).**
```json
{
  "input": [
    { "content_tx": "7171717171717171717171717171717171717171717171717171717171717171",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "stamp_tx": "7171717171717171717171717171717171717171717171717171717171717171",
      "src": { "inscription_id": "1111111111111111111111111111111111111111111111111111111111111111i0", "genesis_txid": "1111111111111111111111111111111111111111111111111111111111111111", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "utxo-spend", "address": "bc1qsameowner...", "utxo": "1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a:0" },
      "tx_spends_proof_utxo": true,
      "stamp_confirmation_block": 904005 },
    { "note": "second PRESERVE spends the inscription's NEW utxo (the output created by the first spend) — a UTXO can be spent only once",
      "content_tx": "7272727272727272727272727272727272727272727272727272727272727272",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "stamp_tx": "7272727272727272727272727272727272727272727272727272727272727272",
      "src": { "inscription_id": "1111111111111111111111111111111111111111111111111111111111111111i0", "genesis_txid": "1111111111111111111111111111111111111111111111111111111111111111", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "utxo-spend", "address": "bc1qsameowner...", "utxo": "2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b:1" },
      "tx_spends_proof_utxo": true,
      "stamp_confirmation_block": 904110 }
  ],
  "expected": { "indexed_as": ["migration_stamp", "migration_stamp"], "canonical_flag": [true, false], "reason": "§3.4 rule 6: both valid, both recorded; first valid (lower block/tx-index) is canonical; non-uniqueness prevents griefing" }
}
```

**TV-08 — Second migration by a DIFFERENT owner post-sale (RECORDED; canonicity per chosen rule).**
```json
{
  "input": [
    { "note": "original owner migrated earlier at block 905000 (canonical=true), spending the inscription utxo they then held",
      "content_tx": "8181818181818181818181818181818181818181818181818181818181818181",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "stamp_tx": "8181818181818181818181818181818181818181818181818181818181818181",
      "src": { "inscription_id": "2222222222222222222222222222222222222222222222222222222222222222i0", "genesis_txid": "2222222222222222222222222222222222222222222222222222222222222222", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "utxo-spend", "address": "bc1qoriginalowner...", "utxo": "3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c:0" },
      "tx_spends_proof_utxo": true,
      "stamp_confirmation_block": 905005 },
    { "note": "new owner (after legitimate sale) migrates at block 950000, spending the inscription utxo they received",
      "content_tx": "8282828282828282828282828282828282828282828282828282828282828282",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "stamp_tx": "8282828282828282828282828282828282828282828282828282828282828282",
      "src": { "inscription_id": "2222222222222222222222222222222222222222222222222222222222222222i0", "genesis_txid": "2222222222222222222222222222222222222222222222222222222222222222", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "utxo-spend", "address": "bc1qnewowner...", "utxo": "4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d:2" },
      "tx_spends_proof_utxo": true,
      "stamp_confirmation_block": 950004 }
  ],
  "expected": { "indexed_as": ["migration_stamp", "migration_stamp"], "canonical_flag": "OPEN QUESTION #4 — recommended: record both with timestamps; if first-valid rule, canonical=[true,false]; if most-recent-owner rule, consumer decides at display", "reason": "§3.8 edge 8: legitimate multi-owner-over-time; both valid and retained" }
}
```

**TV-09 — Cursed inscription ID (ACCEPTED; no special handling).**
```json
{
  "input": {
    "content_tx": "9393939393939393939393939393939393939393939393939393939393939393",
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "9393939393939393939393939393939393939393939393939393939393939393",
    "src": {
      "inscription_id": "3333333333333333333333333333333333333333333333333333333333333333i0",
      "genesis_txid": "3333333333333333333333333333333333333333333333333333333333333333",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/webp", "content_length": 2048,
      "note": "underlying inscription has a negative inscription NUMBER (cursed); its ID form is unchanged"
    },
    "proof": { "type": "utxo-spend", "address": "bc1qcursedowner...", "utxo": "5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e:0" },
    "tx_spends_proof_utxo": true,
    "content_stamp_payload_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 906003
  },
  "expected": { "indexed_as": "migration_stamp", "content_verified": true, "canonical_flag": true, "reason": "§3.8 edge 3: cursed inscriptions have normal ID form; regex passes; no special handling at consensus" }
}
```

**TV-10 — Oversized content, full mode (PRESERVE DROPPED; anchor-only above the cap).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "4444444444444444444444444444444444444444444444444444444444444444",
    "src": {
      "inscription_id": "4444444444444444444444444444444444444444444444444444444444444444i0",
      "genesis_txid": "4444444444444444444444444444444444444444444444444444444444444444",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 5242880
    },
    "proof": { "type": "utxo-spend", "address": "bc1qbigowner...", "utxo": "6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f6f:0" },
    "tx_spends_proof_utxo": true,
    "declared_full_mode_content_bytes": 5242880,
    "max_full_mode_size": "RESOLVED (#878 review / OQ #8): PRESERVE_MAX_FULL_CONTENT_BYTES = 65535 (2-byte OLGA length prefix; effective media 65529 after the 6-byte stamp: prefix)"
  },
  "expected": { "preserve_op": "dropped", "migration_status": "rejected", "reason": "content_length 5242880 > PRESERVE_MAX_FULL_CONTENT_BYTES = 65535 (§3.8 edge 6, resolved); no conformant OLGA content stamp can carry it — the 2-byte length prefix is a hard cap; above the cap only anchor mode is permitted; §3.4 rule 7 (corrected): dropped, no ordinary-stamp fallback" }
}
```

**TV-11 — Method B, transaction does NOT spend the claimed UTXO (PRESERVE DROPPED).**
```json
{
  "input": {
    "content_tx": "5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b",
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "stamp_tx": "5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b",
    "src": {
      "inscription_id": "5555555555555555555555555555555555555555555555555555555555555555i0",
      "genesis_txid": "5555555555555555555555555555555555555555555555555555555555555555",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "utxo-spend", "address": "bc1qclaimant...", "utxo": "7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a7a:1" },
    "tx_spends_proof_utxo": false,
    "content_stamp_payload_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "expected": { "preserve_op": "dropped", "migration_status": "rejected", "content_stamp": "indexed as ordinary stamp (separate tx, unaffected)", "reason": "§3.4 rule 5 (Method B): the claimed proof.utxo does not appear in the PRESERVE transaction's input set — pure input-set match fails deterministically; §3.4 rule 7 (corrected): dropped" }
}
```

**TV-12 — Acceptance-window boundary, Method A (DEFERRED with Method A; pins the inequality).**
```json
{
  "note": "Pins the window inequality 0 <= confirmation_height - msg_block <= N (N = 144) and the future-dated outcome. Deferred with Method A; under v1.10 rules all three sub-cases are dropped (proof.type bip322 out of scope).",
  "input": [
    { "case": "delta == N (boundary, inclusive)", "proof": { "type": "bip322", "msg_block": 910000 }, "stamp_confirmation_block": 910144 },
    { "case": "delta == N + 1 (just past the window)", "proof": { "type": "bip322", "msg_block": 910000 }, "stamp_confirmation_block": 910145 },
    { "case": "future-dated msg_block (delta < 0)", "proof": { "type": "bip322", "msg_block": 910500 }, "stamp_confirmation_block": 910400 }
  ],
  "expected_under_followup_sip": [
    { "case": "delta == N", "preserve_op": "valid", "reason": "0 <= 144 <= 144 — inclusive upper bound" },
    { "case": "delta == N + 1", "preserve_op": "dropped", "reason": "145 > 144" },
    { "case": "delta < 0", "preserve_op": "dropped", "reason": "future-dated proof is invalid: delta = -100 violates the 0 <= delta lower bound" }
  ]
}
```

**TV-13 — Same-block ordering (two valid PRESERVEs for one inscription in one block).**
```json
{
  "input": [
    { "note": "tx_index 7 within block 912000",
      "content_tx": "6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "stamp_tx": "6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c",
      "src": { "inscription_id": "6666666666666666666666666666666666666666666666666666666666666666i0", "genesis_txid": "6666666666666666666666666666666666666666666666666666666666666666", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "utxo-spend", "address": "bc1qfirstintx...", "utxo": "8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b8b:0" },
      "tx_spends_proof_utxo": true,
      "block_index": 912000, "tx_index": 7 },
    { "note": "tx_index 41 within the SAME block 912000",
      "content_tx": "6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "stamp_tx": "6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d6d",
      "src": { "inscription_id": "6666666666666666666666666666666666666666666666666666666666666666i0", "genesis_txid": "6666666666666666666666666666666666666666666666666666666666666666", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "utxo-spend", "address": "bc1qsecondintx...", "utxo": "9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c:0" },
      "tx_spends_proof_utxo": true,
      "block_index": 912000, "tx_index": 41 }
  ],
  "expected": { "indexed_as": ["migration_stamp", "migration_stamp"], "canonical_flag": [true, false], "reason": "§3.4 rule 6: canonical is ordered by (block height, then in-block tx_index) — 912000/7 beats 912000/41; deterministic from the confirmed chain, never from mempool/observation order" }
}
```

**TV-14 — Oversized JSON envelope (PRESERVE DROPPED; envelope grammar bound).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "anchor",
    "src": {
      "inscription_id": "7777777777777777777777777777777777777777777777777777777777777777i0",
      "genesis_txid": "7777777777777777777777777777777777777777777777777777777777777777",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024,
      "padding": "<key/value filler inflating the serialized envelope beyond the PRESERVE envelope byte cap>"
    },
    "proof": { "type": "utxo-spend", "address": "bc1qbloatowner...", "utxo": "adadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadad:0" },
    "tx_spends_proof_utxo": true,
    "serialized_envelope_bytes": "TBD — exceeds the envelope cap",
    "envelope_cap_note": "PRESERVE_MAX_ENVELOPE_BYTES is TBD (review blocker G8: the envelope JSON grammar — max bytes, key case, duplicate keys, number formats — must be codified before Accepted)"
  },
  "expected": { "preserve_op": "dropped", "migration_status": "rejected", "reason": "serialized envelope exceeds the (TBD) PRESERVE envelope byte cap; malformed/over-limit envelopes have a defined outcome — dropped (§3.4 rules 1 and 7, corrected); no partial processing" }
}
```

**TV-15 — Per-block consensus-hash expectations (PLACEHOLDER — the cross-indexer contract).**

Concrete testnet blocks with expected per-block hashes are REQUIRED before Accepted (AUTHORING
§4: shared vectors are the contract between implementations). This placeholder fixes the
*shape*; every value is TBD until the testnet campaign produces real blocks.

| testnet block | contains | expected `txlist_hash` | expected `migration_hash` | expected `ledger_hash` |
|---|---|---|---|---|
| TBD (pre-activation) | one `p:"SRC-ORD"` PRESERVE | TBD — MUST equal the no-op baseline (op dropped pre-activation) | TBD (empty/absent) | TBD — unchanged (isolation) |
| TBD (post-activation) | TV-02-shaped valid full-mode pair | TBD — includes content stamp + PRESERVE sidecar | TBD — one provenance record | TBD — unchanged (isolation) |
| TBD (post-activation) | TV-04-shaped hash mismatch | TBD — includes content stamp only (sidecar dropped) | TBD (no record) | TBD — unchanged (isolation) |
| TBD (post-activation) | TV-13-shaped same-block duplicate | TBD | TBD — canonical by (block, tx_index) | TBD — unchanged (isolation) |

Notes: `ledger_hash` (`str(processed_src20_in_block)`, SRC-20-only) and `messages_hash` MUST be
byte-identical with and without SIP-0110 enabled on every vector block — the verified isolation
property. A full genesis→tip reparse proving byte-identical pre-activation hashes (via the
existing `validate_block_against_reference` infrastructure) is also required before activation.

---
