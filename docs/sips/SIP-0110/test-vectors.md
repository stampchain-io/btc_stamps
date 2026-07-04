# SIP-0110 — Test Vectors (supporting material)

> Non-normative supporting material for **SIP-0110: Ordinals Provenance Preservation (PRESERVE)**. Illustrative JSON test vectors (TV-01–TV-10). See the SIP issue for the normative specification. An accepted SIP MUST ship concrete testnet vectors per SIP-0000.

## Test Vectors

All vectors are illustrative (hashes/signatures are placeholders); an accepted SIP MUST ship
concrete testnet vectors per SIP-0000. Each vector states the expected consensus-layer outcome.

**TV-01 — Valid full-mode, BIP-322 proof (ACCEPTED, canonical).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "src": {
      "inscription_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaai0",
      "genesis_txid": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "bip322", "address": "bc1qexampleaddr...", "signature": "AkcwRAIg...==", "msg_block": 900000 },
    "embedded_content_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 900050
  },
  "expected": { "indexed_as": "migration_stamp", "content_verified": true, "canonical_flag": true, "reason": "well-formed; hash matches embedded content; valid BIP-322 sig over canonical message; msg_block within 144 of confirmation" }
}
```

**TV-02 — Valid full-mode, UTXO-spend proof (ACCEPTED).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "src": {
      "inscription_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbi0",
      "genesis_txid": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "content_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
      "content_type": "text/plain", "content_length": 5
    },
    "proof": { "type": "utxo-spend", "address": "bc1qowneraddr...", "msg_block": 900100 },
    "spends_inscription_utxo": true,
    "inscribed_sat_returned_to_owner": true,
    "embedded_content_sha256_recomputed": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
  },
  "expected": { "indexed_as": "migration_stamp", "content_verified": true, "canonical_flag": true, "reason": "well-formed; hash matches; tx spends the claimed inscription UTXO; inscribed sat preserved to owner output" }
}
```

**TV-03 — Valid anchor-mode (ACCEPTED, verification pending).**
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
    "proof": { "type": "bip322", "address": "bc1qanchoraddr...", "signature": "AkcwRAIh...==", "msg_block": 901000 },
    "stamp_confirmation_block": 901010
  },
  "expected": { "indexed_as": "migration_stamp", "content_verified": false, "canonical_flag": true, "reason": "anchor mode: no embedded content; hash recorded as unverified claim; proof signature valid; verification-layer must confirm against ord" }
}
```

**TV-04 — Hash mismatch, full mode (REJECTED as migration; VALID as plain stamp).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "src": {
      "inscription_id": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddi0",
      "genesis_txid": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "bip322", "address": "bc1qexampleaddr...", "signature": "AkcwRAIg...==", "msg_block": 902000 },
    "embedded_content_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 902005
  },
  "expected": { "indexed_as": "ordinary_stamp", "migration_status": "rejected", "reason": "declared content_sha256 != SHA-256 of embedded content; §3.4 rule 3 fails; rule 7 fallback: still a valid stamp if it meets normal stamp rules, but NO migration status" }
}
```

**TV-05 — Malformed inscription_id (REJECTED as migration).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "src": {
      "inscription_id": "NOT-A-VALID-ID",
      "genesis_txid": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "bip322", "address": "bc1qexampleaddr...", "signature": "AkcwRAIg...==", "msg_block": 903000 }
  },
  "expected": { "indexed_as": "ordinary_stamp_or_none", "migration_status": "rejected", "reason": "inscription_id does not match ^[0-9a-f]{64}i[0-9]+$ (§3.4 rule 2); no migration status; if the tx is otherwise a valid stamp it is indexed as ordinary" }
}
```

**TV-06 — Stale signature outside window (REJECTED as migration; post-sale replay defense).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "src": {
      "inscription_id": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffi0",
      "genesis_txid": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 1024
    },
    "proof": { "type": "bip322", "address": "bc1qprevowner...", "signature": "AkcwRAIg...==", "msg_block": 900000 },
    "embedded_content_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 900500
  },
  "expected": { "indexed_as": "ordinary_stamp", "migration_status": "rejected", "reason": "msg_block=900000, confirmation=900500, delta=500 > N=144; §3.8 edge 4/5; defends previous-owner replay after sale" }
}
```

