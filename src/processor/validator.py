"""Domain cleaning and validation.

Rules:
- Remove wildcard prefix (*.)
- Lowercase
- Strip whitespace  
- Skip IP addresses
- Skip too short (<4) or too long (>255)
- Skip invalid characters
- Decode punycode (IDN)
- Deduplicate
"""

import re
from typing import Optional

# Valid domain pattern (after cleaning)
DOMAIN_PATTERN = re.compile(
    r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)*$'
)

# IP address pattern
IP_PATTERN = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')


def clean_domains(raw_domains: list[str]) -> list[str]:
    """Clean and validate a list of domains. Returns deduplicated list."""
    cleaned = []
    seen = set()

    for domain in raw_domains:
        if clean := clean_domain(domain):
            if clean not in seen:
                cleaned.append(clean)
                seen.add(clean)

    return cleaned


def clean_domain(domain: str) -> Optional[str]:
    """Clean and validate a single domain. Returns None if invalid."""
    if not domain or not isinstance(domain, str):
        return None

    # Remove wildcard prefix
    domain = domain.lstrip('*.')

    # Lowercase and strip
    domain = domain.lower().strip()

    # Skip empty after cleaning
    if not domain:
        return None

    # Skip IP addresses
    if IP_PATTERN.match(domain):
        return None

    # Length check (DNS limits)
    if len(domain) < 4 or len(domain) > 255:
        return None

    # Decode punycode (IDN) - handles domains like xn--sprkasse-q2a.de
    try:
        # Encode to ASCII then decode as IDNA
        domain = domain.encode('ascii').decode('idna')
    except (UnicodeError, UnicodeDecodeError):
        pass  # Keep original if decode fails

    # Validate format
    if not DOMAIN_PATTERN.match(domain):
        return None

    return domain