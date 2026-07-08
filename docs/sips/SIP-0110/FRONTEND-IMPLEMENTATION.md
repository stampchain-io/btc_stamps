# SIP-0110 (OPP) — Frontend Implementation Guidance (Option A)

This is the implementation brief for the stampchain.io frontend + the #880 verifier. It reflects the **Option A** direction (see `DIRECTION-DECISION.md`): provenance/canonicity live OFF consensus, in the verifier + frontend; the indexer emits only the raw claim + `content_verified`.

## Confirmed model

- **Indexer emits ONLY:** the raw `p:"SRC-ORD"` PRESERVE claim + `content_verified` (byte-hash match). No `verified`, no `canonical`, no `migration_hash`. Do not read provenance/canonicity from the indexer — it does not have it.
- **Verifier + frontend own all provenance.** Everything a user sees about "is this real / who owns it / which is canonical" comes from the verifier.
- Content preservation is separate and already works (content is a plain OLGA stamp); this is the provenance/verification layer on top.

## Verifier contract (build against this)

```
GET {verifier}/provenance/{stamp_id} ->
{ content_verified,
  provenance_state: verified|unverified|disputed|unverifiable,
  canonicity:       canonical|superseded|contested|null,
  attestation:      owner_attested|unilateral|null,
  source_inscription_url,      // REQUIRED - always link out to the original
  competing_claims: [...],     // for "disputed"
  verifier: {...}, ttl_seconds }
```

- Badges are verifier-sourced, never indexer-sourced.
- Graceful degradation: verifier down -> render `unverified`; never fail closed or show a stale "verified."
- Always surface `verified`/`unverified` AND `full`/`anchor`. An `anchor` (no-content) record must never render as "verified" or "the canonical."
- Mandatory link-out to the source inscription on every provenance surface — never present a preserved copy as the original.

## The load-bearing decision: verifier canonicity policy

With canonicity off consensus, the verifier must decide how it picks `canonical` among competing claims. **Recommendation: owner-designated, current-owner-wins, explicitly mutable** (flips when the inscription changes hands) — the honest model, and the fix for stale-binding (re-check live ownership rather than freeze a one-time claim). It MUST be reproducible across independent verifier operators (agree on the `ord`-index snapshot + policy); that reproducibility is the cross-indexer contract now, replacing the removed consensus hash.

## Do NOT build / assume

- No in-consensus `canonical_flag`/`migration_hash` — gone; do not design around them.
- Do not source provenance from the indexer; do not assume canonicity is immutable.
- Do not lead the UX with "tradeable/wrapped asset" framing — frame it as "provenance attestation + link to the original," not "buy this wrapped inscription."

## Scope discipline (gated MVP)

Build the minimal verifier + frontend + "parse a metadata op" MVP. Do not over-build — expansion past MVP is gated on a demand signal: >=2 teams (one per community) running the verifier + >500 distinct-creator attestations within 60 days.

## Coordinate on

1. Finalize `GET /provenance/{stamp_id}` jointly with the backend/#880 verifier team.
2. Agree the canonicity policy + `ord`-index reproducibility with >=1 other indexer/verifier operator.
3. Reference: `DIRECTION-DECISION.md` + `specification.md`.