**TV-07 — Duplicate migration, same inscription same address (BOTH recorded; first canonical).**
```json
{
  "input": [
    { "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "src": { "inscription_id": "1111111111111111111111111111111111111111111111111111111111111111i0", "genesis_txid": "1111111111111111111111111111111111111111111111111111111111111111", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "bip322", "address": "bc1qsameowner...", "signature": "AkcwRAIg...==", "msg_block": 904000 },
      "stamp_confirmation_block": 904005 },
    { "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "src": { "inscription_id": "1111111111111111111111111111111111111111111111111111111111111111i0", "genesis_txid": "1111111111111111111111111111111111111111111111111111111111111111", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "bip322", "address": "bc1qsameowner...", "signature": "AkcwRAIg...==", "msg_block": 904100 },
      "stamp_confirmation_block": 904110 }
  ],
  "expected": { "indexed_as": ["migration_stamp", "migration_stamp"], "canonical_flag": [true, false], "reason": "§3.4 rule 6: both valid, both recorded; first valid (lower block/tx-index) is canonical; non-uniqueness prevents griefing" }
}
```

**TV-08 — Second migration by a DIFFERENT address post-sale (RECORDED; canonicity per chosen rule).**
```json
{
  "input": [
    { "note": "original owner migrated earlier at block 905000 (canonical=true)",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "src": { "inscription_id": "2222222222222222222222222222222222222222222222222222222222222222i0", "genesis_txid": "2222222222222222222222222222222222222222222222222222222222222222", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "bip322", "address": "bc1qoriginalowner...", "signature": "AkcwRAIg...==", "msg_block": 905000 },
      "stamp_confirmation_block": 905005 },
    { "note": "new owner (after legitimate sale) migrates at block 950000",
      "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
      "src": { "inscription_id": "2222222222222222222222222222222222222222222222222222222222222222i0", "genesis_txid": "2222222222222222222222222222222222222222222222222222222222222222", "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "content_type": "image/png", "content_length": 1024 },
      "proof": { "type": "bip322", "address": "bc1qnewowner...", "signature": "AkcwRAIh...==", "msg_block": 950000 },
      "stamp_confirmation_block": 950004 }
  ],
  "expected": { "indexed_as": ["migration_stamp", "migration_stamp"], "canonical_flag": "OPEN QUESTION #4 — recommended: record both with timestamps; if first-valid rule, canonical=[true,false]; if most-recent-owner rule, consumer decides at display", "reason": "§3.8 edge 8: legitimate multi-owner-over-time; both valid and retained" }
}
```

**TV-09 — Cursed inscription ID (ACCEPTED; no special handling).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "src": {
      "inscription_id": "3333333333333333333333333333333333333333333333333333333333333333i0",
      "genesis_txid": "3333333333333333333333333333333333333333333333333333333333333333",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/webp", "content_length": 2048,
      "note": "underlying inscription has a negative inscription NUMBER (cursed); its ID form is unchanged"
    },
    "proof": { "type": "bip322", "address": "bc1qcursedowner...", "signature": "AkcwRAIg...==", "msg_block": 906000 },
    "embedded_content_sha256_recomputed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stamp_confirmation_block": 906003
  },
  "expected": { "indexed_as": "migration_stamp", "content_verified": true, "canonical_flag": true, "reason": "§3.8 edge 3: cursed inscriptions have normal ID form; regex passes; no special handling at consensus" }
}
```

**TV-10 — Oversized content, full mode (REJECTED as migration; anchor-only above limit).**
```json
{
  "input": {
    "p": "SRC-ORD", "op": "PRESERVE", "mode": "full",
    "src": {
      "inscription_id": "4444444444444444444444444444444444444444444444444444444444444444i0",
      "genesis_txid": "4444444444444444444444444444444444444444444444444444444444444444",
      "content_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "content_type": "image/png", "content_length": 5242880
    },
    "proof": { "type": "bip322", "address": "bc1qbigowner...", "signature": "AkcwRAIg...==", "msg_block": 907000 },
    "declared_full_mode_content_bytes": 5242880,
    "max_full_mode_size": "OPEN QUESTION #8 — reuse existing stamp limit or migration-specific"
  },
  "expected": { "indexed_as": "rejected_or_ordinary", "migration_status": "rejected", "reason": "content exceeds max full-mode size (§3.8 edge 6); above the limit only anchor mode is permitted; full-mode over-limit fails as migration (rule 7 fallback)" }
}
```

---

