"""
UADSP Splitter Engine — Prototype
==================================
Fragmentation engine for the Uncertainty-Anchored Distributed Storage Protocol.

Implements Phase 1 (Fragmentation) of UADSP-CORE:
  - Reed-Solomon erasure encoding (k, n) via pyeclib
  - Per-shard AES-256-GCM encryption
  - HKDF-SHA256 per-shard key derivation
  - Entangled Packet Identifier (EPI) assignment
  - RAM-only operation — zero persistent state after shard release

Copyright (c) 2026 Kushagr Mishra. All Rights Reserved.
See repository root LICENSE for full terms.

Status: Prototype — theoretical framework implementation.
        Not production-ready. See open engineering challenges in paper/.
"""

import os
import secrets
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import List, Tuple
from enum import Enum

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
except ImportError:
    raise ImportError(
        "Install required dependency: pip install cryptography"
    )

try:
    import pyeclib.ec_iface as ec
    PYECLIB_AVAILABLE = True
except ImportError:
    PYECLIB_AVAILABLE = False
    print(
        "[WARNING] pyeclib not available — falling back to simple XOR split.\n"
        "          For production use, install pyeclib: pip install pyeclib\n"
    )


# ── Sensitivity tiers ────────────────────────────────────────────────────────

class SensitivityTier(Enum):
    STANDARD = "standard"
    ELEVATED = "elevated"
    CRITICAL = "critical"


