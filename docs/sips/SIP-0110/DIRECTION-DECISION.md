# SIP-0110 (PRESERVE / OPP) — Direction Decision & Revision Plan

**Status:** DIRECTION SETTLED (pending community-values sign-off + a demand gate). This supersedes the "full in-consensus tradeable-canonical" shape drafted in `specification.md`. The spec body is to be revised per §5 below.

**Basis:** three independent reviews converged on the same design — **Option A: provenance/canonicity lives OFF consensus, in a verifier + frontend; the indexer's only job is the raw claim + a content byte-hash.**

| Reviewer | Verdict |
|---|---|
| Anthropic **Opus** (community-alignment) | REVISE → *"move `canonical_flag`/provenance out of consensus into the verifier/display layer; that also collapses the indexer adoption ask."* |
| **Grok** (xAI, 2 rounds) | Option A = *"the only version I would ship in its current form"* — and it **demoted its own round-1 recommendation (attestation-only-with-a-mechanism)** below A. C = *"do not ship."* |
| **stampchain.io frontend team** (implementers) | Already building it: *"frontend sources all provenance from the verifier, never the indexer… indexer emits no `verified`/`canonical`."* Expects `canonical_flag` removed; no tokenization. |

---

## 1. The decision

Adopt **Option A**. Concretely:

- **Consensus / indexer owns (minimal, deterministic):**
  - Parse + store the raw `p:"SRC-ORD"` PRESERVE claim (the JSON sidecar) as an immutable record.
  - Compute `content_verified` — **full-mode byte-hash only** (does the declared hash match the referenced content-stamp bytes). Nothing else.
  - Emit **NO** `verified`, **NO** `canonical_flag`, and **NO** `migration_hash` consensus stream.
- **Verifier (#880) + frontend own (off consensus):** all `provenance_state`, `canonicity`, `attestation`, competing-claim resolution, and the "verified" badge — re-checkable against a live `ord` index, mutable over time.
- **Content preservation is unchanged and uncontested:** the content is a plain OLGA stamp — permanent, permissionless, identically numbered by every indexer regardless of SIP-0110. That mechanic stays.

## 2. How this resolves the review findings

| Finding (both models) | Resolution under Option A |
|---|---|
| One-time UTXO proof → **replay / stale-binding** | Gone as a *consensus* defect. The verifier re-checks **current** ownership live; there is no frozen in-consensus binding to go stale. |
| **No indexer incentive** → adoption killer | Ask collapses from "adopt a permanent new consensus surface (stream + table + reorg-purge)" to **"optionally parse a metadata op."** No new consensus divergence risk for OpenStamp/stampscan. |
| Consensus **`canonical_flag` forgeable / front-runnable** | Removed from consensus entirely — a squatter cannot capture a display-layer flag. |
| **SRC-20 ledger isolation** debate | Moot — Grok conceded the byte-identical-hash evidence; there is no `migration_hash` stream to defend. Don't spend further design effort here. |
| **No creator consent** / financialization | Reduced (no in-consensus "the-canonical" migration asset; frontend does not tokenize). **Residual — see §4.** |

## 3. Frontend ⇄ verifier UX contract (normative for the app; non-consensus)

Straw-man endpoint the frontend is designing against — to be finalized with the frontend team:

```
GET {verifier}/provenance/{stamp_id}
{
  "content_verified": bool,          // mirrored from indexer for convenience
  "provenance_state": "verified" | "unverified" | "disputed" | "unverifiable",
  "canonicity":       "canonical" | "superseded" | "contested" | null,
  "attestation":      "owner_attested" | "unilateral" | null,
  "source_inscription_url": "<link-out to the original inscription>",  // MANDATORY
  "competing_claims": [ ... ],       // populated for "disputed"
  "verifier": { ...attester + timestamp... },
  "ttl_seconds": <cache model>
}
```

UI rules (from the gist): badges are **verifier-sourced, never indexer-sourced**; graceful degradation to `unverified` when the verifier is unavailable; first-class `verified`/`unverified` + `full`/`anchor` distinction; **mandatory link-out** to the original inscription; competing-claims display for disputes.

## 4. Open decisions

- **[VERIFIER-CANONICITY — the key remaining design question, raised by the frontend team]** With canonicity off consensus, *how does the verifier pick `canonical`* among competing claims for one inscription — **first-valid / attestation-weighted / owner-designated**? Is it **reproducible** across verifier operators, and **may it flip over time**? This is now the load-bearing design choice (it moved from consensus to policy). Recommend: **owner-designated, current-owner-wins, explicitly mutable** — which is the honest model and the one the "provenance" word actually implies.
- **[COMMUNITY VALUES — surface to community reviewers, not engineerable]** Both models flag the cultural *"plain stamps shouldn't be financialized in the Counterparty sense"* objection. Option A reduces it (no in-consensus canonical asset; the frontend doesn't tokenize) but does not eliminate it if a preserved content-stamp is ever DEX-listed. This is a Stamps-community values call.
- **[CONSENT]** Add an explicit inscription-creator consent / attribution / takedown position (even if "out of consensus scope," the spec cannot be silent). Combined with the mandatory link-out, this is the main blunting of the ordinals-artist attack.
- **[ANCHOR MODE]** Resolve OQ#12 → an `anchor` (no-content, unverified) record must render `provenance_state != "verified"` and MUST NOT be presentable as canonical.

## 5. Concrete revision plan for `specification.md`

**Cut / demote to non-normative:**
- §5 `migration_hash` serialization — **remove the consensus stream entirely** (its whole justification was the in-consensus `canonical_flag`, which is gone). Keep the anti-`str()`/`repr()` serialization guidance only if any per-block hashing of the raw claim record is retained; otherwise drop.
- §3.5 rules 4/6 and §3.8 `canonical_flag` logic — **remove `canonical_flag` from consensus**; relocate canonicity to the verifier contract (§3.6 / new frontend-contract section).
- §3.5.1 "ownership proof" — **rename to "spend attestation"**; state plainly it is not an ownership proof and is not consensus-authoritative.

**Keep (unchanged, they were the strong parts):**
- 2-tx reference model + the content-as-OLGA-stamp carrier (§3.3) — the extractor-safety rationale holds.
- `content_verified` byte-hash (full mode) as the *only* consensus-emitted verification bit.
- BIP-322 (Method A) deferral (§2, §7.5) — correct consensus-safety call.

**Add:**
- The **frontend ⇄ verifier UX contract** (§3 above) as a normative-for-the-app section.
- The **consent/attribution/link-out** position.
- The **demand gate** (§6).
- `stamp_migrations` reorg note: if the raw claim record is still stored per-block, it must still be in `purge_block_db` for reorg safety — but this is now indexer-internal bookkeeping, not a consensus-hash requirement.

## 6. Go / no-go demand gate (Grok, concrete + testable — recommend adopting into the PRD)

Do **not** build past the "optionally parse a metadata op" MVP until:
- **≥2 non-trivial teams (at least one from each of the Stamps and Ordinals sides)** publicly commit to run the off-chain verifier + a frontend, **and**
- **>500 distinct-creator provenance attestations within 60 days** of a test deployment.

Anything weaker is "just another unused metadata field."

## 7. Bottom line

The content-preservation mechanic is sound and stays. Everything both communities objected to lived in the **in-consensus tradeable-canonical provenance layer** — which Option A removes. Ship the minimal metadata-op + verifier + frontend; gate any expansion on the §6 demand signal; and take the financialization-values question to the community rather than engineering around it.
