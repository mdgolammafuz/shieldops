"""ShieldOps Processor - Main Entry Point.

Consumes validated certificates from NATS, detects threats, stores in PostgreSQL.

Design:
- Async for high throughput
- Graceful shutdown on SIGTERM
- Prometheus metrics
- Health endpoint
- Structured JSON logging (structlog)
"""

import asyncio
import signal
import os
import structlog
from aiohttp import web
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

from config import NATS_URL, NATS_SUBJECT, DATABASE_URL, METRICS_PORT
from consumer import Consumer
from validator import clean_domains
from detector import analyze
from repository import Repository, Threat


def configure_logging():
    """Configure structlog for JSON output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            int(os.getenv("LOG_LEVEL", "20"))  # 20=INFO, 10=DEBUG
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


configure_logging()
logger = structlog.get_logger(service="processor", version="1.0.0")

# Prometheus metrics
MESSAGES_PROCESSED = Counter(
    'processor_messages_total',
    'Total messages processed',
)
DOMAINS_ANALYZED = Counter(
    'processor_domains_total',
    'Total domains analyzed',
)
THREATS_DETECTED = Counter(
    'processor_threats_total',
    'Threats detected',
    ['keyword', 'confidence'],
)
DB_INSERTS = Counter(
    'processor_db_inserts_total',
    'Successful database inserts',
)
DB_DUPLICATES = Counter(
    'processor_db_duplicates_total',
    'Duplicate certificates (already in DB)',
)
HEALTHY = Gauge(
    'processor_healthy',
    'Processor health status',
)


class Processor:
    """Main processor application."""

    def __init__(self):
        self._consumer = Consumer(NATS_URL, NATS_SUBJECT)
        self._repository = Repository(DATABASE_URL)
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the processor."""
        logger.info(
            "starting processor",
            nats_url=NATS_URL,
            nats_subject=NATS_SUBJECT,
            metrics_port=METRICS_PORT,
        )

        # Connect to services
        await self._repository.connect()
        logger.info("connected to postgresql")

        await self._consumer.connect()
        logger.info("connected to nats")

        HEALTHY.set(1)

        # Start metrics server
        app = web.Application()
        app.router.add_get('/metrics', self._metrics_handler)
        app.router.add_get('/healthz', self._health_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', METRICS_PORT)
        await site.start()
        logger.info("metrics server started", port=METRICS_PORT)

        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal)

        # Start consuming
        try:
            await self._consumer.consume(self._process_message, self._shutdown_event)
        finally:
            await self._shutdown()

    def _handle_signal(self) -> None:
        """Handle shutdown signal."""
        logger.info("shutdown signal received")
        self._shutdown_event.set()

    async def _shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("shutting down")
        HEALTHY.set(0)
        await self._consumer.close()
        await self._repository.close()
        logger.info("shutdown complete")

    async def _process_message(self, data: dict) -> bool:
        """Process a single certificate message."""
        MESSAGES_PROCESSED.inc()

        # Extract fields
        domains = data.get('domains', [])
        fingerprint = data.get('fingerprint')
        issuer = data.get('issuer')
        not_before = data.get('not_before')
        not_after = data.get('not_after')

        if not domains or not fingerprint:
            logger.debug("skipping message", reason="missing_fields", fingerprint=fingerprint)
            return False

        # Clean domains
        cleaned = clean_domains(domains)
        DOMAINS_ANALYZED.inc(len(cleaned))

        # Analyze each domain
        for domain in cleaned:
            result = analyze(domain)

            if result.is_threat:
                threat = Threat(
                    domain=domain,
                    fingerprint=fingerprint,
                    matched_keyword=result.keyword,
                    entropy=result.entropy,
                    confidence=result.confidence,
                    issuer=issuer,
                    not_before=not_before,
                    not_after=not_after,
                )

                inserted = await self._repository.insert_threat(threat)

                if inserted:
                    DB_INSERTS.inc()
                    THREATS_DETECTED.labels(
                        keyword=result.keyword,
                        confidence=result.confidence,
                    ).inc()
                    logger.info(
                        "threat detected",
                        domain=domain,
                        keyword=result.keyword,
                        confidence=result.confidence,
                        entropy=result.entropy,
                        fingerprint=fingerprint,
                    )
                else:
                    DB_DUPLICATES.inc()
                    logger.debug("duplicate threat", fingerprint=fingerprint)

        return True

    async def _metrics_handler(self, request: web.Request) -> web.Response:
        """Prometheus metrics endpoint."""
        return web.Response(
            body=generate_latest(),
            content_type=CONTENT_TYPE_LATEST,
        )

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        db_healthy = await self._repository.health_check()
        if db_healthy:
            return web.Response(text="ok")
        return web.Response(text="unhealthy", status=503)


def main():
    """Entry point."""
    processor = Processor()
    asyncio.run(processor.start())


if __name__ == '__main__':
    main()