TIER_PARAMS = {
    SensitivityTier.STANDARD: {"n": 10, "k": 6},
    SensitivityTier.ELEVATED: {"n": 16, "k": 8},
    SensitivityTier.CRITICAL: {"n": 24, "k": 8},
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class EPI:
    """
    Entangled Packet Identifier.
    Encodes sibling awareness without sibling location.
    See spec/EPI-schema.md for full specification.
    """
    family_id: bytes        # 256-bit HMAC-SHA256 — shared across all siblings
    shard_index: int        # Ordinal position within family
    family_size: int        # Total sibling count (n)
    verification_token: bytes  # 64-byte one-time token — regenerated each hop
    # Note: DEFENDER Token (DT) omitted in prototype — requires Recall Authority

    def to_dict(self) -> dict:
        return {
            "family_id": self.family_id.hex(),
            "shard_index": self.shard_index,
            "family_size": self.family_size,
            "verification_token": self.verification_token.hex(),
        }


@dataclass
class EncryptedShard:
    """
    A single encrypted shard ready for release into Uncertainty Transit.
    After release, the Splitter Engine retains no reference to this object.
    """
    epi: EPI
    ciphertext: bytes       # AES-256-GCM encrypted shard data
    nonce: bytes            # 96-bit random nonce
    auth_tag: bytes         # 16-byte GCM authentication tag (appended to ciphertext by AESGCM)
    shard_key_id: str       # Identifier only — actual key is destroyed after encryption

    def to_dict(self) -> dict:
        return {
            "epi": self.epi.to_dict(),
            "ciphertext": self.ciphertext.hex(),
            "nonce": self.nonce.hex(),
            "shard_key_id": self.shard_key_id,
        }


@dataclass
class RecallSeed:
    """
    Minimal cryptographic credential enabling authorised recall.
    In production, the four components are held separately:
      - FDS and integrity_digest → Recall Authority HSM
      - reconstruction_threshold → system configuration
      - session_scope_token → issued fresh at each authenticated session

    This prototype holds all components together for demonstration only.
    See UADSP-CORE spec Section 4.2.3 for full production model.
    """
    family_derivation_secret: bytes   # Root secret for FID and key derivation
    reconstruction_threshold: int     # k — minimum shards for reconstruction
    integrity_digest: bytes           # BLAKE3/SHA256 hash of original data D
    session_scope_token: bytes        # Single-use, time-bounded credential


# ── Splitter Engine ───────────────────────────────────────────────────────────

class SplitterEngine:
    """
    UADSP Splitter Engine.

    Stateless, RAM-only fragmentation process. Accepts raw data D and produces
    an ordered set of encrypted micro-shards with no knowledge of where those
    shards will travel.

    The engine knows everything about D at fragmentation time and nothing about
    D after shard release. This is by design.
    """

    def __init__(self, tier: SensitivityTier = SensitivityTier.STANDARD):
        params = TIER_PARAMS[tier]
        self.n = params["n"]   # Total shards
        self.k = params["k"]   # Reconstruction threshold
        self.tier = tier

    def fragment(self, data: bytes) -> Tuple[List[EncryptedShard], RecallSeed]:
        """
        Fragment data D into n encrypted shards.

        Returns:
            shards      — list of EncryptedShard objects ready for Uncertainty Transit
            recall_seed — credential enabling authorised recall (store securely)

        After this method returns, the SplitterEngine retains no state about D.
        """

        # ── Step 1: Generate master fragmentation secret ──────────────────────
        master_secret = secrets.token_bytes(32)

        # ── Step 2: Derive Family ID ──────────────────────────────────────────
        family_id = hmac.new(
            master_secret,
            b"UADSP-FID-v1",
            hashlib.sha256
        ).digest()  # 256-bit Family ID

        # ── Step 3: Reed-Solomon erasure encoding ─────────────────────────────
        raw_shards = self._erasure_encode(data)

        # ── Step 4: Per-shard key derivation + AES-256-GCM encryption ─────────
        encrypted_shards = []
        for i, raw_shard in enumerate(raw_shards):
            shard_key = self._derive_shard_key(master_secret, i)
            nonce = secrets.token_bytes(12)  # 96-bit random nonce

            # AES-256-GCM — ciphertext includes auth tag appended by library
            aesgcm = AESGCM(shard_key)
            ciphertext_with_tag = aesgcm.encrypt(nonce, raw_shard, None)

            # EPI assignment
            verification_token = secrets.token_bytes(64)
            epi = EPI(
                family_id=family_id,
                shard_index=i,
                family_size=self.n,
                verification_token=verification_token,
            )

            encrypted_shards.append(EncryptedShard(
                epi=epi,
                ciphertext=ciphertext_with_tag,
                nonce=nonce,
                auth_tag=ciphertext_with_tag[-16:],   # Last 16 bytes = GCM tag
                shard_key_id=f"shard-{family_id.hex()[:8]}-{i}",
            ))

            # Destroy shard key from local scope immediately
            del shard_key

        # ── Step 5: Build Recall Seed ─────────────────────────────────────────
        integrity_digest = hashlib.sha256(data).digest()
        session_scope_token = secrets.token_bytes(32)

        recall_seed = RecallSeed(
            family_derivation_secret=master_secret,
            reconstruction_threshold=self.k,
            integrity_digest=integrity_digest,
            session_scope_token=session_scope_token,
        )

        # ── Step 6: Purge intermediate state ──────────────────────────────────
        # In production, master_secret would be securely transferred to the
        # Recall Authority HSM and then zeroed from RAM here.
        # Python does not guarantee memory zeroing on del — a production
        # implementation requires ctypes or a memory-safe language for this step.
        del master_secret
        del family_id
        del raw_shards

        return encrypted_shards, recall_seed

    def _erasure_encode(self, data: bytes) -> List[bytes]:
        """
        Encode data using Reed-Solomon (k, n) erasure coding.
        Falls back to simple equal-split if pyeclib unavailable.
        """
        if PYECLIB_AVAILABLE:
            ec_driver = ec.ECDriver(
                k=self.k,
                m=self.n - self.k,
                ec_type="liberasurecode_rs_vand"
            )
            return ec_driver.encode(data)
        else:
            # Fallback: pad and split into n equal chunks
            # This is NOT equivalent to Reed-Solomon — install pyeclib for real use
            chunk_size = max(1, (len(data) + self.n - 1) // self.n)
            padded = data.ljust(chunk_size * self.n, b'\x00')
            return [padded[i * chunk_size:(i + 1) * chunk_size] for i in range(self.n)]

    def _derive_shard_key(self, master_secret: bytes, shard_index: int) -> bytes:
        """
        Derive a unique 256-bit AES key for shard i using HKDF-SHA256.
        No two shards share a key. Compromise of one key reveals nothing about others.
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"UADSP-shard-key-{shard_index}".encode(),
            backend=default_backend()
        )
        return hkdf.derive(master_secret)


# ── Demo ──────────────────────────────────────────────────────────────────────

def demo():
    print("UADSP Splitter Engine — Prototype Demo")
    print("=" * 50)

    test_data = b"Sensitive data: this would be encrypted and fragmented across distributed nodes."
    print(f"Input data:     {len(test_data)} bytes")

    engine = SplitterEngine(tier=SensitivityTier.STANDARD)
    print(f"Sensitivity:    {engine.tier.value} (n={engine.n}, k={engine.k})")
    print()

    shards, recall_seed = engine.fragment(test_data)

    print(f"Shards produced: {len(shards)}")
    print(f"Reconstruction threshold: any {recall_seed.reconstruction_threshold} of {len(shards)}")
    print()

    for i, shard in enumerate(shards[:3]):
        print(f"Shard {i}:")
        print(f"  Family ID (first 16 hex): {shard.epi.family_id.hex()[:16]}...")
        print(f"  Shard index:              {shard.epi.shard_index} / {shard.epi.family_size}")
        print(f"  Ciphertext size:          {len(shard.ciphertext)} bytes")
        print(f"  Nonce:                    {shard.nonce.hex()}")
        print()

    print(f"[Shards {3}–{len(shards)-1} omitted for brevity]")
    print()
    print("Recall Seed components:")
    print(f"  Family Derivation Secret: {recall_seed.family_derivation_secret.hex()[:16]}... (32 bytes)")
    print(f"  Reconstruction threshold: k = {recall_seed.reconstruction_threshold}")
    print(f"  Integrity digest:         {recall_seed.integrity_digest.hex()[:16]}... (SHA-256)")
    print(f"  Session scope token:      {recall_seed.session_scope_token.hex()[:16]}... (32 bytes)")
    print()
    print("Splitter Engine state after release: None (purged)")
    print()
    print("Note: In production, the Recall Seed components are held separately.")
    print("      FDS + integrity digest → Recall Authority HSM")
    print("      Reconstruction threshold → system configuration")
    print("      Session scope token → issued fresh per authenticated session")


if __name__ == "__main__":
    demo()
