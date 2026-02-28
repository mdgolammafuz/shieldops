# ShieldOps

**Real-time phishing detection infrastructure targeting German financial institutions.**

A Kubernetes platform that processes live SSL certificates from Certificate Transparency logs, detecting brand impersonation attacks within 60 seconds of domain registration.

---

## The Problem

Phishing attacks targeting (German) banks (Sparkasse, Volksbank, Deutsche Bank) typically register domains and obtain SSL certificates hours before launching campaigns. Traditional detection methods rely on blocklists updated days later.

**The gap:** 24-72 hours between domain registration and blocklist inclusion.

## The Solution

This platform monitors the Certificate Transparency log stream in real-time, detecting suspicious domains the exact moment their SSL certificates are issued.

`Certificate Issued → Detected in <60 seconds → Alert Generated`

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         SHIELDOPS PLATFORM                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  INGESTION          BUFFERING           PROCESSING         STORAGE      │
│                                                                         │
│  ┌─────────┐       ┌─────────┐        ┌─────────┐       ┌─────────┐   │
│  │CertStream│──────►│  NATS   │───────►│Processor│──────►│PostgreSQL│   │
│  │WebSocket │       │ Message │        │ Python  │       │ Database │   │
│  │  (Go)   │       │ Broker  │        │ Engine  │       │         │   │
│  └─────────┘       └─────────┘        └─────────┘       └─────────┘   │
│       │                 │                  │                  │         │
│       └─────────────────┴──────────────────┴──────────────────┘         │
│                              │                                          │
│                              ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    OBSERVABILITY STACK                           │   │
│  │                                                                  │   │
│  │   Prometheus ◄────── Metrics ──────► Grafana                     │   │
│  │                                                                  │   │
│  │   Loki ◄───────── Logs ───────────► Promtail                     │   │
│  │                                                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    SECURITY LAYER (CALICO)                       │   │
│  │                                                                  │   │
│  │   • Strict NetworkPolicies (Zero Trust / Default Deny)           │   │
│  │   • RBAC with least-privilege ServiceAccounts                    │   │
│  │   • PodDisruptionBudgets & Resource Quotas                       │   │
│  │                                                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Engineering Decisions

### 1. Decoupled Ingestion & Processing
- **Ingestor (Go):** High-throughput WebSocket handling, minimal memory footprint, single binary deployment tailored for speed.
- **Processor (Python):** Domain analysis logic benefits from rapid iteration and extensive string manipulation libraries for calculating entropy and typosquatting scores.
- **Buffer (NATS):** Decouples the firehose from the processor. If the processor scales down or crashes, NATS absorbs the traffic spikes, preventing data loss.

### 2. Zero Trust Networking (Calico)
In a compromised cluster, lateral movement must be physically blocked by the CNI. Every pod has explicit ingress/egress rules.

```yaml
# PostgreSQL strictly accepts connections ONLY from the Processor pod
ingress:
  - from:
      - podSelector:
          matchLabels:
            app: processor
    ports:
      - port: 5432
```
A rogue pod attempting database or broker access is blocked at the TCP/IP level.

---

## Infrastructure as Code

### Provisioning (Terraform)
Automated provisioning of Google Cloud Platform (GCP) resources to host the cluster.

```hcl
# Two e2-small instances on GCP
resource "google_compute_instance" "k3s" {
  count        = 2
  machine_type = "e2-small"  # 2 vCPU, 2GB RAM
}
```

### Configuration (Ansible)
Automated bootstrapping of the Kubernetes environment and system hardening.

```yaml
# K3s cluster setup with hardened defaults
- name: Install K3s server
  roles:
    - common        # System hardening
    - k3s-server    # Control plane
    - k3s-agent     # Worker nodes
```

---

## Security Posture

| Control | Implementation |
|---------|----------------|
| **Network Isolation** | 11 Calico NetworkPolicies, strict Default-Deny baseline |
| **Authentication** | Dedicated ServiceAccount per workload |
| **Authorization** | RBAC roles strictly scoped to the `shieldops` namespace |
| **Runtime** | Non-root containers, dropped capabilities (`drop: ["ALL"]`) |
| **Secrets** | Kubernetes Secrets mapped as volumes/env vars |

---

## Project Structure

```text
aerocast/
├── infrastructure/
│   ├── terraform/          # GCP instance provisioning
│   └── ansible/            # K3s cluster bootstrapping
├── src/
│   ├── ingestor/           # Go WebSocket client
│   ├── processor/          # Python detection engine
│   └── api/                # Lightweight UI/API
├── kubernetes/
│   ├── apps/               # Core workloads (Ingestor, Processor, DB, NATS)
│   ├── platform/           # Observability (Prometheus, Grafana, Loki)
│   └── security/           # Zero Trust NetworkPolicies & RBAC
├── tests/                  # Automated verification suite
│   ├── verify_infrastructure.sh
│   ├── verify_application_layer.sh
│   └── verify_observability_security.sh
└── .github/workflows/      # CI/CD Pipelines
```

---

## Deployment & Verification

```bash
# 1. Provision infrastructure
cd infrastructure/terraform && terraform apply

# 2. Configure cluster
cd ../ansible && ansible-playbook playbooks/site.yml

# 3. Apply Kubernetes Manifests
kubectl apply -f kubernetes/security/
kubectl apply -f kubernetes/platform/
kubectl apply -f kubernetes/apps/

# 4. Run the Verification Suite
chmod +x tests/*.sh
./tests/verify_infrastructure.sh
./tests/verify_application_layer.sh
./tests/verify_observability_security.sh
```

---
## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture Deep Dive](ARCHITECTURE.md) | Component interactions, data flow |
| [Backpressure Demo](BACKPRESSURE.md) | Zero data loss demonstration |
| [Zero Trust Demo](ZERO-TRUST.md) | Network isolation verification |
| [Troubleshooting Runbooks](TROUBLESHOOTING.md) | Common failure scenarios |
| [KUBERNETES Patterns](KUBERNETES-PATTERNS.md) | Kubernetes design patterns |

---
## Technologies

| Layer | Tools |
|-------|-------|
| **Infrastructure** | Terraform, Ansible, GCP |
| **Cluster** | K3s |
| **Runtime** | Go 1.22, Python 3.12, Docker |
| **Messaging** | NATS |
| **Storage** | PostgreSQL 16 |
| **Observability** | Prometheus, Grafana, Loki, Promtail |
| **Security** | Calico CNI |

---

*Built as a side project demonstrating production-grade Kubernetes platform engineering, SRE best practices, and distributed systems architecture.*