# SIP-0110 — Reference Implementation & Reviewer Notes (supporting material)

> Non-normative supporting material for **SIP-0110**. Grounds the proposed indexer changes in the actual `btc_stamps` codebase. See the SIP issue for the normative specification.

## 4. Reference Implementation

### 4.1 Overview

The reference implementation targets the `stampchain-io/btc_stamps` indexer. PRESERVE is an
*additional property layer* over the existing stamp-processing pipeline; it does not replace
any existing path.

### 4.2 Consensus determinism requirement

All migration-record fields written by the indexer MUST derive **solely** from Bitcoin chain
data and the rules in §3. No field may depend on an external `ord` index (that is the
verification layer's job, §3.6 Option 2). This is what keeps cross-indexer consistency
achievable.

### 4.3 Indexer implementation surface (grounded in the actual codebase)

The following references the real modules at
`btc_stamps/indexer/src/index_core/`. Where the brief named a function/table that does not
exist under that name, the closest real equivalent is given and the divergence is flagged.

**Op detection — NOT in `parser.py`.** The brief says to "detect PRESERVE in the parser."
In the actual codebase, `parser.py` contains only the Rust-backed `Parser` class
(`deserialize_transaction`, `batch_parse_transactions`, `parse_block`); it deserializes
transactions and does not perform protocol/op-level detection. **Protocol detection actually
happens downstream**:
- `stamp.py :: get_src_or_img_from_data()` inspects the decoded payload's `p` field and, today,
  raises `ValueError("invalid p")` unless `p.upper() ∈ {"SRC-20","SRC-721","SRC-101"}`.
- `models.py :: StampData.decode_and_reformat_src_string()` sets `self.ident` from `p` after
  checking `config.SUPPORTED_SUB_PROTOCOLS = ["SRC-721","SRC-20","SRC-101"]`.

Therefore the real hook points for PRESERVE detection are `stamp.py` /
`models.py`. The resolved decision (Open Question #9) is: **register `p = "SRC-ORD"` alongside
`SRC-20`/`SRC-721`/`SRC-101` in the protocol-detection path** — i.e. `SUPPORTED_SUB_PROTOCOLS`
(or an equivalent registry) MUST be extended, AND the `get_src_or_img_from_data()` gate that
today `raise ValueError("invalid p")` MUST be extended to **accept `SRC-ORD` and route it to the
new `PRESERVE` processor** (not to the SRC-20 path). Isolation is structural: because
`is_src20()` gates on `ident == "SRC-20"`, a distinct `SRC-ORD` ident never enters
`valid_src20()`, the `SRC20Valid` ledger, or `ledger_hash` — so `PRESERVE` cannot perturb SRC-20
balance consensus. `PRESERVE` also defines its **own** JSON validation and size limits and does
**not** inherit SRC-20's tight JSON string-length limits (a BIP-322 signature is much larger
than any SRC-20 field).

**PRESERVE handler — new module `preserve.py`, modeled on `parse_src20`.** The closest real
pattern is `src20.py`: a module-level `parse_src20(db, src20_dict, processed_src20_in_block,
lock)` entry point that constructs a `Src20Processor` whose `validate_and_process_operation()`
dispatches on `op` to `handle_deploy()` / `handle_mint()` / `handle_transfer()`. A PRESERVE
implementation SHOULD add a parallel module **`preserve.py`** exposing `parse_preserve(...)` and
a `PreserveProcessor` with a `validate_and_process_operation()` implementing the §3.4 rules,
mirroring the SRC-20 structure (including a `PreserveValidator` analogous to `Src20Validator`).
Because the modern SRC-20 substrate is JSON-only, `preserve.py` additionally handles the
**embedded OLGA content** carried alongside the `SRC-ORD` JSON envelope in the same direct,
non-Counterparty transaction (§3.7).

**Block routing — `blocks.py :: BlockProcessor`.** PRESERVE ops route through the existing
`BlockProcessor.process_transaction_results()` (which already calls `parse_stamp(...)` and,
conditionally, `parse_src20(...)`). A parallel branch would call the new
`parse_preserve(...)` when the `SRC-ORD` op is detected and collect results on the
`BlockProcessor` instance (analogous to `self.processed_src20_in_block`), then persist them in
`finalize_block(...)`.

**Check-hashes — `block_validation.py :: create_check_hashes`, NOT `blocks.py`.** The brief
says "include migration records in ledger check-hashes." The real function is
`create_check_hashes(db, block_index, valid_stamps_in_block, processed_src20_in_block,
txhash_list, ...)` in **`block_validation.py`** (called from
`BlockProcessor.finalize_block()`). It computes three per-block hashes via
`check.consensus_hash`:
- `txlist_hash` from the sorted `valid_stamps_in_block`,
- `ledger_hash` from `str(processed_src20_in_block)`,
- `messages_hash` from `str(txhash_list)`.

To bring PRESERVE records under cross-indexer consistency, they MUST be folded deterministically
into `txlist_hash` **or a new dedicated `migration_hash` stream — but NEVER into `ledger_hash`**,
which is SRC-20-specific (`str(processed_src20_in_block)`) and must stay isolated from PRESERVE
(§3.7, Open Question #10). **Recommendation:** add a dedicated **`migration_hash`** (a fourth
hash stream) rather than overloading `txlist_hash`; it keeps PRESERVE provenance cleanly
separable and makes the SRC-20-isolation invariant self-evident. Whatever is chosen, the
serialization MUST be deterministic and derived only from consensus fields (§4.2). **Divergence
note:** there is no single function literally named "ledger check-hashes"; `create_check_hashes`
is the real equivalent, and `ledger_hash` today is specifically the SRC-20 ledger, not a general
stamp ledger — which is exactly why PRESERVE records must not enter it.

**Persistence — new table, modeled on `StampTableV4` / `SRC20Valid`.** The brief's `migrations`
table does not exist. Real precedents: `insert_into_stamp_table()` writes to
`config.STAMP_TABLE = "StampTableV4"`; `insert_into_src20_tables()` writes valid SRC-20 rows to
`SRC20Valid`. A new table (e.g. `stamp_migrations`) SHOULD be created with a primary key on
`stamp_id` and an index on `inscription_id`, holding:

```
stamp_migrations(
  stamp_id            <FK to StampTableV4.stamp>,   -- primary key
  inscription_id      TEXT,                          -- indexed
  genesis_txid        TEXT,
  content_sha256      TEXT,
  mode                TEXT,        -- 'full' | 'anchor'
  proof_type          TEXT,        -- 'bip322' | 'utxo-spend'
  proof_address       TEXT,
  proof_block         INTEGER,     -- msg_block (Method A) / spend height (Method B)
  content_verified    BOOLEAN,     -- consensus-layer hash check (true only for full-mode pass)
  canonical_flag      BOOLEAN,     -- first-valid per §3.4 rule 6
  block_index         INTEGER,
  block_time          <timestamp>
)
```

The table is indexer-internal, but its contents derive from consensus rules, so the derivation
(§3.4) is the normative part; two conformant indexers MUST produce identical `content_verified`
and `canonical_flag` values for the same chain.

**Stamp-number assignment stays unchanged.** A Migration Stamp is still a stamp: it receives its
number via the existing `get_next_stamp_number(db, "stamp")` path in `stamp.py ::
StampProcessor.process_stamp()`. PRESERVE does not alter stamp numbering.

### 4.4 API surface

- `GET /migrations/{inscription_id}` — all migration records referencing an inscription ID
  (there may be several; §3.4 rule 6), each with its `canonical_flag`.
- `GET /stamps/{id}/provenance` — the provenance record for a given Migration Stamp.
- (Option 2) A `verified` status field on the above, sourced from the **external verifier**
  (§3.6), NOT from the indexer. The consensus layer never emits `verified`; it emits
  `content_verified` (the self-contained full-mode hash result) and the raw attestation.

---


---

## Reviewer Notes (non-normative)

**(0) Decisions finalized in this revision.** The following were open in the earlier draft and
are now **decided**, and should be read as design decisions rather than proposals:

- **SIP number = `SIP-0110`** — deliberate, maintainer-reserved thematic mirror of BIP-110
  (§ Numbering note). 0012–0109 stay available for normal sequential assignment; the gap is
  intentional.
- **Operation keyword = `PRESERVE`** (Open Question #2 resolved).
- **Protocol identifier = `p = "SRC-ORD"`**, registered alongside SRC-20/721/101 but routed to a
  separate `PRESERVE` processor and fully isolated from SRC-20 balance consensus (Open Question
  #9 resolved; §3.3, §3.7, §4.3).
- **Encoding = Option (a): a direct, non-Counterparty transaction** on the modern SRC-20-style
  substrate, with `full`-mode content via the existing OLGA P2WSH path (§3.7). The
  Counterparty/SRC-721 route was rejected for its Counterparty consensus dependency.

**Genuinely-remaining open items:** #1 (verification architecture — recommend Option 2), #3
(commit/reveal — recommend defer), #4 (multi-owner canonicity), #5 (signature window N≈144), #6
(SIP-0005 binary-format alignment), #7 (`deps` normativity), #8 (max full-mode size), #10 (add
dedicated `migration_hash` — recommended), #11 (BIP-110 34-byte cap inclusive/exclusive
boundary), #12 (anchor-mode canonical-flag semantics).

**(a) Brief items that could NOT be grounded in real code, and why.**

- **`parser.py` op detection.** The brief says to detect PRESERVE "in the parser." The real
  `parser.py` is a Rust-backed transaction *deserializer* (`Parser.deserialize_transaction`,
  `batch_parse_transactions`, `parse_block`) and does no protocol/op detection. Real detection
  is in `stamp.py :: get_src_or_img_from_data()` and `models.py ::
  decode_and_reformat_src_string()`. Section 4.3 was rewritten to point at the real hook points.
- **PRESERVE handler.** No such handler exists today. Closest real equivalent: `src20.py ::
  parse_src20()` + `Src20Processor.validate_and_process_operation()` dispatching to
  `handle_deploy/handle_mint/handle_transfer`. §4.3 specifies a **new `preserve.py` module**
  (`parse_preserve()` + `PreserveProcessor` + `PreserveValidator`) modeled on this.
- **"ledger check-hashes."** No function by that name. Real equivalent:
  `block_validation.py :: create_check_hashes()` (called from `BlockProcessor.finalize_block`),
  computing `txlist_hash` / `ledger_hash` / `messages_hash` via `check.consensus_hash`. Note
  `ledger_hash` today is specifically the **SRC-20** ledger (`str(processed_src20_in_block)`),
  not a general stamp ledger — flagged as Open Question #10.
- **`migrations` table.** Does not exist. Real precedents: `StampTableV4` (`config.STAMP_TABLE`,
  written by `insert_into_stamp_table`) and `SRC20Valid` (written by `insert_into_src20_tables`).
  §4.3 proposes a new `stamp_migrations` table modeled on these.
- **Payload protocol identifier.** The current code's `get_src_or_img_from_data` raises
  `ValueError("invalid p")` for anything outside `["SRC-20","SRC-721","SRC-101"]`, and
  `SUPPORTED_SUB_PROTOCOLS` does not include a preservation identifier today. **Resolved (Open
  Question #9): `p = "SRC-ORD"`**, registered alongside the existing sub-protocols but routed to
  the new `PRESERVE` processor and isolated from SRC-20 balance consensus. The gate MUST be
  extended to accept `SRC-ORD`.
- **Max full-mode content size.** No single explicit max-size constant was found in `config.py`
  (grep for size/limit constants returned no authoritative max-stamp-size). Left as Open
  Question #8 with the divergence noted.
- **BIP-110 specifics.** Verified against public sources (bip110.org; Bitcoin Knots 29.2
  reference implementation; 256-byte witness-element cap, 34-byte output cap, pre-activation
  UTXO exemption, ~1-year temporary soft fork, ~August 2026 flag day / 55% miner fast-track,
  <1% miner support as of mid-2026). The Motivation subsection was rewritten with these facts
  plus the OLGA-P2WSH-is-exactly-34-bytes analysis. The one remaining unverified detail — the
  inclusive/exclusive semantics of the 34-byte output cap relative to a 34-byte P2WSH output —
  is Open Question #11.

**(b) Additional open questions identified during drafting.** #10 (add a dedicated
`migration_hash`, recommended), #11 (BIP-110 34-byte-cap boundary), #12 (anchor-mode
canonical-flag semantics) — see Open Questions above. (#9, protocol-identifier registration, is
now **resolved** to `p = "SRC-ORD"`.)

**(c) Numbering.** The number is **decided: SIP-0110**, a deliberate, maintainer-reserved
thematic mirror of BIP-110 (§ Numbering note). This intentionally departs from strict sequential
assignment; **0012–0109 remain available** for normal sequential SIPs, and the gap is
intentional, not an error.

**Grounding sources read for §4.3:** `indexer/src/index_core/parser.py`,
`indexer/src/index_core/src20.py`, `indexer/src/index_core/blocks.py`,
`indexer/src/index_core/stamp.py`, `indexer/src/index_core/models.py`,
`indexer/src/index_core/block_validation.py`, `indexer/src/index_core/database.py`,
`indexer/src/config.py`, `docs/PROTOCOLS.md`, `docs/whitepaper/improvement-proposals.md`.
