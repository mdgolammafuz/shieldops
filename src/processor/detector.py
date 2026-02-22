"""Threat detection logic.

Detection strategy:
1. Check allowlist (skip real domains like sparkasse.de)
2. Match against keyword lists
3. Calculate Shannon entropy (randomness indicator)
4. Assign confidence level
"""

import math
import re
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class ThreatResult:
    """Immutable result of threat analysis."""
    is_threat: bool
    keyword: Optional[str]
    entropy: float
    confidence: str  # 'high', 'medium', 'low'


# German banks (high priority targets)
GERMAN_BANKS = frozenset({
    'sparkasse', 'volksbank', 'commerzbank', 'postbank',
    'dkb', 'deutsche-bank', 'hypovereinsbank', 'ing-diba',
    'targobank', 'sparda', 'apobank', 'santander',
})

# Global brand targets
GLOBAL_BRANDS = frozenset({
    'paypal', 'amazon', 'microsoft', 'apple', 'google',
    'netflix', 'facebook', 'instagram', 'whatsapp', 'linkedin',
    'dropbox', 'adobe', 'zoom', 'slack', 'github',
})

# Phishing patterns
PHISHING_PATTERNS = frozenset({
    'login', 'signin', 'sign-in', 'logon',
    'secure', 'security', 'verify', 'verification',
    'account', 'accounts', 'update', 'confirm',
    'alert', 'suspend', 'locked', 'password',
    'credential', 'authenticate', 'wallet',
})

# Allowlist - real domains to skip (reduces false positives)
ALLOWLIST_PATTERNS = [
    re.compile(r'\.google\.com$'),
    re.compile(r'\.google\.[a-z]{2,3}$'),  # google.de, google.co.uk
    re.compile(r'\.microsoft\.com$'),
    re.compile(r'\.amazon\.com$'),
    re.compile(r'\.amazon\.[a-z]{2,3}$'),
    re.compile(r'\.apple\.com$'),
    re.compile(r'\.facebook\.com$'),
    re.compile(r'\.instagram\.com$'),
    re.compile(r'\.sparkasse\.de$'),
    re.compile(r'\.volksbank\.de$'),
    re.compile(r'\.commerzbank\.de$'),
    re.compile(r'\.deutsche-bank\.de$'),
    re.compile(r'\.postbank\.de$'),
    re.compile(r'\.dkb\.de$'),
    re.compile(r'\.ing\.de$'),
    re.compile(r'\.paypal\.com$'),
    re.compile(r'\.netflix\.com$'),
    re.compile(r'\.github\.com$'),
    re.compile(r'\.cloudflare\.com$'),
    re.compile(r'\.amazonaws\.com$'),
    re.compile(r'\.letsencrypt\.org$'),
]

# All keywords for matching
ALL_KEYWORDS = GERMAN_BANKS | GLOBAL_BRANDS | PHISHING_PATTERNS


def analyze(domain: str) -> ThreatResult:
    """Analyze a domain for phishing indicators."""
    # Skip allowlisted domains
    for pattern in ALLOWLIST_PATTERNS:
        if pattern.search(domain):
            return ThreatResult(False, None, 0.0, 'low')

    # Find keyword match
    matched = _find_keyword(domain)
    if not matched:
        return ThreatResult(False, None, 0.0, 'low')

    # Calculate entropy
    entropy = _calculate_entropy(domain)

    # Determine confidence
    confidence = _determine_confidence(matched, entropy, domain)

    return ThreatResult(True, matched, round(entropy, 3), confidence)


def _find_keyword(domain: str) -> Optional[str]:
    """Find matching keyword by priority: Banks > Brands > Generic."""
    # Priority 1: High-value targets (High Confidence)
    for keyword in GERMAN_BANKS:
        if keyword in domain:
            return keyword
            
    # Priority 2: Global brands (Medium Confidence)
    for keyword in GLOBAL_BRANDS:
        if keyword in domain:
            return keyword
            
    # Priority 3: Generic phishing patterns (Low Confidence)
    for keyword in PHISHING_PATTERNS:
        if keyword in domain:
            return keyword
            
    return None

def _calculate_entropy(text: str) -> float:
    """Calculate Shannon entropy. Higher = more random = more suspicious."""
    if not text:
        return 0.0

    freq = {}
    for char in text:
        freq[char] = freq.get(char, 0) + 1

    length = len(text)
    entropy = -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )
    return entropy


def _determine_confidence(keyword: str, entropy: float, domain: str) -> str:
    """Determine confidence level based on multiple factors."""
    # Base confidence from keyword type
    if keyword in GERMAN_BANKS:
        base = 'high'
    elif keyword in GLOBAL_BRANDS:
        base = 'medium'
    else:
        base = 'low'

    # Boost if high entropy (random-looking)
    if entropy > 3.8:
        if base == 'low':
            return 'medium'
        return 'high'

    # Boost if many subdomains
    if domain.count('.') >= 3:
        if base == 'low':
            return 'medium'

    return base