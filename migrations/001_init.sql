-- ShieldOps Database Schema
-- Version: 001_init

-- Threats table: Detected phishing domains
CREATE TABLE IF NOT EXISTS threats (
    id              BIGSERIAL PRIMARY KEY,
    domain          VARCHAR(255) NOT NULL,
    fingerprint     VARCHAR(64) UNIQUE NOT NULL,
    matched_keyword VARCHAR(50) NOT NULL,
    entropy         NUMERIC(5,3) NOT NULL,
    confidence      VARCHAR(10) NOT NULL,
    issuer          VARCHAR(255),
    not_before      TIMESTAMPTZ,
    not_after       TIMESTAMPTZ,
    received_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints for data integrity
    CONSTRAINT valid_confidence CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT valid_entropy CHECK (entropy >= 0 AND entropy <= 5),
    CONSTRAINT valid_domain_length CHECK (char_length(domain) BETWEEN 4 AND 255)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_threats_created ON threats(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_threats_keyword ON threats(matched_keyword);
CREATE INDEX IF NOT EXISTS idx_threats_confidence ON threats(confidence);
CREATE INDEX IF NOT EXISTS idx_threats_domain ON threats(domain);

-- Comments for documentation
COMMENT ON TABLE threats IS 'Detected phishing domains from CertStream';
COMMENT ON COLUMN threats.fingerprint IS 'SHA256 fingerprint of SSL certificate (unique)';
COMMENT ON COLUMN threats.entropy IS 'Shannon entropy of domain (0-5, higher = more random)';
COMMENT ON COLUMN threats.confidence IS 'Detection confidence: high, medium, low';