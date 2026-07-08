# SIP-0110: Ordinals Provenance Preservation ("Stamp an Inscription") — PRESERVE

**Status**: Draft
**Author**: reinamora137
**Type**: Standards Track
**Created**: 2026-07-03
**Requires**: (none — self-contained; interacts with SIP-0005 if it activates first)
**Related**: SIP-0000 (#686, process), SIP-0002 (#484, superseded UTXO binding), SIP-0005
(#688, binary transfer format), #878 (SIP issue), #880 (verifier tool)

> ✅ **DIRECTION: revised per Option A (2026-07-08).** Independent community-alignment reviews
> (Anthropic Opus + xAI Grok) and the stampchain.io frontend team converged on **Option A: all
> provenance/canonicity lives OFF consensus, in the verifier (#880) + frontend; the indexer emits
> only the immutable raw `p:"SRC-ORD"` claim record + `content_verified` (the full-mode byte-hash)
> — no `migration_hash` consensus stream, no in-consensus `canonical_flag`, no consensus
> `verified`.** This body **has been revised to that shape**; the earlier in-consensus
> tradeable-canonical design is superseded. See
> **[`DIRECTION-DECISION.md`](./DIRECTION-DECISION.md)** for the reconciliation; the applied
> revisions live in §3.6 (verifier + frontend UX contract), §3.9 (creator consent), §5 (no
> consensus-hash stream), and §10 (ratification ledger + demand gate).

> **Normative status of this file.** This is the **committed normative specification** for
> SIP-0110. It consolidates the §3.x consensus rules that previously lived only in the body of
> GitHub issue **#878** into a repo file that is version-controlled, diff-able in PRs, and pinned
> to the codebase it governs. Where this file and the #878 issue body disagree, **this file is
> authoritative** once merged; the issue body should be updated to link here.
>
> This is a deliberate deviation from the "normative spec stays in the GitHub issue" arrangement
> described in `docs/sips/AUTHORING.md §8` (the "SIP-0110 split pattern"). The rationale: a
> consensus specification that two independent indexers must agree on byte-for-byte should not
> live only in a mutable, unversioned issue body. `AUTHORING.md §8` SHOULD be updated to reflect
> that consensus-critical SIPs commit their normative spec (tracked as a follow-up; see the PR).
>
> The two existing supporting files remain **non-normative**:
> [`reference-implementation.md`](./reference-implementation.md) (code grounding) and
> [`test-vectors.md`](./test-vectors.md) (illustrative vectors).
>
> **Open ratification items** are marked inline as `TODO(ratify)` and collected in §10. They MUST
> be resolved before this SIP moves to **Accepted**. Where the #878 issue body was ambiguous, the
> ambiguity is preserved as a `TODO(ratify)` rather than resolved by invention.

---

## Abstract

This SIP defines an optional Bitcoin Stamps operation, **`PRESERVE`**, that lets the current
owner of a Bitcoin Ordinals inscription create a Stamps asset which preserves that inscription's
content on the Bitcoin UTXO set and records a one-time, cryptographic provenance attestation
binding the new Stamp to the source inscription.

Two modes are supported:

- **`full`** — the complete inscription content is embedded on-chain using the existing OLGA
  P2WSH stamp encoding, and the payload carries a SHA-256 that the indexer verifies against the
  embedded bytes. Flagship mode; targeted at small/medium content.
- **`anchor`** — only metadata plus a SHA-256 of the content is embedded, for inscriptions too
  large to embed economically. The hash is an **unverified-at-consensus claim** (§3.4 rule 4).

"Migration" is a convenience label, **not** a literal claim: the source inscription is not moved,
spent (except optionally as a one-time **spend attestation**, §3.5.1), pruned, or invalidated. `full`-mode content
gains Bitcoin's **structural** UTXO-set persistence guarantee (every validating node must retain
the UTXO set), whereas inscription content lives in **witness** data whose retention is a
**social** guarantee. Migration-Stamp ownership follows normal account/address-based Stamps
rules; the link to the source inscription is a one-time attestation recorded at creation, not a
live binding.

The motivation, honest-economics analysis, and the BIP-110 resilience framing (the source of the
`0110` number) are non-normative and are retained in issue **#878**; this file carries the
**normative Specification** and its implementation-binding appendices.

---

## 2. Scope for v1.10 (normative)

The **v1.10** activation ships a deliberately reduced surface:

- **Modes:** `full` and `anchor`.
- **Proof methods:** **Method B (`utxo-spend`) only.** Method A (`bip322`) is **deferred to a
  follow-up SIP** — no BIP-322 implementation exists in the dependency tree, and full BIP-322
  executes Bitcoin script, so a library disagreement would become a Stamps consensus bug (§7
  item 5). Method A is specified here (§3.5) for completeness and forward-compatibility, but a
  `proof.type` other than `"utxo-spend"` MUST be **dropped** under v1.10 rules.
- **Verification architecture:** Option 2 (two-tier), with the verifier (#880) shipping
  **alongside** the indexer change.

---

## 3. Specification

The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as in RFC 2119.

### 3.1 Terminology

- **Source inscription** — the Ordinals inscription whose content is being preserved.
- **Migration Stamp** — the Stamps asset created by a `PRESERVE` operation (the JSON sidecar).
- **Content stamp** — in `full` mode, the ordinary OLGA stamp transaction that carries the
  preserved content bytes and is referenced by the sidecar's `stamp_tx` (§3.3).
- **Provenance attestation** — the one-time, creation-time claim binding the Migration Stamp to
  the source inscription (inscription ID + genesis txid + content hash + spend attestation).
- **Spend attestation** — the one-time, creation-time *fact* that the `PRESERVE` transaction spent
  a named UTXO (§3.5.1, Method B). It is **not** an ownership proof and is **not**
  consensus-authoritative; whether that UTXO actually held the inscription is checked off consensus
  by the verifier.
- **Consensus layer** — validation performed by the Stamps indexer using only data derivable
  from the Bitcoin chain and the rules in this SIP. Under Option A it emits exactly two things per
  `PRESERVE`: the immutable raw claim record and `content_verified` (§5).
- **Verification / verifier layer** — a separate, non-consensus service (#880) that checks the
  attestation against a live Ordinals (`ord`) index and **owns** `provenance_state`, `canonicity`,
  `attestation`, competing-claim resolution, and the "verified" badge (§3.6). These are
  re-checkable live and explicitly **mutable**; the indexer never emits them.

### 3.2 One-time proof is NOT persistent UTXO binding (read this first)

SIP-0002 (SRC-20 UTXO Binding, #484) was **superseded** because binding an account-model asset's
ownership to a specific UTXO caused accidental loss when a non-protocol-aware wallet spent that
UTXO. This SIP does **not** reintroduce persistent UTXO binding:

> The ownership proof in this SIP is a **single historical event, verified once, at one block
> height**. It creates no ongoing UTXO state in the indexer. In Method B (§3.5), the fact that the
> source inscription's UTXO was spent as an input to the Stamp-creating transaction is a one-time
> fact recorded at creation. The indexer does not thereafter watch that UTXO, does not track the
> inscription's future movements, and does not bind the Migration Stamp's ownership to any UTXO.
> Migration-Stamp ownership follows normal account/address-based Stamps rules, identically to any
> other stamp.

### 3.3 On-wire layout — the 2-tx reference model (normative)

`PRESERVE` in `full` mode is carried by **two transactions**:

1. **The content transaction — an ordinary OLGA stamp.** The source inscription's content bytes
   ride the existing CP-OLGA stamp pipeline (the raw-binary, length-first, base64-free carrier:
   a 2-byte big-endian length prefix, then raw chunk data, identified by the
   `config.PREFIX = b"stamp:"` marker). This requires **zero** changes to the stamp-content
   extractor. On every indexer — upgraded or not — this transaction is a plain stamp and is
   numbered identically.
2. **The `PRESERVE` transaction — the JSON sidecar.** A small, JSON-only op on the **direct,
   non-Counterparty substrate** (P2WSH data outputs, keyburn, **no `cpid`**) whose envelope
   carries `"stamp_tx": "<64 hex>"` referencing the content transaction. In `anchor` mode there
   is **no** content transaction and **no** `stamp_tx`.

This 2-tx model is chosen so that, on non-upgraded indexers, the **content survives** as a plain
stamp; only the small provenance sidecar is missed. A single-tx binary `SRC-ORD` was rejected
(the direct substrate is JSON-only and binary-unsafe; making it binary-capable means editing the
`#749`-protected shared extractor; and a `p:"SRC-ORD"` single tx is dropped outright by
non-upgraded indexers, losing the content). See `reference-implementation.md §4.3` for the full
code-grounded rationale.

**Rule-3 hashing binds to the wire, not the pipeline.** The §3.4 rule-3 integrity check hashes
the content stamp's **raw on-wire OLGA payload bytes** — the reassembled length-prefixed chunk
data (`chunk[2:2+len]`) minus the leading 6-byte `stamp:` marker — **not** post-pipeline content.
This sidesteps MIME normalization / svgz-decompression / the base64 / Python-3.13 decoder hazard
class (#803/#871) entirely.

### 3.4 Migration payload — protocol identity

- `p` (protocol identifier) is **`"SRC-ORD"`** (Open Question #9, resolved). It is registered
  **alongside** `SRC-20`/`SRC-721`/`SRC-101` in the protocol-detection path but routes to a
  **separate `PRESERVE` processor** and is **fully isolated from SRC-20 balance consensus**:
  because `is_src20()` gates on `ident == "SRC-20"`, a distinct `SRC-ORD` ident never enters
  `valid_src20()`, the `SRC20Valid` ledger, or `ledger_hash`.
- `op` is **`"PRESERVE"`** (Open Question #2, resolved).
- `PRESERVE` defines its **own** JSON validation and size limits (§4, the envelope grammar); it
  does **not** inherit SRC-20's tight string-length limits.

The exact envelope grammar (allowed keys, types, byte caps, canonical parse/validation
procedure) is **normative** and specified in **§4**.

### 3.5 Consensus validation rules

An indexer implementing this SIP MUST apply the following rules, **in order**, to a candidate
`PRESERVE` operation. **Every input to these rules MUST be derivable from Bitcoin chain data plus
this SIP alone.** A rule marked "→ drop" means: the `PRESERVE` op produces **no** Migration
Stamp, no stamp number, and no `stamp_migrations` row (§3.5 rule 7, corrected — there is no
ordinary-stamp fallback on the no-`cpid` sidecar substrate). The separate content transaction, if
any, is an ordinary OLGA stamp and is **unaffected** on every indexer.

1. **Well-formedness.** The envelope MUST parse under the §4 grammar and MUST contain `p`,
   `op == "PRESERVE"`, `mode ∈ {"full","anchor"}`, and a `src` object with `inscription_id`,
   `genesis_txid`, `content_sha256`, `content_type`, `content_length`. Any grammar violation
   (unknown key, wrong type, over the byte cap, duplicate key, etc. — §4) → **drop**.

2. **Inscription ID format.** `src.inscription_id` MUST match `^[0-9a-f]{64}i[0-9]+$` (lowercase
   hex genesis txid, literal `i`, non-negative decimal index). Purely syntactic; the indexer does
   **not** resolve the inscription. Mismatch → **drop**.

3. **Content hash (mode = `full`).** `src.content_sha256` MUST equal the SHA-256 of the content
   stamp's **raw on-wire OLGA payload bytes** (§3.3). Self-contained; requires no external data.
   Mismatch → **drop**. The referenced content stamp MUST be confirmed at a **lower**
   `(block_index, tx_index)` than the `PRESERVE` sidecar (same-block references resolve via the
   `valid_stamps_in_block` collection, the SRC-721 precedent).

4. **Content hash (mode = `anchor`).** There is **no** embedded content to check.
   `src.content_sha256` is recorded as an **unverified-at-consensus claim**; the indexer MUST set
   `content_verified = false`. Verification against the real inscription is possible **only** at
   the verification layer (§3.6). This `full`/`anchor` asymmetry MUST be surfaced to consumers, and
   per §3.6.2 an anchor record MUST NOT be presented as `canonical` or `verified`.

5. **Proof validation (v1.10 = Method B only).** For `proof.type == "utxo-spend"`: the
   `PRESERVE` transaction MUST spend, as one of its inputs, the UTXO named in `proof.utxo`
   (`"<txid>:<vout>"`). This is a **pure input-set match** — deterministic from the transaction's
   inputs. For `proof.type == "bip322"` (Method A): **deferred** — under v1.10 rules the op is
   **dropped** (unknown/out-of-scope proof type). The consensus layer does **NOT** verify that the
   address/UTXO actually held the inscription — that binding is an attestation (§3.6).

6. **Multiplicity.** Multiple `PRESERVE` ops referencing the same `src.inscription_id` are
   **allowed**; the indexer records **all** valid ones as immutable raw claim records. Uniqueness
   is deliberately **not** enforced (enforcing it creates griefing/front-running incentives).

   **No in-consensus canonicity (Option A).** The consensus layer does **NOT** designate a
   canonical claim — there is **no** in-consensus `canonical_flag`. Selecting which competing claim
   (if any) is "canonical" is a **verifier / frontend** determination made off consensus (§3.6.2),
   re-checkable against a live `ord` index and explicitly **mutable** over time. The indexer stores
   each claim's `(block_index, tx_index)` so that any off-consensus canonicity policy (e.g.
   first-valid, owner-designated) is reproducible from confirmed-chain order, but the indexer emits
   no canonicity verdict of its own. (The verifier-canonicity *policy* is the load-bearing open
   item; see §3.6.2 and §10.)

7. **No ordinary-stamp fallback for the sidecar (corrected).** A `PRESERVE` op that fails any of
   rules 1–6 is **dropped**, byte-identically to how a pre-activation (or non-upgraded) indexer
   handles the same transaction. Because the sidecar rides the no-`cpid` direct substrate (not a
   content-bearing stamp), there is **no** ordinary-stamp fallback for it. (This supersedes the
   earlier "fallback to ordinary stamp" wording in the #878 issue body, which predated the 2-tx
   model; the **content** transaction remains an ordinary stamp regardless.)

### 3.5.1 Spend attestation detail (Method B normative; Method A deferred)

The `proof` field records a **spend attestation**, not an ownership proof. At consensus the indexer
verifies only the **self-contained fact** that the `PRESERVE` transaction spent the named UTXO (a
pure input-set match, §3.5 rule 5). It does **not** — and cannot, without an external `ord` index —
verify that the spent UTXO actually held the source inscription. That binding is **not
consensus-authoritative**; it is checked off consensus by the verifier (§3.6), which can also
detect that it has since gone stale. Calling this an "ownership proof" would overclaim: it is a
one-time historical spend fact.

**Method B — UTXO spend (`proof.type == "utxo-spend"`).** The Stamp-creating transaction spends,
as one of its inputs, the UTXO holding the source inscription. Outputs MUST be constructed so the
inscribed sat returns to an owner-controlled output using standard `ord` postage handling.
Method B carries freshness **intrinsically**: a UTXO can only be spent by whoever controls it at
the moment of the spend, so no acceptance window applies (and MUST NOT be applied).

> **Implementer warning (normative-adjacent).** Naïve output construction can send the inscribed
> sat to fees, destroying the inscription. Implementations MUST follow standard `ord`
> sat-selection/postage rules. This SIP does not redefine sat tracking.

**Method A — BIP-322 signature (`proof.type == "bip322"`) — DEFERRED.** The creator signs the
canonical ASCII message

```
PRESERVE|<inscription_id>|<content_sha256>|<stamper_address>|<block_target>
```

(fields verbatim: `src.inscription_id`, `src.content_sha256`, `proof.address`, `proof.msg_block`
as decimal). Method A has no intrinsic freshness, so it requires an acceptance window
`0 ≤ (confirmation_height − msg_block) ≤ N` (proposed **N = 144**), with a future-dated
`msg_block` (negative delta) invalid. `TODO(ratify)`: N (Open Question #5). Method A ships in a
follow-up SIP, not v1.10.

### 3.6 Verification architecture (Option 2 RECOMMENDED / adopted for v1.10)

- **Option 1 — Full consensus verification.** Indexer embeds an `ord`-equivalent tracker.
  Rejected: enormous cost and consensus-divergence risk (a Stamps↔ord disagreement becomes a
  Stamps consensus bug).
- **Option 2 — Two-tier (ADOPTED).** The **consensus layer** validates only self-contained facts
  (well-formedness, `full`-mode content-hash match, and the *fact* of the claimed UTXO spend).
  The **binding of address/UTXO to the inscription** is recorded as an **attestation**, checked by
  a separate open-source **verifier** (#880) that exposes `verified: true|false`. The verifier
  MUST ship **alongside** the indexer change. Marketplaces/wallets display badges sourced from the
  verifier, never from the indexer.
- **Option 3 — Pure attestation.** No proof field. Rejected as too weak.

The consensus layer never emits `verified`, never emits `canonical_flag`, and never emits any
`provenance_state`. It emits exactly two things: `content_verified` (the self-contained full-mode
hash result, §5) and the immutable raw claim record. **Everything else — `provenance_state`,
`canonicity`, `attestation`, competing-claim resolution, and the "verified" badge — is owned by
the verifier + frontend, off consensus** (§3.6.1, §3.6.2).

### 3.6.1 Frontend ⇄ verifier UX contract (normative for the app; non-consensus)

This section is **normative for the application** — the verifier and any frontend/marketplace
consuming it — and **non-consensus**: nothing here affects indexer determinism. Frontend
implementation guidance: see [`FRONTEND-IMPLEMENTATION.md`](./FRONTEND-IMPLEMENTATION.md). The
straw-man endpoint the stampchain.io frontend is building against (to be finalized with the
verifier/frontend teams):

```
GET {verifier}/provenance/{stamp_id}
{
  "content_verified":  bool,        // mirrored from the indexer for convenience (the only consensus bit)
  "provenance_state":  "verified" | "unverified" | "disputed" | "unverifiable",
  "canonicity":        "canonical" | "superseded" | "contested" | null,
  "attestation":       "owner_attested" | "unilateral" | null,
  "source_inscription_url": "<link-out to the original inscription>",   // MANDATORY
  "competing_claims":  [ ... ],     // populated for "disputed"
  "verifier":          { ...attester identity + timestamp... },
  "ttl_seconds":       <cache model>
}
```

Trust taxonomy and UI rules (normative for the app):

- **Badges are verifier-sourced, never indexer-sourced.** A frontend MUST NOT synthesize a
  "verified"/"canonical" badge from indexer data. The indexer emits only `content_verified` and the
  raw claim; everything else is a live verifier determination.
- **`verified` vs. `unverified`.** `provenance_state == "verified"` requires the verifier to
  confirm — against a live `ord` index — that the attested UTXO/address actually held the source
  inscription. This is **mutable**: a state that verifies today MAY become `unverified`/`disputed`
  later; consumers MUST re-check and MUST NOT cache it as permanent.
- **`full` vs. `anchor`.** The frontend MUST surface the mode distinction. A `full` record has
  on-chain content the indexer byte-verified (`content_verified == true`); an `anchor` record has
  only a hash claim (`content_verified == false`) — see §3.6.2 for its canonicity floor.
- **Graceful degradation.** When the verifier is unavailable, the frontend MUST degrade to
  `unverified` (never fabricate `verified`) and MAY still show `content_verified` (the indexer bit)
  with clear "content byte-hash only; provenance unchecked" labelling.
- **Mandatory link-out.** Every provenance display MUST link out to the original inscription
  (`source_inscription_url`) so a viewer can see the source and its creator. This is non-negotiable
  (attribution; §3.9).
- **Competing claims.** For `provenance_state == "disputed"`, the frontend MUST show the competing
  claims rather than silently picking one.

### 3.6.2 Verifier canonicity policy (off consensus)

Because canonicity is off consensus, choosing which of several competing claims for one inscription
is `canonical` is a **verifier policy**, not a consensus rule. The recommended policy (see the §10
open item) is **owner-designated / current-owner-wins / explicitly mutable** — the honest model the
word "provenance" implies: canonicity MAY flip when the inscription legitimately changes hands. The
verifier MUST document its policy and SHOULD make it reproducible across operators from
chain-derivable inputs (each claim's `(block_index, tx_index)`, plus live `ord` ownership state).

**Anchor-mode floor (Open Question #12 — RESOLVED).** An `anchor` record (no on-chain content,
`content_verified == false`) MUST render `provenance_state != "verified"` and MUST NOT be presented
as `canonical` by any verifier or frontend. An unverifiable claim can never outrank a byte-verified
`full` claim for the same inscription. This is a verifier/frontend rule; at consensus the indexer
simply records the anchor claim with `content_verified = false`.

### 3.7 Encoding (RESOLVED — direct, non-Counterparty transaction)

`PRESERVE` rides a **direct, non-Counterparty transaction** — the modern SRC-20-style substrate
(P2WSH data outputs, keyburn, **no `cpid`**). This SIP defines no new *data* encoding: `full`-mode
content uses the **existing OLGA P2WSH encoding**. The Counterparty/SRC-721 route was rejected
(it carries a Counterparty consensus dependency; `PRESERVE` mirrors the modern direct SRC-20
substrate instead). Because modern SRC-20 is JSON-only, `full`-mode `PRESERVE` is **new
plumbing**: a new `preserve.py` processor (mirroring `Src20Processor`) and a new `stamp_migrations`
table (§6) that stores the immutable raw claim records and their `content_verified` bit. Under
Option A, `PRESERVE` records are **not** folded into any dedicated consensus-hash stream — there is
no `migration_hash` (§5) — and **never** into `ledger_hash` (which is SRC-20-specific).

### 3.8 Edge-case handling (normative)

1. **Reinscriptions.** A migration references an inscription **ID**, not a sat. Distinct IDs
   migrate independently (TV-09).
2. **Delegates / pointers / recursive inscriptions.** `content_sha256` covers the **envelope
   content bytes of the referenced inscription ID only**. Recursive content will not render
   standalone from the Stamp copy — documented limitation. An optional informational `deps` array
   MAY list referenced IDs. `TODO(ratify)`: `deps` normativity (Open Question #7) — recommended
   **informational** in v1.
3. **Cursed inscriptions / negative numbers.** IDs still match the rule-2 regex; **no** special
   handling (TV-09).
4. **Inscription moved between signature and confirmation (Method A only).** Bounded by the
   acceptance window (§3.5.1); moot for Method B.
5. **Inscription sold; previous owner replays an old signature (Method A only).** Bounded by the
   window; structurally impossible under Method B (a sold UTXO is unspendable by the seller).
6. **Content larger than the OLGA cap.** `full`-mode content MUST NOT exceed
   `PRESERVE_MAX_FULL_CONTENT_BYTES = 65535` (§4.4). Above the cap, only `anchor` mode is
   permitted; an over-cap `full` op is **dropped** (TV-10).
7. **Hash mismatch in `full` mode.** Dropped (rule 3; TV-04).
8. **Same inscription migrated by two different owners over time.** Allowed; both retained as raw
   claims. Which (if either) is `canonical` is a **verifier** determination (§3.6.2, off
   consensus), not a consensus flag; the recommended policy is current-owner-wins/mutable (§10).

### 3.9 Inscription-creator consent, attribution & link-out (position)

Even though creator consent is "out of consensus scope," this SIP cannot be silent on it. The
content-preservation mechanic copies an inscription's bytes onto the UTXO set; the original creator
may not have consented. Option A's position:

- **Mandatory attribution / link-out.** Every provenance display MUST link out to the original
  inscription and its creator (§3.6.1). Preservation presents as "a preserved copy of `<source>`,"
  never as an original or a replacement.
- **No tokenization of the provenance claim.** The frontend does not mint or DEX-list a
  "the-canonical" provenance asset; there is no in-consensus canonical asset to trade. (A preserved
  `full`-mode content stamp is an ordinary OLGA stamp and MAY be traded like any stamp; the
  financialization-values question about *that* is a community call — §10.)
- **Takedown / attribution requests.** The consensus record is immutable and permissionless (it
  cannot be redacted on-chain), but the **verifier + frontend** SHOULD honor a documented
  creator-attribution / takedown-from-display process (e.g. suppressing or annotating a disputed
  claim in the verifier's `provenance_state`), and MUST clearly attribute the source creator.
- **Unilateral vs. owner-attested.** The verifier's `attestation` field (§3.6.1) distinguishes an
  `owner_attested` claim from a `unilateral` one; a unilateral claim over someone else's
  inscription MUST NOT render as `verified` or `canonical`.

This, together with the spend attestation being explicitly *not* an ownership proof (§3.5.1), is
the main blunting of the "an ordinals artist's work is captured without consent" objection.

---

## 4. Envelope JSON grammar (normative — resolves review blocker G8)

Two conformant indexers MUST be able to agree on **accept vs. drop** for any candidate envelope
**from this section alone**, with no reference to external state. This mirrors how
`src20.py :: check_format()` constrains SRC-20. Any violation of any MUST below → the op is
**dropped** (§3.5 rule 1); there is **no** partial acceptance and **no** repair/coercion.

### 4.1 Byte source and size cap

- The envelope is the JSON document reassembled from the direct-substrate P2WSH data outputs
  (after stripping the `config.PREFIX = b"stamp:"` marker), decoded as **UTF-8**. A UTF-8 decode
  error → **drop**.
- Let `envelope_bytes` be the exact reassembled byte string **before** JSON parsing. It MUST
  satisfy `len(envelope_bytes) ≤ PRESERVE_MAX_ENVELOPE_BYTES`. Over the cap → **drop**. The cap is
  measured on the **raw on-wire bytes**, not on any re-serialization, so it is independent of any
  parser's whitespace handling.
- **`PRESERVE_MAX_ENVELOPE_BYTES = 4096`.** Rationale: the largest v1.10 envelope (Method B) is a
  fixed set of short fields — two 64-hex hashes, a 66-char inscription ID, a `"<txid>:<vout>"`
  UTXO string, a MIME string, an address, and small scalars — comfortably under 1 KB; 4096 leaves
  headroom for a bounded MIME/address and the optional `deps` array while staying far below any
  standardness limit. `TODO(ratify)`: confirm 4096 during the testnet campaign; if Method A
  (BIP-322, ~larger signature) is later folded in, this cap MUST be revisited in that SIP (a
  base64 BIP-322 signature can be several hundred bytes but still fits 4096).

### 4.2 Parse procedure (canonical, deterministic)

1. UTF-8-decode `envelope_bytes`; on error → **drop**.
2. Parse as JSON with a parser that:
   - **Rejects duplicate keys** anywhere in the document. A JSON object containing the same key
     twice → **drop**. (Do **not** use a last-wins/first-wins silent policy; duplicate keys are a
     cross-parser divergence hazard and MUST be a hard reject. Implementations MUST use an
     object-pairs hook that detects duplicates, e.g. `json.loads(..., object_pairs_hook=...)`
     raising on a repeated key.)
   - **Rejects any number in scientific notation** and any non-integer where an integer is
     required (mirror `src20.py`'s `parse_no_sci_float`). All numeric fields in this grammar are
     **non-negative integers**; a value containing `.`, `e`, `E`, a leading `+`, or a leading zero
     (other than the single digit `0`) → **drop**.
   - Treats the top level as a JSON **object**; a non-object top level → **drop**.
3. Validate the object against §4.3 (keys, types, values). Any failure → **drop**.

**Key case is significant and fixed.** All keys are **exact lowercase ASCII** as written in §4.3.
`"P"`, `"Op"`, `"Mode"`, etc. → **drop**. (Contrast: SRC-20 lowercases `p` for routing; PRESERVE
does **not** — routing already happened via the `p == "SRC-ORD"` gate, and within the envelope the
grammar is case-exact to eliminate ambiguity.) String **values** are case-sensitive except where
§4.3 says otherwise (`inscription_id`/`genesis_txid`/`content_sha256` are required lowercase hex).

### 4.3 Allowed keys and types

The top-level object MUST contain **exactly** these keys — no unknown/extra top-level keys are
permitted (unknown top-level key → **drop**):

| key       | required | type            | constraint |
|-----------|----------|-----------------|------------|
| `p`       | yes      | string          | exactly `"SRC-ORD"` |
| `op`      | yes      | string          | exactly `"PRESERVE"` |
| `mode`    | yes      | string          | `"full"` or `"anchor"` |
| `stamp_tx`| iff `mode=="full"` | string | `^[0-9a-f]{64}$`; MUST be **absent** when `mode=="anchor"` |
| `src`     | yes      | object          | see below |
| `proof`   | yes      | object          | see below |
| `deps`    | no       | array of string | each item matches `^[0-9a-f]{64}i[0-9]+$`; informational (§3.8.2) |

`src` object — MUST contain **exactly** these keys:

| key              | type    | constraint |
|------------------|---------|------------|
| `inscription_id` | string  | `^[0-9a-f]{64}i[0-9]+$` (§3.5 rule 2) |
| `genesis_txid`   | string  | `^[0-9a-f]{64}$` |
| `content_sha256` | string  | `^[0-9a-f]{64}$` |
| `content_type`   | string  | 1–255 bytes; printable ASCII (`0x20`–`0x7E`); no CR/LF |
| `content_length` | integer | `0 ≤ n ≤ PRESERVE_MAX_FULL_CONTENT_BYTES` in `full`; `0 ≤ n` in `anchor` |

`proof` object — v1.10 (`proof.type == "utxo-spend"`) MUST contain **exactly**:

| key       | type   | constraint |
|-----------|--------|------------|
| `type`    | string | exactly `"utxo-spend"` (v1.10). `"bip322"` → **drop** (Method A deferred) |
| `address` | string | 1–90 bytes; printable ASCII; informational at consensus (the spend, not the address, is the proof) |
| `utxo`    | string | `^[0-9a-f]{64}:(0|[1-9][0-9]*)$` — the claimed `"<txid>:<vout>"` (§3.5 rule 5) |

> `TODO(ratify)`: the Method A (`bip322`) `proof` shape (`type`,`address`,`signature`,`msg_block`)
> is defined in §3.5.1 for the follow-up SIP but is **out of grammar** for v1.10 (any `bip322`
> envelope is dropped). When Method A lands, this table gains a `bip322` variant and the duplicate
> address-vs-signature rules must be pinned there.

### 4.4 Size constants

- **`PRESERVE_MAX_FULL_CONTENT_BYTES = 65535`** (Open Question #8, resolved). This is
  **structural**: the OLGA payload's 2-byte big-endian length prefix hard-caps the payload at
  65,535 bytes. Effective media size is **65,529 bytes** after the 6-byte `stamp:` prefix. Because
  stamp data has no witness discount, witness-scale (~4 MB) content is not reachable here.
- **`PRESERVE_MAX_ENVELOPE_BYTES = 4096`** (§4.1). `TODO(ratify)`.

Both SHOULD be codified in `config.py` at implementation time. **Follow-up (not done in this
docs-only PR):** add `PRESERVE_MAX_FULL_CONTENT_BYTES = 65535` and `PRESERVE_MAX_ENVELOPE_BYTES =
4096` to `indexer/src/config.py` near `SUPPORTED_SUB_PROTOCOLS` (line ~416), and extend
`SUPPORTED_SUB_PROTOCOLS` / the `get_src_or_img_from_data()` gate to accept `SRC-ORD` — these
touch consensus-adjacent files and are deferred to the implementation PR.

---

## 5. No dedicated consensus-hash stream (Option A)

**There is no `migration_hash`.** The earlier draft folded PRESERVE records into a dedicated fourth
per-block consensus hash whose entire justification was carrying the in-consensus `canonical_flag`
(and a consensus `verified`). Under Option A both are gone — canonicity and verification live off
consensus in the verifier (§3.6) — so the dedicated stream is **removed** (Open Question #10,
resolved by removal).

The indexer's consensus surface for `PRESERVE` is therefore minimal:

- **Parse + store** the immutable raw `p:"SRC-ORD"` claim record (§3.4, §4), and
- **Compute `content_verified`** — the full-mode byte-hash of §3.5 rule 3 (does the declared
  `content_sha256` match the referenced content stamp's raw on-wire OLGA payload bytes). This is
  the **only** consensus-emitted verification bit.

Both are **deterministically derivable from Bitcoin chain data + this SIP alone**, so any two
conformant indexers compute identical values. Note that the `PRESERVE` sidecar is itself a stamp
and already flows through **`txlist_hash`** as an ordinary stamp (§8) — the existence and numbering
of the claim are covered there; no PRESERVE-specific hash stream is added on top. Neither
`content_verified` nor the raw claim is folded into `ledger_hash`
(`str(processed_src20_in_block)`, SRC-20-only) or `messages_hash`; both remain **byte-identical**
with and without SIP-0110 enabled — the isolation property (§8, TV-15).

Because no PRESERVE-specific hash stream is emitted, the earlier anti-`str()`/`repr()` serialization
guidance (a canonical, Python-version-invariant record encoding for the removed stream) is **no
longer needed** and is dropped with the stream. If a future SIP ever reintroduces per-block hashing
of the raw claim record, that guidance MUST be restored there: never use `str()`/`repr()` of a
dict/list/`Decimal`/object as a consensus serialization — insertion order, `Decimal`-vs-`int`
`repr`, and cross-version container formatting all diverge (the #803/#871 hazard class).

---

## 6. `stamp_migrations` schema (normative derivation; table is indexer-internal)

Modeled on `StampTableV4` (`config.STAMP_TABLE`) and `SRC20Valid`. The table stores the **immutable
raw PRESERVE claim records** and their consensus-derived `content_verified` bit. It is
indexer-internal, but those contents **derive from the consensus rules of §3.5**, so two conformant
indexers MUST produce identical raw claims and identical `content_verified` for the same chain. It
stores **no** `canonical_flag` — canonicity is not an indexer field under Option A (§3.6.2).

```
stamp_migrations(
  stamp_id          <FK to StampTableV4.stamp>,  -- PRIMARY KEY (the PRESERVE sidecar's stamp)
  stamp_tx          TEXT,     -- full mode: txid of the referenced content stamp (§3.3); NULL in anchor
  inscription_id    TEXT,     -- INDEXED
  genesis_txid      TEXT,
  content_sha256    TEXT,
  mode              TEXT,     -- 'full' | 'anchor'
  proof_type        TEXT,     -- 'utxo-spend' (v1.10); 'bip322' reserved for the follow-up SIP
  proof_address     TEXT,
  proof_utxo        TEXT,     -- Method B: the claimed "<txid>:<vout>" (§3.5 rule 5)
  proof_block       INTEGER,  -- spend height (Method B) / msg_block (Method A, deferred)
  content_verified  BOOLEAN,  -- consensus byte-hash check: true only for a passing full-mode op
  block_index       INTEGER,  -- INDEXED (needed for the reorg purge, §6.1)
  tx_index          INTEGER,  -- in-block position; lets a verifier reproduce any chain-order canonicity policy (§3.6.2)
  block_time        <timestamp>
)
```

There is **no** `canonical_flag` column — canonicity is a verifier determination off consensus
(§3.6.2). `tx_index` is retained only so the verifier can reproduce a chain-order canonicity policy
from the raw claims; the indexer itself computes no canonicity verdict.

Indexes: PK on `stamp_id`; secondary index on `inscription_id` (the `GET /migrations/{id}` path);
`block_index` indexed for the reorg purge.

### 6.1 Reorg safety (indexer-internal bookkeeping)

**`stamp_migrations` MUST still be added to the table list purged by `purge_block_db`**
(`indexer/src/index_core/database.py`, the `tables = [...]` list at ~line 1199, alongside
`STAMP_TABLE`, `SRC20_VALID_TABLE`, etc.). The purge deletes `WHERE block_index >= %s`, which is
exactly why `stamp_migrations.block_index` must be a real, indexed column. Under Option A this is
**indexer-internal bookkeeping for reorg correctness, not a consensus-hash requirement** — there is
no `migration_hash` to keep in sync (§5).

If `stamp_migrations` is **omitted** from `purge_block_db`, a reorg leaves **stale raw-claim rows**
behind; after re-derivation on the new chain the stored claims and their `content_verified` values
no longer match what the canonical chain implies, so the indexer (and the verifier that mirrors
`content_verified` and reads the raw claims) would serve wrong data. This MUST be covered by a
reorg regression test. (Follow-up: the `purge_block_db` edit and the `CREATE TABLE` migration are
implementation-PR changes.)

---

## 7. Security Considerations (normative summary; full text in #878)

1. **Forged ownership claims.** Under Option 2 consensus accepts a well-formed op, but the
   verifier rejects the false binding **forever**; the attacker gains nothing durable and leaves
   permanent public evidence.
2. **Signature replay (Method A).** The canonical message binds inscription/content/address/block;
   the acceptance window bounds staleness. Moot for Method B.
3. **Content sniping (single tx).** Not claimed to be resisted; optional commit/reveal deferred
   (Open Question #3).
4. **Griefing via duplicates.** Resolved structurally by non-uniqueness (§3.5 rule 6).
5. **Indexer divergence.** All consensus inputs derive from Bitcoin chain data + this SIP alone;
   this is why Option 1 is rejected and Method A/BIP-322 is deferred.
6. **UTXO-set footprint & political blast radius.** PRESERVE bridges Ordinals content onto the
   UTXO set; a mass-migration wave is a real (pre-acknowledged) policy-surface cost. Keep `full`
   mode economically self-limiting; prefer `anchor` for large content.
7. **Anchor-mode false hashes.** Unverifiable at consensus; consumers MUST treat them as claims,
   and per §3.6.2 an anchor record MUST NOT render as `verified` or `canonical`.
8. **Creator consent / unauthorized preservation.** Not a consensus control, but blunted off
   consensus: mandatory attribution + link-out, no tokenized "canonical" asset, and a verifier
   `attestation` distinction (`owner_attested` vs. `unilateral`) — a unilateral claim over someone
   else's inscription never renders `verified`/`canonical` (§3.9, §3.6.2).

---

## 8. Activation & backward compatibility (normative)

- **Activation block:** TBD, fixed when this SIP is marked **Accepted** (≥ 4 weeks lead time per
  SIP-0000).
- **SIP-0110 is an activation-gated consensus change, not "purely additive metadata."** A valid
  `PRESERVE` sidecar is itself assigned a stamp number and enters `txlist_hash` (via the sorted
  `valid_stamps_in_block`). Post-activation, upgraded and non-upgraded indexers therefore
  **diverge on numbering and `txlist_hash`** — the normal consequence of any new stamp-creating
  op, and exactly why a coordinated activation height that all participating indexers ship before
  is required. A non-upgraded indexer **drops** a `p:"SRC-ORD"` sidecar outright
  (`raise ValueError("invalid p")`) — fail-**safe**, not "indexed as an ordinary stamp." Under the
  2-tx model the **content** transaction is a plain OLGA stamp, preserved and numbered identically
  on every indexer.
- **Isolation invariant (MUST hold on every vector block):** `ledger_hash`
  (`str(processed_src20_in_block)`, SRC-20-only) and `messages_hash` are byte-identical with and
  without SIP-0110 enabled. A full genesis→tip reparse proving byte-identical **pre-activation**
  hashes (via `validate_block_against_reference`) is required before activation.
- **Multi-indexer acceptance:** requires the stampchain reference indexer **plus at least one
  independent indexer** (e.g. OpenStamp / stampscan) to validate the shared test vectors, per
  SIP-0000 §6.1.3.
- **Verifier co-delivery:** the #880 verifier + stampchain verification API MUST ship
  **alongside** the indexer change.
- **SIP-0005 interaction:** if SIP-0005 (binary format) has not activated, the payload is JSON in
  the OLGA envelope; if it activates first, a binary op-code SHOULD be reserved (Open Question #6).

---

## 9. API surface (non-normative)

- `GET /migrations/{inscription_id}` — all raw migration claim records for an inscription ID (there
  may be several; §3.5 rule 6), each with its `content_verified` bit and `(block_index, tx_index)`.
  **No `canonical_flag`** — canonicity is not an indexer field (§3.6.2).
- `GET /stamps/{id}/provenance` — the raw claim record for a Migration Stamp (in `full` mode,
  including the referenced content stamp's `stamp_tx`).
- **`provenance_state` / `canonicity` / `verified` are served by the external verifier (#880)** via
  the `GET {verifier}/provenance/{stamp_id}` contract (§3.6.1), **never** by the indexer.

---

## 10. Resolved decisions & open ratification ledger

### 10.1 Resolved (design decisions — not open)

| # | Decision |
|---|----------|
| — | **SIP number = SIP-0110** (deliberate BIP-110 thematic mirror; 0012–0109 stay available) |
| #2 | **Op keyword = `PRESERVE`** |
| #8 | **`PRESERVE_MAX_FULL_CONTENT_BYTES = 65535`** (structural: 2-byte OLGA length prefix; 65,529 effective after the `stamp:` prefix) |
| #9 | **`p = "SRC-ORD"`**, registered alongside SRC-20/721/101 but routed to a separate PRESERVE processor, fully isolated from SRC-20 balance consensus |
| #11 | **BIP-110 34-byte boundary resolved favorably** — the cap measures the **scriptPubKey** and is **inclusive (≤ 34)**; a P2WSH scriptPubKey is exactly 34 bytes, so new OLGA stamps remain creatable. Pinned to current `bip-0110.mediawiki`; exact upstream revision MUST be recorded at Accepted. |
| — | **Encoding = direct, non-Counterparty transaction** for the envelope (§3.7); 2-tx reference model (§3.3) |
| — | **v1.10 scope = `full` + `anchor`, Method B only** (Method A/BIP-322 deferred) |
| #1 | **Verification architecture = Option 2 (two-tier)** adopted; under **Option A** all provenance/canonicity/`verified` moves to the verifier + frontend, off consensus (§3.6) |
| #10 | **No dedicated consensus-hash stream (Option A).** The `migration_hash` fourth stream is **removed from consensus** — its only purpose was carrying the in-consensus `canonical_flag`/`verified`, both now off consensus. Consensus emits only the raw claim + `content_verified` (§5). |
| #4, #12 | **Canonicity removed from consensus (Option A).** The in-consensus `canonical_flag` (multi-owner canonicity, #4) and the anchor-mode canonical gate (#12) are **resolved by removal**: canonicity is a verifier policy (§3.6.2). An anchor record MUST NOT render as `canonical`/`verified`. The *verifier* canonicity policy remains an open (non-consensus) item — see §10.2. |

### 10.2 Open — `TODO(ratify)` before Accepted

| # | Item | Trade-off / recommendation |
|---|------|----------------------------|
| **VERIFIER-CANONICITY** | **Off-consensus canonicity policy — the load-bearing remaining design choice.** With `canonical_flag` gone from consensus, how does the verifier pick `canonical` among competing claims for one inscription — first-valid / attestation-weighted / owner-designated? Must it be reproducible across verifier operators, and may it flip over time? | Recommendation: **owner-designated, current-owner-wins, explicitly mutable** — the honest model "provenance" implies (re-check live ownership rather than freeze a one-time claim). The verifier documents its policy and makes it reproducible from chain-derivable inputs (§3.6.2). This is a **verifier/frontend** decision, not consensus. |
| **DEMAND-GATE (go/no-go)** | **Do not build past the "optionally parse a metadata op" MVP until:** (a) **≥ 2 non-trivial teams** — at least one each from the Stamps and Ordinals sides — publicly commit to run the off-chain verifier + a frontend, **and** (b) **> 500 distinct-creator provenance attestations within 60 days** of a test deployment. | Concrete, testable gate (Grok). Anything weaker is "just another unused metadata field." Adopt into the PRD (§6-equivalent scope discipline). |
| **COMMUNITY-VALUES** | **Financialization objection** — "plain stamps shouldn't be financialized in the Counterparty sense." Option A reduces it (no in-consensus canonical asset; the frontend doesn't tokenize) but does not eliminate it if a preserved content-stamp is ever DEX-listed. | Not engineerable; a Stamps-community values call. **Surface to community reviewers** before Accepted, do not engineer around it. |
| **CONSENT** | **Inscription-creator consent / attribution / takedown position** (§3.9). | With the mandatory link-out, this is the main blunting of the ordinals-artist attack; the spec cannot be silent. |
| #4-adjacent | `PRESERVE_MAX_ENVELOPE_BYTES = 4096` (§4.1) | Confirm during the testnet campaign; revisit if Method A/BIP-322 (larger signature) is folded in. |
| #5 | **Method A acceptance window `N`** (deferred with Method A) | Proposed **N = 144** (~24h). Defers to the follow-up SIP. |
| #6 | **SIP-0005 binary op-code** | Reserve one of `0x13`–`0x15`; define JSON normatively now, binary form conditional. |
| #7 | **`deps` normativity** | Recommendation: **informational** in v1. |
| #3 | **Commit/reveal** | Recommendation: **defer** to a follow-up SIP. |

> **Note (Option A).** Open Questions **#4** (multi-owner canonicity), **#10** (`migration_hash`
> serialization form), and **#12** (anchor-mode canonical-flag semantics) are **no longer
> consensus ratification items** — canonicity and verification left consensus entirely (§10.1).
> #4/#12 survive only as the **VERIFIER-CANONICITY** policy question above (off consensus); #10 is
> closed with the stream.

### 10.3 External (non-doc) pre-coding blockers

These are outside this repo's docs and cannot be closed by specification alone:

1. **Activation-height coordination** — a concrete activation block, fixed at Accepted, with ≥ 4
   weeks lead time, shipped by all participating indexers before it.
2. **Cross-indexer sign-on** — at least one independent indexer (OpenStamp / stampscan) validates
   the frozen shared test vectors. Under Option A the consensus surface is only the raw-claim parse
   + `content_verified` (§5), so these vectors are much lighter than before (no `migration_hash`
   serialization or in-consensus canonicity to pin). Cross-**verifier** reproducibility of the
   canonicity policy is a separate, off-consensus agreement (§3.6.2, §10.2).
3. **Verifier (#880) co-delivery** — the open-source verifier + stampchain verification API must
   be ready to ship alongside the indexer change (Option 2 requirement).

---

*Supporting (non-normative): [`reference-implementation.md`](./reference-implementation.md),
[`test-vectors.md`](./test-vectors.md). Historical Motivation / BIP-110 framing: issue #878.*
