# ShieldOps

[![ShieldOps CI/CD Pipeline](https://github.com/mdgolammafuz/shieldops/actions/workflows/main.yml/badge.svg)](https://github.com/mdgolammafuz/shieldops/actions/workflows/main.yml)
[View Live UI](http://35.242.213.243/)

**Cloud-Native Threat Intelligence Platform.**

A Kubernetes DevSecOps platform that processes live Certificate Transparency (CT) logs to detect brand impersonation and zero-day phishing infrastructure within seconds of domain registration.

This project is built to demonstrate platform engineering, continuous deployment with ephemeral testing, Zero-Trust networking, and distributed stateful workloads.

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

## Technical Approach

* **Go for Concurrency:** Go was chosen for the ingestion and processing services to efficiently handle multiple concurrent network requests and high-volume data streams without heavy resource overhead.
* **NATS over Kafka:** NATS was selected as the central messaging nervous system for its simplicity, lightweight deployment footprint, and highly performant pub/sub mechanics, which align well with the immediate routing needs of this pipeline.
* **Containerized Microservices:** The system is broken down into isolated Docker containers deployed on Kubernetes. This approach separates the concerns of ingestion, processing, and the UI, making it easier to manage dependencies and scale individual components.

* **Zero-Trust Security & IAM:**
  * **Network Isolation:** Calico NetworkPolicies enforce a strict default-deny baseline. Lateral movement is blocked at the CNI level (e.g., PostgreSQL natively rejects all TCP traffic except ingress originating directly from the Processor pod).
  * **Workload Identity Federation (WIF):** The CI/CD pipeline authenticates to GCP entirely via short-lived OIDC tokens, mitigating the security risks associated with long-lived service account JSON keys.
  * **Hardened Runtime:** Application pods execute with `runAsNonRoot: true`, read-only root filesystems, and explicitly dropped Linux capabilities (`drop: ["ALL"]`).

* **Infrastructure as Code (Hybrid Capability):** The infrastructure is designed to be environment-agnostic:
  * **Managed Cloud:** Terraform provisions the VPC, Subnets, and Google Kubernetes Engine (GKE) clusters.
  * **Edge/Bare-Metal:** Ansible playbooks securely bootstrap K3s clusters on raw Linux virtual machines, maintaining self-managed control-plane capability.

* **Self-Hosted Stateful Workloads:** NATS and PostgreSQL are deployed natively using StatefulSets, PersistentVolumeClaims, and dynamic ConfigMaps to ensure strict control over the storage layer and avoid cloud vendor lock-in.

---
### The DevSecOps Pipeline (CI/CD)

The GitHub Actions pipeline enforces a strict "shift-left" testing paradigm using ephemeral infrastructure to validate changes before production rollouts.

```text
1. Code Push (Main)
       │
       ▼
2. Static Analysis & Linting (Flake8, GolangCI, Hadolint)
       │
       ▼
3. IaC Security Scan (Trivy - CRITICAL/HIGH vulnerabilities)
       │
       ▼
4. Ephemeral Infrastructure (KinD - Kubernetes in Docker)
       │   ├─ Builds local Docker images
       │   └─ Deploys full application stack dynamically
       ▼
5. SRE Verification Suite (Integration Testing)
       │   ├─ verify_infrastructure.sh (Node/Namespace readiness)
       │   ├─ verify_application_layer.sh (Pod lifecycles, Health endpoints)
       │   └─ verify_observability_security.sh (Zero-Trust network enforcement)
       ▼
6. Production Deployment (GKE)
           ├─ Authenticates via Workload Identity Federation (Keyless)
           ├─ Pushes to Google Artifact Registry (GAR)
           └─ Executes rollout to Managed Kubernetes Cluster
```
---

## Detection Engine & Trade-offs

The Processor microservice relies on static heuristics—calculating Shannon entropy and enforcing lexical regex boundaries—to detect typosquatting and Domain Generation Algorithms (DGAs) targeting global brands.

**Architectural Trade-off**:
While highly performant with minimal memory footprint, static heuristics inherently produce false positives when analyzing legitimate, auto-generated cloud infrastructure (e.g., internal AWS/Azure routing fabrics or CDN endpoints).

**Future Iteration**:
To improve detection accuracy and reduce false positives, the static allowlist will be replaced with dynamic integration of the Tranco/Alexa Top 1M domains, accompanied by asynchronous validation against external threat intelligence APIs (e.g., VirusTotal) via a dedicated worker queue.

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
shieldops/
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

### Prerequisites
* Docker & Docker Compose
* Kubernetes (Minikube / kind)
* Go (1.21+)

### Running the Project

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/mdgolammafuzgm/shieldops.git](https://github.com/mdgolammafuz/shieldops.git)
    cd shieldops
    ```

2.  **Provision the infrastructure:**
    Ensure your Kubernetes cluster is running, then apply the base configurations for NATS and the application deployments:
    ```bash
    kubectl apply -f kubernetes/
    ```

3.  **Verify Deployment:**
    Run the verification script to ensure all pods are running and security/observability configurations are properly attached:
    ```bash
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