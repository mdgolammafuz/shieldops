# Architecture Deep Dive

## System Overview

ShieldOps is a streaming data pipeline that processes SSL certificate issuance events in real-time. The architecture prioritizes **reliability over latency** — we accept slightly delayed detection to guarantee zero data loss during traffic spikes.

---

## Data Flow

```text
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  CertStream  │────►│   Ingestor   │────►│     NATS     │────►│  Processor   │
│   (External) │     │     (Go)     │     │   (Broker)   │     │   (Python)   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │                    │                     │
                            │                    │                     │
                            ▼                    ▼                     ▼
                     WebSocket client      In-Memory Queue       Domain analysis
                     ~128Mi memory         Shock absorber        Pattern matching
                     100 certs/sec         Decouples load        PostgreSQL write
                                                                       │
                                                                       ▼
                                                               ┌──────────────┐
                                                               │ Lightweight  │
                                                               │   API & UI   │
                                                               └──────────────┘
```

### Stage 1: Ingestion

The Ingestor maintains a WebSocket connection to the Certificate Transparency aggregator. It performs minimal processing:

1. Receive certificate JSON
2. Extract domain and metadata
3. Publish to NATS
4. Continue (no blocking operations)

**Design choice:** Go was selected for its efficient WebSocket handling and low memory footprint. The entire ingestor is a lightweight, compiled binary.

### Stage 2: Buffering

NATS provides high-throughput, in-memory message queueing:

**Why not Kafka?** For this throughput (~100 msg/sec), Kafka's JVM memory requirements and operational complexity are not justified. NATS provides the necessary shock-absorption with a fraction of the hardware overhead.

### Stage 3: Processing

The Processor pulls messages from NATS and applies detection rules:

```python
# Simplified detection logic
def detect(domain: str) -> Detection | None:
    for keyword in GERMAN_BANKS + GLOBAL_BRANDS:
        if keyword in domain.lower():
            return Detection(
                domain=domain,
                keyword=keyword,
                confidence=calculate_confidence(domain, keyword)
            )
    return None
```

### Stage 4: Storage & Visualization

PostgreSQL stores detected threats with full metadata. A lightweight FastAPI service queries this database to serve a real-time HTML dashboard.

```sql
CREATE TABLE threats (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    fingerprint VARCHAR(64) UNIQUE,  -- Deduplication
    matched_keyword VARCHAR(50),
    confidence VARCHAR(20),
    entropy FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Why PostgreSQL over a time-series DB?** The query patterns are transactional (lookups, deduplication) rather than analytical. PostgreSQL's `UNIQUE` constraint handles stream deduplication efficiently natively.

---

## Reliability Patterns

### Backpressure Handling

The system handles downstream slowdowns without data loss:

```text
Normal:     Ingestor → NATS → Processor → DB
                         │
Slowdown:   Ingestor → NATS ──────────────► Processor (catching up)
                         │
                    Buffer grows
```

**Implementation:**
- NATS accumulates messages in memory during processor unavailability or scaling events.
- No complex coordination required — stateless recovery.

### Graceful Degradation

Each component can fail independently:

| Failure | Impact | Recovery |
|---------|--------|----------|
| Ingestor crash | New certs missed | Restart reconnects to CertStream instantly |
| Processor crash | Processing paused | Restart resumes pulling from NATS buffer |
| PostgreSQL down | Writes fail | Processor enters CrashLoopBackOff until DB recovers |

---

## Security Architecture

### Network Topology (Calico CNI)

```text
┌─────────────────────────────────────────────────────────────┐
│                     SHIELDOPS NAMESPACE                      │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Ingestor │───►│   NATS   │◄───│Processor │              │
│  └──────────┘    └──────────┘    └─────┬────┘              │
│       │                                 │                    │
│       │ (egress only)                   │ (egress only)     │
│       ▼                                 ▼                    │
│  ┌──────────┐                    ┌──────────┐              │
│  │ Internet │                    │PostgreSQL│              │
│  │(CertStream)                   └──────────┘              │
│  └──────────┘                          ▲                    │
│                                        │                    │
│                              ┌─────────┴─────────┐         │
│                              │   BLOCKED         │         │
│                              │ (rogue pod)       │         │
│                              └───────────────────┘         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Policy Summary

| Policy | Source | Destination | Ports |
|--------|--------|-------------|-------|
| Ingestor egress | `ingestor` | Internet | 443 (WSS) |
| Ingestor egress | `ingestor` | NATS | 4222 |
| Processor egress | `processor` | NATS | 4222 |
| Processor egress | `processor` | PostgreSQL | 5432 |
| PostgreSQL ingress | `processor` | PostgreSQL | 5432 |
| Default deny | `*` | `*` | `*` |

---

## Observability Stack

### Metrics Pipeline

```text
Application ──► Prometheus ──► Grafana
    │
    └──► Custom metrics:
         • ingestor_messages_received_total
         • processor_threats_total
         • nats_consumer_num_pending
```

### Logging Pipeline

```text
Application ──► stdout ──► Promtail ──► Loki ──► Grafana
```

---

## Deployment Model

### CI/CD with GitHub Actions

Infrastructure is provisioned via Terraform/Ansible, but application workloads are deployed via standard CI/CD pipelines targeting Google Kubernetes Engine (GKE).

```yaml
# .github/workflows/deploy.yml
name: Deploy to GKE
on:
  push:
    branches: [ "main" ]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Build & Push Images
        run: docker push us-central1-docker.pkg.dev/...
      - name: Apply Manifests
        run: kubectl apply -f kubernetes/
```

### Manual Deployment

```bash
# Apply in order (dependencies first)
kubectl apply -f kubernetes/security/
kubectl apply -f kubernetes/platform/
kubectl apply -f kubernetes/apps/
```

---

## Resource Allocation (Tuned for Stability)

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| Ingestor | 50m | 200m | 128Mi | 256Mi |
| NATS | 100m | 500m | 32Mi | 128Mi |
| Processor | 100m | 500m | 128Mi | 256Mi |
| PostgreSQL | 50m | 200m | 128Mi | 256Mi |
| Prometheus | 200m | 500m | 128Mi | 256Mi |
| Grafana | 250m | 500m | 256Mi | 512Mi |
| Loki | 200m | 500m | 128Mi | 256Mi |

**Total:** Requires a robust cluster environment (e.g., GKE `e2-standard-2` or higher) to prevent node starvation.

---

## Trade-offs

| Decision | Trade-off | Rationale |
|----------|-----------|-----------|
| Single PostgreSQL | No replication | Simplicity; threats are recoverable from CT logs. |
| In-memory NATS | Volatile buffer | Avoids complex PVC management for ephemeral stream data. |
| Custom UI/API | Bypasses Grafana | Provides an ultra-lightweight portfolio demonstration without crushing cluster memory. |
| GKE over Minikube | Cloud costs | Local ARM64 VMs cannot reliably schedule this enterprise stack; GKE provides necessary metal. |