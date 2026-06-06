# UADSP-CORE — Uncertainty Storage Protocol Specification

**Version:** 1.0  
**Status:** Theoretical framework  
**Author:** Kushagr Mishra  
**Date:** April 2026

---

## Overview

UADSP-CORE is the three-phase operational protocol of the Uncertainty-Anchored Distributed Storage Protocol. It governs how data enters, persists in, and exits the UADSP system.

The three phases are:

1. **Fragmentation** — data is split, encrypted, and released into the network
2. **Uncertainty Transit** — packets travel continuously with no rest state
3. **Authorised Recall** — authenticated assembly of data in memory only

No data is ever complete at rest. No authority holds a routing map. No migration event occurs.

---

## Phase 1 — Fragmentation

### 1.1 Sensitivity Classification

Incoming data `D` is classified into one of three sensitivity tiers:

| Tier | Shards (n) | Reconstruction threshold (k) | k/n ratio |
|------|-----------|------------------------------|-----------|
| Standard | 10 | 6 | 0.60 |
| Elevated | 16 | 8 | 0.50 |
| Critical | 24 | 8 | 0.33 |

Higher sensitivity = more shards, lower k/n ratio, greater uncertainty and redundancy.

### 1.2 Reed-Solomon Erasure Encoding

`D` is encoded using a `(k, n)` Reed-Solomon scheme (Vandermonde matrix, via pyeclib). Any `k` of the `n` shards can reconstruct `D` exactly. The remaining `n-k` shards are parity shards carrying no data fragment.

### 1.3 Per-Shard Key Derivation

A unique 256-bit key is derived for each shard:

```
shard_key[i] = HKDF-SHA256(master_fragmentation_secret, shard_index=i)
```

No two shards share a key. Compromise of one shard key reveals nothing about any other.

### 1.4 AES-256-GCM Encryption

Each shard is independently encrypted:

```
ciphertext[i], tag[i] = AES-256-GCM(shard_key[i], nonce[i], plaintext_shard[i])
```

The GCM authentication tag provides per-shard integrity verification at recall.

### 1.5 EPI Assignment

Each encrypted shard is assigned an Entangled Packet Identifier. See `EPI-schema.md`.

### 1.6 Shard Release and State Purge

Shards are released individually into the Uncertainty Transit layer. The Splitter Engine immediately purges all intermediate state from RAM — no shard, no key, no routing intention is retained.

**Invariant:** The Splitter Engine knows everything about `D` at fragmentation time and nothing about `D` one millisecond after release.

---

## Phase 2 — Uncertainty Transit

Uncertainty Transit is the permanent operational state of all packets. It has no start and no end — packets enter at fragmentation and leave only at authorised recall.

### Invariants

- **Continuous motion** — no packet has a rest state
- **Non-deterministic timing** — transition intervals drawn from a true random process
- **Non-deterministic routing** — destination nodes selected uniformly at random from live pool
- **No announcement** — nodes do not index resident packets
- **Identity shedding** — at each hop, the packet undergoes Morphic Hopping (full identity replacement)
- **Constant traffic** — all nodes send/receive at a fixed rate regardless of real packet presence

### Morphic Hopping

At each relay node:

1. Incoming packet received into RAM only — no disk write
2. Packet decrypted using hop-specific ephemeral key
3. Inner payload extracted and held in RAM
4. New packet wrapper created: new encryption, new size, new headers, new identity
5. Original packet overwritten with random bytes and deallocated
6. New packet transmitted to next randomly selected relay node
7. Ephemeral hop key destroyed

Result: the outbound packet is observable as a completely different packet from the inbound one at every network layer.

---

## Phase 3 — Authorised Recall

### 3.1 Authentication

A principal presents valid credentials to the Recall Authority (RA). The RA validates the Session Scope Token (SST) and, if valid, initiates the recall using the Recall Seed.

### 3.2 Cryptowave Broadcast

The RA generates a cryptowave `W`:

```
W = H(SK || N || SE || FS)
```

Where:
- `SK` = per-session asymmetric key pair
- `N` = cryptographically random nonce
- `SE` = session entropy from multiple unpredictable sources
- `FS` = Family Signature (derivative of Family ID, known only to RA)

`W` is broadcast across the relay network via the Constant Traffic channel — indistinguishable from dummy traffic.

### 3.3 Silent Absorption

Each shard computes a resonance score:

```
R = similarity(W, SRK)
```

Where `SRK` is the Shard Resonance Key derived from EPI components at creation.

- If `R < T` (threshold): shard does nothing, continues Uncertainty Transit
- If `R ≥ T`: shard silently absorbs the cryptowave, emits no signal, begins routing toward the Recall Engine via Morphic Hopping

No response signal is ever emitted. Recall is network-invisible.

### 3.4 Assembly

The Recall Engine collects arriving shards, verifies each via GCM authentication tag and EPI family signature, and waits until `k` verified shards arrive. Reed-Solomon decoding reconstructs `D` entirely in RAM.

### 3.5 Delivery and Purge

`D` is delivered to the authenticated client via encrypted in-memory channel. All shard buffers, decoding state, and the reconstructed `D` are immediately overwritten with random bytes and deallocated.

**Invariant:** `D` is whole only in the client's RAM, only for the duration of the session, only after successful authentication.

---

## Security Properties

| Property | Guaranteed by |
|----------|--------------|
| No static location | Uncertainty Transit — continuous non-deterministic motion |
| No routing map | Splitter Engine state purge + no node indexing |
| No migration timestamp | Motion is permanent state, not an event |
| No complete data at rest | k-of-n erasure coding — no single node holds reconstructible data |
| Network-invisible recall | Silent Absorption Model |
| Timestamp uncorrelatability | Ephemeral RAM + Morphic Hopping + Constant Traffic Invariant |

---

## Copyright

Copyright © 2026 Kushagr Mishra. All Rights Reserved.  
See repository root LICENSE for full terms.
