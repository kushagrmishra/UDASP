# EPI Schema — Entangled Packet Identifier

**Version:** 1.0  
**Status:** Theoretical framework  
**Author:** Kushagr Mishra  
**Date:** April 2026

---

## Overview

The Entangled Packet Identifier (EPI) is the cryptographic identity assigned to each shard in UADSP. It encodes sibling awareness without encoding sibling location — a shard knows it belongs to a family without knowing where any sibling currently resides.

The EPI is regenerated at every Morphic Hop. The inner components (FID, SI, FS) remain constant across hops; the outer components (VT, DT) are refreshed.

---

## Design Requirements

The EPI satisfies six requirements simultaneously:

| Requirement | Description |
|-------------|-------------|
| Uniqueness | No two packets share an EPI |
| Sibling Awareness | Encodes that siblings exist and their count, without encoding their location |
| Recall Verifiability | A packet can verify a cryptowave signal without revealing its identity to a passive observer |
| Location Independence | Contains no routing information of any kind |
| Tamper Evidence | Modification of any EPI component is detectable |
| Observer Governance | Carries a DEFENDER component enforcing active observer acceptance |

---

## EPI Structure

```
┌─────────────────────────────────────────────────┐
│                EPI (total: ~1600 bits)          │
├──────────────┬──────────────────────────────────┤
│ Family ID    │ 256-bit HMAC-SHA256 hash          │
│ (FID)        │ Shared across all siblings        │
├──────────────┼──────────────────────────────────┤
│ Shard Index  │ 32-bit integer                    │
│ (SI)         │ Ordinal position within family    │
├──────────────┼──────────────────────────────────┤
│ Family Size  │ 32-bit integer                    │
│ (FS)         │ Total sibling count (n)           │
├──────────────┼──────────────────────────────────┤
│ Verification │ 512-bit one-time-pad token        │
│ Token (VT)   │ Regenerated at every Morphic Hop  │
├──────────────┼──────────────────────────────────┤
│ DEFENDER     │ 768-bit signed time-variant token │
│ Token (DT)   │ Observer governance credential    │
└──────────────┴──────────────────────────────────┘
```

---

## Component Definitions

### Family ID (FID)

The FID uniquely identifies the data family — all `n` shards of the same dataset share one FID. It is derived from the Family Derivation Secret (FDS) held by the Recall Authority:

```
FID = HMAC-SHA256(FDS, dataset_identifier)
```

The FID is encrypted within the packet payload. A relay node holding a shard cannot read the FID — it can only forward the packet. Only the Recall Authority and the Recall Engine can derive and verify FIDs.

### Shard Index (SI)

The ordinal position of this shard within the family: `0` through `n-1`. Used by the Recall Engine for sequence validation and Reed-Solomon decoding order.

### Family Size (FS)

The total number of shards in this family (`n`). Combined with SI, allows any shard to know the complete family composition count without knowing sibling locations.

### Verification Token (VT)

A one-time-pad-derived token enabling cryptowave resonance verification. The VT is the basis for the Shard Resonance Key (SRK) used in resonance scoring:

```
SRK = H(FID || SI || VT)
R   = similarity(cryptowave_W, SRK)
```

The VT is regenerated at each Morphic Hop. Each hop produces a new VT, a new SRK, and therefore a new resonance fingerprint. This ensures that even if a packet's identity is observed at one hop, it cannot be tracked to the next.

### DEFENDER Token (DT)

A time-variant 768-bit signed credential encoding the data holder's observer governance policy:

| DT Field | Description |
|----------|-------------|
| Observer list hash | BLAKE3 hash of all registered observer identity certificates |
| Pulse rate | How frequently the DEFENDER Pulse Signal is broadcast |
| Acceptance window | Time in seconds within which an observer must accept each pulse |
| Current epoch | Monotonically increasing epoch counter — invalidates tokens from prior epochs |
| RA signature | Signed by the Recall Authority using its private key |

---

## EPI DEFENDER — Observer Governance

### Problem

Observers registered by the data holder may become inactive, compromised, or malicious after registration. A passive registration model has no mechanism to detect or respond to this.

### Solution

The DEFENDER model enforces active, continuous, cryptographically verified participation. At each pulse interval, every registered observer must actively sign and return the Pulse Signal using their DEFENDER Token. Silence is a failure event.

### Rules

| Event | Consequence |
|-------|-------------|
| Observer accepts Pulse Signal | Token remains valid, observer stays registered |
| Observer fails to accept within window | Immediately removed from sibling resolution network for all families |
| Removal | DEFENDER Token revoked at key derivation level — permanently invalid |
| Re-joining | Full re-authentication with data holder required; new DT issued |

### Cryptographic Removal

Removal is not a database flag — it is cryptographic. Future Pulse Signals are generated excluding the removed observer's identity input:

```
pulse_n = H(FDS || epoch_n || active_observer_list_hash)
```

A removed observer's token was derived using a prior `active_observer_list_hash`. It cannot verify any future pulse. The token is permanently and irrevocably invalid regardless of whether the observer later responds.

---

## EPI Across Morphic Hops

At each hop, the EPI is partially refreshed:

| Component | Behaviour across hops |
|-----------|----------------------|
| FID | Constant — inner payload, encrypted |
| SI | Constant — inner payload, encrypted |
| FS | Constant — inner payload, encrypted |
| VT | **Regenerated** — new random value each hop |
| DT | **Refreshed** — epoch updated, re-signed by RA at each pulse interval |

The regeneration of VT means each hop produces a new observable EPI at the network layer, even though the inner family identity is preserved.

---

## What a Relay Node Knows

A relay node holding a shard can observe:

- That it holds *a* shard (encrypted payload in RAM)
- Nothing else

The relay node cannot read the FID, SI, FS, or any EPI component — all are encrypted within the payload using the shard's AES-256-GCM key, which the relay node does not hold. The relay node forwards packets based on Morphic Hopping routing logic alone.

---

## Copyright

Copyright © 2026 Kushagr Mishra. All Rights Reserved.  
See repository root LICENSE for full terms.
