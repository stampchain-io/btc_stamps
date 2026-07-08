# SIP-0110 — Reference Implementation & Reviewer Notes (supporting material)

> Non-normative supporting material for **SIP-0110**. Grounds the proposed indexer changes in the actual `btc_stamps` codebase. See the SIP issue for the normative specification.

> ✅ **Revised per Option A (2026-07-08).** Provenance/canonicity moved **OFF consensus** into the
> verifier (#880) + frontend (see `DIRECTION-DECISION.md`). The indexer's consensus surface is now
> just: **parse + store the immutable raw `p:"SRC-ORD"` claim, compute `content_verified`
> (full-mode byte-hash), and keep the raw-claim table in `purge_block_db` for reorg safety**
> (indexer-internal bookkeeping, **not** a consensus-hash requirement). The **`migration_hash`
> fourth-stream** and the in-consensus **`canonical_flag`** are **removed**; canonicity and the
> "verified" badge are relocated to the verifier. Sections below have been updated to that shape.

> **Revision note (2026-07 — applies the #878 code-grounded technical review).** This revision
> adopts the **2-tx on-wire reference model** for `full` mode (content = a plain OLGA stamp;
> `PRESERVE` = a JSON sidecar referencing it via `stamp_tx`; rule 3 hashes the content stamp's
> **raw on-wire OLGA payload bytes**); reduces the **v1.10 scope to `full` + `anchor`, Method B
> (`utxo-spend`) only** (Method A / BIP-322 deferred to a follow-up SIP); corrects the
> activation/fail-safe description (a non-upgraded indexer **drops** `p:"SRC-ORD"`, it does not
> index it as an ordinary stamp); resolves Open Question **#8**
> (`PRESERVE_MAX_FULL_CONTENT_BYTES = 65_535`) and Open Question **#11** (BIP-110 34-byte cap:
> scriptPubKey, inclusive — favorable); and applies the review's precision fixes to the BIP-110
> facts.

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
Because the modern SRC-20 substrate is JSON-only, `preserve.py` handles **only the JSON
envelope**; in `full` mode the content bytes arrive in a **separate, ordinary OLGA stamp
transaction** referenced by the envelope's `stamp_tx` field — see the on-wire layout below.
`preserve.py` never touches the stamp-content extraction path.

**On-wire layout — the 2-tx reference model (applies #878 review, G1; normative in the SIP).**
Full-mode `PRESERVE` is carried by **two transactions**, not one:

1. **The content transaction — an ordinary OLGA stamp.** The source inscription's content bytes
   ride the existing CP-OLGA stamp pipeline — the raw-binary, length-first, **base64-free**
   carrier (`transaction_utils.py:514-517`: 2-byte big-endian length prefix, then raw chunk
   data; OpenStamp already implements it byte-for-byte). This requires **zero changes** to the
   `#749`-protected extractor: on every indexer, upgraded or not, this transaction is a plain
   stamp and is numbered identically.
2. **The `PRESERVE` transaction — a small, JSON-only op on the direct substrate** (P2WSH data,
   keyburn, no `cpid`) whose envelope adds `"stamp_tx": "<64 hex>"` referencing the content
   transaction. In `anchor` mode there is no content transaction and no `stamp_tx`.

**Rule-3 hashing binds to the wire, not the pipeline.** The §3.4 rule-3 integrity check hashes
the content stamp's **raw on-wire OLGA payload bytes** — the reassembled length-prefixed chunk
data (`chunk[2:2+len]`) minus the leading 6-byte `stamp:` marker (`config.PREFIX`) — **not**
post-pipeline content. Rationale: MIME normalization / svgz-decompression can silently replace
decoded bytes after extraction (`models.py:420-422`), and raw-bytes hashing sidesteps the
base64 / Python-3.13 decoder hazard entirely.

**Design rationale — why not a single-tx binary `SRC-ORD` (rejected).** The single-transaction
alternative (binary content inline on the direct substrate, e.g. a TLV second segment) was
evaluated and rejected for four code-grounded reasons:

1. **The direct substrate is JSON-only and binary-unsafe.** `transaction_utils.py:537` does
   `.rstrip(b"\x00")` *before* reading the 2-byte length prefix (line 541). Binary content whose
   final byte is `0x00` (common across real formats) loses those bytes, the
   `len >= 2 + chunk_length` check fails, and the transaction is silently dropped.
2. **Making it binary-capable means editing the highest-risk consensus surface in the repo.**
   `transaction_utils.py:536-564` is the shared extractor for **all** SRC-20 *and* SRC-101
   parsing — the `#749 (WONTFIX)` zone flagged as consensus-forking. Reordering `rstrip`/length
   would require a full genesis→tip reindex-diff to prove zero historical reclassifications.
3. **You'd still hit base64-or-segment.** The direct payload is JSON, so inline binary is either
   base64-in-JSON (~33% overhead on already-4×-cost output bytes, plus JSON parse-determinism
   risk) or a raw segment appended after the envelope — which *is* the extractor surgery of
   point 2.
4. **It breaks the preservation guarantee.** A `p:"SRC-ORD"` transaction hits
   `raise ValueError("invalid p")` on every non-upgraded indexer (`stamp.py:247-252`) → the
   whole tx is dropped → the content is **lost** on non-upgraded indexers. In the 2-tx model the
   content is a plain OLGA stamp, indexed and numbered identically by *every* indexer; only the
   small provenance sidecar is missed. For a SIP named "Preservation," that property is the
   point.

Two further properties of the 2-tx model: the content stamp is a **Counterparty asset**, so the
preserved content becomes a first-class tradeable Stamp (CP DEX order book, dispensers, the
existing market/indexing stack) — a deliberate upside of the CP-issuance dependency, not just a
caveat; and the **64 KB cap is identical either way** (both carriers share the same 2-byte
length prefix), so a single-tx layout gains nothing on size. Cost of the extra transaction:
~2–5%, shrinking as content grows. Precedent for the 2-tx shape: ord's own commit/reveal, and
SRC-721 mints referencing other stamps via `valid_stamps_in_block`.

**Block routing — `blocks.py :: BlockProcessor`.** PRESERVE ops route through the existing
`BlockProcessor.process_transaction_results()` (which already calls `parse_stamp(...)` and,
conditionally, `parse_src20(...)`). A parallel branch would call the new
`parse_preserve(...)` when the `SRC-ORD` op is detected and collect results on the
`BlockProcessor` instance (analogous to `self.processed_src20_in_block`), then persist them in
`finalize_block(...)`. Resolving a full-mode `stamp_tx` reference that points at a content stamp
in the **same block** uses the `valid_stamps_in_block` collection — the same precedent SRC-721
mints already rely on; the content stamp MUST be confirmed at a lower (block, tx_index) than the
`PRESERVE` op (see §3.4 rule 3).

**Check-hashes — `block_validation.py :: create_check_hashes`, NOT `blocks.py`.** The brief
says "include migration records in ledger check-hashes." The real function is
`create_check_hashes(db, block_index, valid_stamps_in_block, processed_src20_in_block,
txhash_list, ...)` in **`block_validation.py`** (called from
`BlockProcessor.finalize_block()`). It computes three per-block hashes via
`check.consensus_hash`:
- `txlist_hash` from the sorted `valid_stamps_in_block`,
- `ledger_hash` from `str(processed_src20_in_block)`,
- `messages_hash` from `str(txhash_list)`.

**Under Option A there is NO dedicated PRESERVE hash stream.** The earlier draft added a fourth
`migration_hash` stream here; its only purpose was carrying the in-consensus `canonical_flag`/
`verified`, both of which now live off consensus in the verifier (§3.6). So
`create_check_hashes(...)` is **left unchanged** — no fourth stream, no signature change. PRESERVE
records are **not** folded into any consensus hash of their own, and **never** into `ledger_hash`
(SRC-20-specific, `str(processed_src20_in_block)`). Cross-indexer consistency for PRESERVE reduces
to two deterministic, chain-derived facts — the **raw claim record** and **`content_verified`**
(§4.2) — plus the fact that a valid `PRESERVE` sidecar is itself a stamp and therefore already
enters `txlist_hash` (see "Stamp numbering and the activation gate" below). **Divergence note:**
there is no single function literally named "ledger check-hashes"; `create_check_hashes` is the
real equivalent, and `ledger_hash` today is specifically the SRC-20 ledger, not a general stamp
ledger — which is exactly why PRESERVE records must not enter it. What is verified in code:
`ledger_hash` (`str(processed_src20_in_block)`, SRC-20-only) and `messages_hash` (all txids)
**cannot** be affected by PRESERVE.

**Persistence — new table, modeled on `StampTableV4` / `SRC20Valid`.** The brief's `migrations`
table does not exist. Real precedents: `insert_into_stamp_table()` writes to
`config.STAMP_TABLE = "StampTableV4"`; `insert_into_src20_tables()` writes valid SRC-20 rows to
`SRC20Valid`. A new table (e.g. `stamp_migrations`) SHOULD be created with a primary key on
`stamp_id` and an index on `inscription_id`, holding:

```
stamp_migrations(
  stamp_id            <FK to StampTableV4.stamp>,   -- primary key (the PRESERVE sidecar's stamp)
  stamp_tx            TEXT,        -- full mode: txid of the referenced content stamp (§3.3); NULL in anchor mode
  inscription_id      TEXT,                          -- indexed
  genesis_txid        TEXT,
  content_sha256      TEXT,
  mode                TEXT,        -- 'full' | 'anchor'
  proof_type          TEXT,        -- 'utxo-spend' (v1.10); 'bip322' reserved for the follow-up SIP
  proof_address       TEXT,
  proof_utxo          TEXT,        -- Method B: the claimed "<txid>:<vout>" (§3.5, review G3)
  proof_block         INTEGER,     -- spend height (Method B) / msg_block (Method A, deferred)
  content_verified    BOOLEAN,     -- consensus-layer byte-hash check (true only for full-mode pass)
  block_index         INTEGER,
  tx_index            INTEGER,     -- in-block position; lets a verifier reproduce a chain-order canonicity policy (§3.6.2)
  block_time          <timestamp>
)
```

**No `canonical_flag` column (Option A).** Canonicity is a verifier determination off consensus
(§3.6.2); the indexer stores only the raw claims + `content_verified`. `tx_index` is retained only
so a verifier can reproduce a chain-order canonicity policy from the raw claims. The table is
indexer-internal, but its contents derive from consensus rules, so the derivation (§3.5) is the
normative part; two conformant indexers MUST produce identical raw claims and identical
`content_verified` values for the same chain.

**Reorg safety (indexer-internal bookkeeping, not a consensus-hash requirement).**
`stamp_migrations` MUST still be added to the table list purged by `purge_block_db`
(`database.py:1199-1211`). Otherwise a reorg leaves stale raw-claim rows behind and the stored
claims + `content_verified` no longer match the canonical chain after re-derivation. There is no
`migration_hash` to keep in sync, so this is reorg correctness, not consensus-hash agreement.

**Stamp numbering and the activation gate (corrected per the #878 review, G5).** The numbering
*mechanism* is unchanged: a valid stamp receives its number via the existing
`get_next_stamp_number(db, "stamp")` path in `stamp.py :: StampProcessor.process_stamp()`. But
SIP-0110 is an **activation-gated consensus change**, not "purely additive metadata": a valid
`PRESERVE` sidecar is itself assigned a stamp number (`stamp.py:63-64`) and enters `txlist_hash`
(via the sorted `valid_stamps_in_block`, `block_validation.py:70-75`). Post-activation, upgraded
and non-upgraded indexers therefore **diverge on numbering and `txlist_hash`** — the normal
consequence of *any* new stamp-creating op, and exactly why AUTHORING §4/§5 require a
coordinated activation height that all participating indexers ship before. A non-upgraded
indexer **drops** a `p:"SRC-ORD"` transaction outright (`raise ValueError("invalid p")`,
`stamp.py:247-252`) — fail-**safe** per AUTHORING §5, but *not* "indexed as an ordinary stamp."
Under the 2-tx model, the **content** transaction is a plain OLGA stamp and is preserved and
numbered identically on every indexer, upgraded or not; only the small provenance sidecar is
missed by non-upgraded indexers.

### 4.4 API surface

- `GET /migrations/{inscription_id}` — all raw migration claim records referencing an inscription
  ID (there may be several; §3.5 rule 6), each with its `content_verified` bit and
  `(block_index, tx_index)`. **No `canonical_flag`** — canonicity is not an indexer field (§3.6.2).
- `GET /stamps/{id}/provenance` — the raw claim record for a given Migration Stamp (including, in
  full mode, the referenced content stamp's `stamp_tx`).
- **`provenance_state` / `canonicity` / `verified` are served by the external verifier (#880)**
  via `GET {verifier}/provenance/{stamp_id}` (spec §3.6.1; see `FRONTEND-IMPLEMENTATION.md`), NOT
  by the indexer. The consensus layer never emits `verified`/`canonical`; it emits only
  `content_verified` (the self-contained full-mode hash result) and the raw claim.

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
- **Encoding = Option (a): a direct, non-Counterparty transaction** for the `PRESERVE` envelope
  (§3.7). The Counterparty/SRC-721 route was rejected *for the envelope* for its Counterparty
  consensus dependency; note that under the 2-tx model the full-mode **content** deliberately
  rides the CP-OLGA stamp path (see the on-wire layout in §4.3 and its design rationale).
- **On-wire layout = the 2-tx reference model** (#878 review, G1): content = a plain OLGA stamp;
  `PRESERVE` = a JSON sidecar referencing it via `stamp_tx`; rule 3 hashes the content stamp's
  raw on-wire OLGA payload bytes. The single-tx binary `SRC-ORD` alternative is rejected (four
  reasons, §4.3).
- **v1.10 scope = `full` + `anchor`, Method B (`utxo-spend`) only.** Method A (BIP-322) is
  **deferred to a follow-up SIP**: no BIP-322 implementation exists in the dependency tree
  (neither `bitcoinlib` nor `python-bitcoinlib` implements it), and full BIP-322 executes
  Bitcoin script — a library disagreement would become a Stamps consensus bug (§5 item 5's exact
  risk).
- **Maximum full-mode content size = `PRESERVE_MAX_FULL_CONTENT_BYTES = 65_535`** (Open Question
  #8 resolved — see below).
- **BIP-110 34-byte boundary resolved favorably** (Open Question #11 resolved — see below).

**Genuinely-remaining open items (Option A):** #1 (verification architecture — Option 2 adopted;
all provenance/canonicity now off consensus), #3 (commit/reveal — recommend defer), #6 (SIP-0005
binary-format alignment), #7 (`deps` normativity), plus the **off-consensus** items: the
**verifier canonicity policy** (recommend owner-designated / current-owner-wins / mutable) and the
**demand gate** (≥ 2 teams running the verifier + > 500 distinct-creator attestations in 60 days) —
see spec §10.2. **Resolved by Option A (removed from consensus):** #4 (multi-owner canonicity) and
#12 (anchor-mode canonicity) survive only as the verifier-canonicity policy above; #10 (`migration_hash`)
is closed with the removed stream. #5 (signature acceptance window) applies to Method A only and
**defers with it** to the follow-up SIP; the pinned form of the window inequality is
`0 ≤ confirmation_height − msg_block ≤ N` (proposed N = 144), with a future-dated `msg_block`
(negative delta) invalid. #8 and #11 are now **resolved** (see the finalized-decisions list).

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
  not a general stamp ledger — which is why PRESERVE must not enter it. Under Option A no fourth
  stream is added at all (the drafting-era `migration_hash`, Open Question #10, is dropped):
  `create_check_hashes()` is unchanged.
- **`migrations` table.** Does not exist. Real precedents: `StampTableV4` (`config.STAMP_TABLE`,
  written by `insert_into_stamp_table`) and `SRC20Valid` (written by `insert_into_src20_tables`).
  §4.3 proposes a new `stamp_migrations` table modeled on these.
- **Payload protocol identifier.** The current code's `get_src_or_img_from_data` raises
  `ValueError("invalid p")` for anything outside `["SRC-20","SRC-721","SRC-101"]`, and
  `SUPPORTED_SUB_PROTOCOLS` does not include a preservation identifier today. **Resolved (Open
  Question #9): `p = "SRC-ORD"`**, registered alongside the existing sub-protocols but routed to
  the new `PRESERVE` processor and isolated from SRC-20 balance consensus. The gate MUST be
  extended to accept `SRC-ORD`.
- **Max full-mode content size — RESOLVED: `PRESERVE_MAX_FULL_CONTENT_BYTES = 65_535`** (Open
  Question #8; #878 review). The earlier divergence note ("no explicit max-size constant in
  `config.py`") stands, but the binding limit is structural: the OLGA payload's **2-byte
  big-endian length prefix** (`transaction_utils.py:536-546`) hard-caps the payload at
  **65,535 bytes**, binding *below* transaction standardness (~72–74 KB). Effective media size
  is **65,529 bytes** after the 6-byte `stamp:` prefix. Because stamp data is carried in
  **output/base bytes with no witness discount**, witness-scale content (~4 MB) is **not
  reachable** in this encoding. The constant SHOULD be codified in `config.py` at
  implementation time.
- **BIP-110 specifics (corrected per the #878 external review, primary-source-verified).**
  Reference implementation is **Bitcoin Knots v29.3.knots20260508** (not 29.2). Flag-day
  activation is **~September 1, 2026 (height 965,664)**; **August 2026 is the
  mandatory-signaling window**, not the flag day. Miner fast-track: 55% of a 2,016-block period
  (version bit 4); miner support **under 1%** as of mid-2026. The 256-byte witness cap applies
  to **data pushes**, not the tapleaf container — large witness content could be re-chunked
  (less efficiently) rather than being outright blocked. The pre-activation exemption precisely
  **grandfathers *spends of* pre-activation UTXOs** (rather than "exempting UTXOs" loosely).
  **The 34-byte boundary (Open Question #11) is RESOLVED, favorably:** the canonical BIP-110
  text — *"New output scriptPubKeys exceeding 34 bytes are invalid…"* — measures the
  **scriptPubKey** and is **inclusive (≤ 34)**; a P2WSH scriptPubKey is exactly 34 bytes, so
  **new OLGA stamps remain creatable under BIP-110**, while the larger bare-multisig encoding is
  blocked under any reading. The resolution is pinned to the current `bip-0110.mediawiki` text;
  the exact upstream revision/commit hash MUST be recorded when the SIP moves to Accepted (TBD).
  On OLGA efficiency, use sourced figures — **~50% size / ~60–70% cost** improvement over bare
  multisig — not the unsourced "30–95%".

**(b) Additional open questions identified during drafting.** #10 (`migration_hash`) and #12
(anchor-mode canonicity) were drafting-era consensus questions; **Option A resolves both by moving
provenance/canonicity off consensus** — #10 is closed with the removed stream, and #12 becomes a
verifier/frontend floor (an anchor record is never `verified`/`canonical`, §3.6.2). (#9,
protocol-identifier registration, is **resolved** to `p = "SRC-ORD"`; #11, the BIP-110 34-byte-cap
boundary, is now **resolved favorably** — see the BIP-110 bullet in (a).)

**(c) Numbering.** The number is **decided: SIP-0110**, a deliberate, maintainer-reserved
thematic mirror of BIP-110 (§ Numbering note). This intentionally departs from strict sequential
assignment; **0012–0109 remain available** for normal sequential SIPs, and the gap is
intentional, not an error.

**Grounding sources read for §4.3:** `indexer/src/index_core/parser.py`,
`indexer/src/index_core/src20.py`, `indexer/src/index_core/blocks.py`,
`indexer/src/index_core/stamp.py`, `indexer/src/index_core/models.py`,
`indexer/src/index_core/block_validation.py`, `indexer/src/index_core/database.py`,
`indexer/src/config.py`, `docs/PROTOCOLS.md`, `docs/whitepaper/improvement-proposals.md`.
