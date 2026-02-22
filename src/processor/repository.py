"""Database operations.

Design:
- Idempotent inserts (ON CONFLICT DO NOTHING)
- Connection pooling via asyncpg
- Parameterized queries (SQL injection safe)
"""

import asyncpg
from typing import Optional
from dataclasses import dataclass


@dataclass
class Threat:
    """Threat record to persist."""
    domain: str
    fingerprint: str
    matched_keyword: str
    entropy: float
    confidence: str
    issuer: Optional[str]
    not_before: Optional[int]
    not_after: Optional[int]


class Repository:
    """Database repository for threats."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Initialize connection pool."""
        self._pool = await asyncpg.create_pool(
            self._database_url,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    async def insert_threat(self, threat: Threat) -> bool:
        """
        Insert threat record. Returns True if inserted, False if duplicate.
        
        Idempotent: duplicate fingerprints are silently ignored.
        """
        if not self._pool:
            raise RuntimeError("Repository not connected")

        query = """
            INSERT INTO threats (
                domain, fingerprint, matched_keyword, 
                entropy, confidence, issuer, not_before, not_after
            ) VALUES ($1, $2, $3, $4, $5, $6, 
                      to_timestamp($7), to_timestamp($8))
            ON CONFLICT (fingerprint) DO NOTHING
            RETURNING id
        """

        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                query,
                threat.domain,
                threat.fingerprint,
                threat.matched_keyword,
                threat.entropy,
                threat.confidence,
                threat.issuer,
                threat.not_before,
                threat.not_after,
            )
            return result is not None

    async def health_check(self) -> bool:
        """Check database connectivity."""
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False