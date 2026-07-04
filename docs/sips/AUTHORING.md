# SIP Authoring Guide

> **Companion to [SIP-0000](https://github.com/stampchain-io/btc_stamps/issues/686) (the SIP
> process).** SIP-0000 defines the *process* (lifecycle, numbering, review, coordination). This
> guide gives authors the reusable **templates, checklists, and terminology rules** to write a SIP
> that passes review the first time. When the two disagree, SIP-0000 is authoritative.

**Audience:** anyone drafting a Stamps Improvement Proposal.
**TL;DR:** copy the [SIP template](#1-sip-template), fill every section, run the
[pre-submission checklist](#7-pre-submission-checklist), and obey the
[terminology guide](#6-terminology-guide) (Stamps are **not** inscriptions).

---

## Contents

1. [SIP template (full section-by-section)](#1-sip-template)
2. [Section guidance](#2-section-guidance)
3. [Security Considerations checklist](#3-security-considerations-checklist)
4. [Cross-indexer coordination requirements](#4-cross-indexer-coordination-requirements)
5. [Activation template](#5-activation-template)
6. [Terminology guide](#6-terminology-guide)
7. [Pre-submission checklist](#7-pre-submission-checklist)
8. [Large SIPs: the SIP-0110 split pattern](#8-large-sips-the-sip-0110-split-pattern)

---

## 1. SIP template

Copy this verbatim into a new GitHub issue. Every section is required unless marked *(optional)*.
This mirrors the format in SIP-0000 and adds the sections review has repeatedly needed.

```markdown
# SIP-XXXX: Title

**Status**: Draft
**Author**: GitHub username(s) / contact
**Type**: Standards Track | Informational | Process
**Created**: YYYY-MM-DD
**Requires**: SIPs or dependencies this needs (or "none — self-contained")
**Supersedes**: SIPs this replaces (optional)
**Related**: Related issues/SIPs

---

## Abstract
One paragraph. What does this change, and what does it enable? A reader should understand the
proposal from this paragraph alone.

## Motivation
The problem being solved and why it needs a *consensus-level* change (vs. an indexer-only fix or
an API feature — see SIP-0000's "What Qualifies as a SIP"). Include concrete use cases.

## Specification
The normative, precise technical spec. This is the part indexers implement against. Cover:
- New / modified operations, JSON fields (or binary layout) with **types and validation rules**
- Indexer behavior: balance handling, state transitions, ordering, determinism requirements
- Exact encoding (bare-multisig / OLGA P2WSH / prefix bytes) where relevant
- Backward-compatibility analysis (what existing stamps/tokens do under the new rules)

## Rationale
Why this design over the alternatives you considered. Record rejected approaches and why — this
saves reviewers from re-litigating settled questions.

## Use Cases
Concrete, worked examples of what the change enables.

## Security Considerations
Attack vectors, mitigations, and residual risk. **Mandatory** — see the checklist in
docs/sips/AUTHORING.md §3. A SIP with an empty or hand-wave Security Considerations section is
not review-ready.

## Test Vectors
JSON (or binary) test cases covering valid inputs, invalid inputs, and edge cases, each stating
the expected consensus-layer outcome. Illustrative vectors are fine for Draft; an **Accepted**
SIP MUST ship concrete testnet vectors (SIP-0000).

## Cross-Indexer Coordination
Which indexers must implement this, the shared test-vector set, and the activation-coordination
plan. See §4.

## Activation
Activation block height (TBD until Accepted), minimum lead time, and fail-safe behavior for
non-upgraded indexers. See §5.

## Open Questions
Unresolved design decisions for community input.
```

---

## 2. Section guidance

- **Abstract before Motivation.** Reviewers triage dozens of proposals; the abstract is your
  elevator pitch. Keep it to one dense paragraph.
- **Specification is normative; everything else is context.** Write the Specification so a second
  indexer team could implement it *without talking to you*. Ambiguity here is the #1 cause of
  cross-indexer divergence.
- **Determinism is a hard requirement.** Every field an indexer writes MUST derive solely from
  Bitcoin chain data and the rules in your Specification. No dependence on external indexes,
  wall-clock time, or non-deterministic ordering. State this explicitly (SIP-0110 §4.2 is a good
  model).
- **Backward compatibility is not optional prose.** Say precisely what happens to existing
  stamps/tokens, and what a non-upgraded indexer does when it sees the new operation.
- **Rationale prevents re-litigation.** SIP-0002 (#484) was superseded partly because its
  loss-risk rationale was under-argued; record your rejected alternatives.

---

## 3. Security Considerations checklist

A SIP is not review-ready until each item is either addressed or explicitly marked N/A **with a
reason**. Copy this into the SIP or answer it in the review thread.

- [ ] **Consensus divergence.** Can two correct indexers reach different state from the same
      chain data? If yes, the spec is under-determined — fix it. (No dependence on external
      indexes, floats, map iteration order, or timestamps.)
- [ ] **Fund/balance loss.** Can a user lose tokens or a stamp through normal wallet behavior
      (e.g., spending a UTXO)? UTXO-binding designs are historically rejected for this reason
      (SIP-0002).
- [ ] **Replay / double-spend of the operation.** Can the same op be counted twice, or replayed
      after a reorg?
- [ ] **Reorg behavior.** What happens to state written by this op if its block is reorged out?
      Is re-derivation clean?
- [ ] **Ordering / MEV.** Does within-block or cross-tx ordering affect outcome? Can a miner or
      indexer exploit ordering? State the deterministic ordering rule and any required slippage /
      guard parameters.
- [ ] **Griefing / DoS.** Can a cheap transaction force expensive indexer work, unbounded state
      growth, or lock another party's funds (timelock griefing, dust pools)?
- [ ] **Input validation.** Every new field has an explicit type, range, and length bound.
      Malformed input has a defined outcome (reject vs. ignore) — never undefined behavior.
- [ ] **Cryptographic assumptions.** If the SIP uses hashes/signatures/commitments, state the
      algorithm, what is signed, and what an attacker gains by forging it. Distinguish
      consensus-verified facts from unverified claims.
- [ ] **Cross-protocol interaction.** Interactions with Ordinals, runes, other SIPs, or
      dual-payload transactions (SIP-0008) that could change classification or ownership.
- [ ] **Fail-safe direction.** When an indexer is confused or un-upgraded, does it **fail safe**
      (ignore, do not debit) rather than **fail open** (guess and diverge)? State this explicitly.
- [ ] **Economic / fee-market impact.** Does the change materially alter minting cost, block
      space demand, or create a new fee-driven incentive? Disclose it.

---

## 4. Cross-indexer coordination requirements

Bitcoin Stamps has **no on-chain consensus** — protocol rules are whatever the indexers agree to
enforce. A consensus-changing SIP therefore lives or dies on cross-indexer coordination.

**Requirements for a SIP to reach `Accepted`:**

1. **At least two independent indexers.** The reference indexer (**stampchain**) plus **≥1 other**
   (e.g., OpenStamp) must review and agree the specification is implementable. stampchain alone is
   not sufficient for Accepted status.
2. **Shared test vectors.** A single canonical set of test vectors (valid / invalid / edge) that
   every indexer runs and must agree on. Divergence on any vector blocks activation. These are the
   contract between implementations — treat them as normative for Accepted+.
3. **Activation-block coordination.** All participating indexers agree on a single activation block
   height. No indexer activates early or late.
4. **Minimum 4-week (~4,032-block) lead time** from Accepted to activation, so operators, wallets,
   and services can upgrade. (Historical precedent: block 796,000 SRC-20 cutoff, block 865,000 OLGA
   — both gave multi-week notice.)
5. **Cross-indexer test pass before activation.** Each indexer runs the shared vectors *and* a full
   historical-sync regression (genesis → tip) to prove no existing-stamp regression, and the teams
   confirm identical results.

**Coordination artifacts to include in the SIP:**

- A "Cross-Indexer Coordination" section naming the participating indexers and their sign-off status.
- A link to the shared test-vector file (for large SIPs, under `docs/sips/SIP-XXXX/` — see §8).
- The agreed activation block height (once Accepted) and the lead-time window.

---

## 5. Activation template

Copy into the SIP's **Activation** section:

```markdown
## Activation

- **Activation block height**: TBD (set at Accepted; MUST be ≥ 4,032 blocks / ~4 weeks after
  acceptance).
- **Minimum lead time**: 4 weeks from Accepted status to activation block.
- **Participating indexers at activation**: stampchain (reference) + <other indexer(s)>.
- **Fail-safe behavior (non-upgraded indexers)**: Describe exactly what an indexer that has NOT
  upgraded does when it encounters the new operation. It MUST fail safe — i.e., ignore the
  operation and NOT mutate balances/state — never fail open (guess and diverge). Example: "A
  pre-upgrade indexer does not treat the new op's marker as a valid operation, so it skips it —
  the transfer is ignored, no tokens are debited, and no stamp number is assigned. This is
  fail-safe, not fail-open." (If your op reuses the existing `stamp:` prefix rather than a new
  marker, see the caveat below — that is *not* automatically fail-safe.)
- **No-balance-divergence check**: State how an upgraded and a not-yet-upgraded indexer avoid
  diverging on *existing* stamps/tokens before the activation height. Confirm that below the
  activation block the new op is a no-op for all indexers.
- **Post-activation monitoring**: Recommend indexers log the new operation during rollout for
  cross-implementation reconciliation.
```

**Fail-safe is the cardinal rule.** The classic safe pattern is a new prefix/marker or op-code that
old indexers simply do not recognize and therefore skip. Avoid any design where a non-upgraded
indexer would *partially* process the operation.

**Verify the fail-safe claim against the reference indexer's real classification path, not intent.**
A common trap: `stamp:` is the *universal* stamp-detection prefix (`config.PREFIX`), so an op that
merely reuses it is **not** skipped by a pre-upgrade indexer. The prefix is recognized, the new
(e.g. binary) body fails to parse as a known operation, and the payload falls through to being
classified as an ordinary stamp (`ident = "STAMP"` in `index_core/models.py`) and assigned a stamp
number. That diverges stamp numbering *and* the `txlist_hash` — which is fail-**open**, the opposite
of the intended behavior. So a design that reuses `stamp:` for a new operation (e.g. a binary SRC-20
encoding) must additionally prove that pre-upgrade indexers cleanly *reject* the new body — not
render it as a stamp — below the activation height, or else use a distinct marker they ignore
outright.

---

## 6. Terminology guide

Bitcoin Stamps has a deliberate, culturally load-bearing vocabulary. Getting it wrong in a SIP is a
review blocker, not a nit.

### Stamps are NOT inscriptions

- **Bitcoin Stamps** store data **directly in the UTXO set** (bare-multisig outputs, or OLGA
  P2WSH). This is the source of Stamps' permanence claim: UTXO-set data is not prunable the way
  witness data is.
- **"Inscription" is the Ordinals term** for data placed in the SegWit **witness** field (which
  receives a fee discount but is prunable / less permanent).
- Therefore: **never call a Stamp, SRC-20, or SRC-721 feature an "inscription."** Do not write
  "stamp inscription," "inscription output," "inscription fees" (for stamp/SRC-20 txs), or
  "inscription method" (for UTXO embedding).

| Don't write (for Stamps) | Write instead |
|--------------------------|---------------|
| "stamp inscription" | "stamp" / "stamp transaction" / "stamp data" |
| "the inscription output" | "the stamp output" / "the transfer output" |
| "inscription fees" | "transaction fees" / "embedding fees" |
| "the inscription method" (UTXO embedding) | "the embedding method" / "the encoding method" / "UTXO storage" |
| "inscribe a stamp" | "create a stamp" / "mint a stamp" / "embed on-chain" |
| "data inscription ecosystem" | "data-embedding ecosystem" |

### When "inscription" IS correct

Use "inscription" **only** when you genuinely mean an **Ordinals** inscription:

- Comparing Stamps to Ordinals ("Ordinals inscriptions live in witness data").
- Referring to BIP-110's "witness-data inscriptions."
- **SIP-0110 (PRESERVE)** is *about* preserving Ordinals inscriptions — it correctly says
  "inscription" for the source Ordinals content and "Stamp" for the resulting asset. That is the
  model to follow: name the Ordinals thing an inscription, name the Stamps thing a stamp, and never
  blur them.
- A good in-repo example is SIP-0002 (#484): *"When a UTXO contains both an **ordinal inscription**
  (or rune) and SRC-20 transfer data …"* — the Ordinals thing is an inscription; the Stamps thing
  is SRC-20 data.

### KEVIN and cultural rules

- **KEVIN is always written in ALL CAPS.** KEVIN is the first SRC-20 token and a cultural
  touchstone; it is never "Kevin" or "kevin" in protocol docs.
- **Preserve the permanence narrative.** Stamps' value proposition is UTXO permanence over witness
  ephemerality — do not frame Stamps as a cheaper/lesser variant of inscriptions.
- **Respect the community's authentic heritage** (Trinity formation narrative, KEVIN provenance)
  when a SIP touches cultural artifacts; do not rewrite or flatten it.

---

## 7. Pre-submission checklist

Before you open (or move to Review) a SIP:

- [ ] Title is `SIP-XXXX: <descriptive title>` and the number is assigned/reserved per SIP-0000.
- [ ] Every template section (§1) is present and non-empty (Open Questions may say "none").
- [ ] Specification is precise enough for an independent indexer to implement without asking you.
- [ ] Determinism statement present (all indexer-written fields derive solely from chain data).
- [ ] Backward-compatibility analysis present and concrete.
- [ ] **Security Considerations** answers every item in §3 (or marks N/A with a reason).
- [ ] Test Vectors present (illustrative OK for Draft; concrete testnet vectors required for Accepted).
- [ ] Cross-indexer coordination section names ≥2 indexers and links the shared vectors (§4).
- [ ] Activation section uses the §5 template with an explicit fail-safe description.
- [ ] **Terminology audit (§6):** grep your draft for "inscription" — every remaining occurrence
      must be a genuine Ordinals reference. Fix any Stamp/SRC-20 misuse. KEVIN is ALL-CAPS.
- [ ] `SIP` label added to the issue; registry updated per SIP-0000's "New SIP Checklist"
      (SIP-0000 table, `README.md`, whitepaper `improvement-proposals.md`, and
      `sip-registry.yaml` on bitcoinstamps.xyz).
- [ ] Related SIPs cross-referenced (comments on SIPs this depends on / interacts with).

---

## 8. Large SIPs: the SIP-0110 split pattern

For a SIP whose full material (spec + reference implementation + test vectors + reviewer notes)
would make a single GitHub issue unwieldy, use the **SIP-0110 split pattern**:

- **The normative specification stays in the GitHub issue.** The issue body is the single source of
  truth for the consensus rules (`#878` for SIP-0110).
- **Supporting, non-normative material lives in the repo** under `docs/sips/SIP-XXXX/`, and the
  issue links to it. SIP-0110 uses:
  - `docs/sips/SIP-0110/reference-implementation.md` — grounds the proposed indexer changes in the
    real `btc_stamps` codebase (module/function/table names), and flags where the brief diverged
    from the actual code. Explicitly labeled *"Non-normative supporting material … see the SIP issue
    for the normative specification."*
  - `docs/sips/SIP-0110/test-vectors.md` — illustrative test vectors (TV-01…TV-nn), each stating the
    expected consensus-layer outcome, with the note that an Accepted SIP MUST ship concrete testnet
    vectors.

**Why:** the issue stays readable and reviewable; the heavy, code-grounded material is diff-able in
PRs and versioned with the codebase it references; and the normative/non-normative boundary is
unambiguous. Every supporting file MUST carry a header stating it is non-normative and pointing to
the issue for the normative spec.

Small SIPs do **not** need a `docs/sips/SIP-XXXX/` directory — the issue alone is sufficient
(SIP-0000, "Future Considerations").
