"""Configuration from environment variables.

Supports both:
- Direct env vars (local development)
- File-mounted secrets (Kubernetes - security best practice)
"""

import os
from pathlib import Path


def _read_secret(env_var: str, file_env_var: str, default: str) -> str:
    """
    Read secret from file if available, otherwise from env var.
    
    Priority:
    1. File path in {file_env_var} (Kubernetes file-mounted secret)
    2. Direct value in {env_var} (local development)
    3. Default value
    """
    # Check for file-mounted secret first
    file_path = os.getenv(file_env_var)
    if file_path:
        path = Path(file_path)
        if path.exists():
            return path.read_text().strip()
    
    # Fall back to direct env var
    return os.getenv(env_var, default)


# NATS
NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")
NATS_SUBJECT = os.getenv("NATS_SUBJECT", "certs.validated")

# PostgreSQL (supports file-mounted secret)
DATABASE_URL = _read_secret(
    env_var="DATABASE_URL",
    file_env_var="DATABASE_URL_FILE",
    default="postgresql://shieldops:shieldops-secret-2024@postgres:5432/shieldops"
)

# Metrics
METRICS_PORT = int(os.getenv("METRICS_PORT", "8080"))

# Processing
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))