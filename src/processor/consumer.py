"""NATS message consumer.

Design:
- Pull-based consumption
- Manual ACK after successful DB write
- Graceful error handling
"""

import json
import asyncio
import nats
from nats.errors import TimeoutError as NatsTimeoutError
from typing import Callable, Awaitable, Optional
import logging

logger = logging.getLogger(__name__)


class Consumer:
    """NATS message consumer."""

    def __init__(self, nats_url: str, subject: str):
        self._nats_url = nats_url
        self._subject = subject
        self._nc: Optional[nats.NATS] = None
        self._sub = None

    async def connect(self) -> None:
        """Connect to NATS."""
        self._nc = await nats.connect(
            self._nats_url,
            reconnect_time_wait=2,
            max_reconnect_attempts=-1,
        )
        self._sub = await self._nc.subscribe(self._subject)
        logger.info(f"Connected to NATS: {self._nats_url}, subject: {self._subject}")

    async def close(self) -> None:
        """Close NATS connection."""
        if self._sub:
            await self._sub.unsubscribe()
        if self._nc:
            await self._nc.close()

    async def consume(
        self,
        handler: Callable[[dict], Awaitable[bool]],
        shutdown_event: asyncio.Event,
    ) -> None:
        """
        Consume messages and call handler for each.
        
        Handler should return True if processed successfully.
        """
        if not self._sub:
            raise RuntimeError("Consumer not connected")

        logger.info("Starting message consumption")

        while not shutdown_event.is_set():
            try:
                msg = await asyncio.wait_for(
                    self._sub.next_msg(timeout=1.0),
                    timeout=2.0,
                )

                try:
                    data = json.loads(msg.data.decode())
                    await handler(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in message")
                except Exception as e:
                    logger.error(f"Handler error: {e}")

            except (NatsTimeoutError, asyncio.TimeoutError):
                # No message available, check shutdown flag
                continue
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                await asyncio.sleep(1)

        logger.info("Consumer shutdown")