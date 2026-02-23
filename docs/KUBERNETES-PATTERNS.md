# Operational Excellence & Kubernetes Patterns

This document outlines the production-grade Kubernetes design patterns and Site Reliability Engineering (SRE) practices implemented within the ShieldOps architecture.

---

## Core Engineering Pillars

| Domain | Implementation Focus | Status |
|--------|----------------------|--------|
| **Security & Isolation** | Zero Trust NetworkPolicies, Strict RBAC | ✅ Enforced |
| **Workload Resilience** | Automated recovery, precise resource boundaries | ✅ Enforced |
| **Observability** | Centralized metrics and log aggregation | ✅ Enforced |
| **Storage & State** | Decoupled state, ephemeral processing | ✅ Enforced |

---

## 1. Security & Cluster Architecture

The cluster is designed assuming a hostile internal network environment.

| Pattern | Implementation |
|-------|----------------|
| **Least Privilege (RBAC)** | Dedicated ServiceAccounts per workload. Roles and RoleBindings strictly limited to the `shieldops` namespace. |
| **Pod Security Contexts** | Containers enforce `runAsNonRoot: true`, drop all Linux capabilities (`drop: ["ALL"]`), and utilize `RuntimeDefault` seccomp profiles. |
| **Secret Management** | No hardcoded credentials. Passwords and connection strings are injected via Kubernetes Secrets as environment variables or read-only volume mounts. |

**Relevant definitions:** `kubernetes/security/rbac.yaml`

---

## 2. Workload Resilience & Scheduling

Workloads are designed to survive node starvation, dependency failures, and network partitions.

| Pattern | Implementation |
|-------|----------------|
| **Resource Quotas** | Every container specifies exact CPU/Memory `requests` (for scheduling) and `limits` (to prevent node OOM crashes). |
| **Lifecycle Probes** | • *Startup Probes:* Allow slow initializations (e.g., database boot) without premature termination.<br>• *Liveness Probes:* Catch deadlocks.<br>• *Readiness Probes:* Ensure traffic is only routed to fully initialized pods. |
| **Graceful Degradation** | `preStop` hooks ensure in-flight messages are safely drained or negatively acknowledged before a pod terminates. |

**Relevant definitions:** `kubernetes/apps/*.yaml`

---

## 3. Services & Zero Trust Networking

Internal communication is strictly whitelisted at the network layer.

| Pattern | Implementation |
|-------|----------------|
| **Microsegmentation** | 11 NetworkPolicies (managed via Calico/Dataplane V2) enforce a strict `default-deny-all` baseline. |
| **Explicit Whitelisting** | Pods can only communicate if both the egress of the source and the ingress of the destination explicitly match label selectors. |
| **Internal Routing** | `ClusterIP` services abstract pod IP churn, providing stable internal DNS resolution via CoreDNS. |

**Relevant definitions:** `kubernetes/security/network-policies.yaml`

---

## 4. Storage and State Management

Stateful components are isolated from ephemeral processing nodes.

| Pattern | Implementation |
|-------|----------------|
| **Persistent Volumes (PV/PVC)** | PostgreSQL utilizes standard block storage claims ensuring database state survives pod rescheduling. |
| **Ephemeral Buffering** | NATS operates entirely in-memory to provide high-throughput shock absorption without the latency of disk I/O. |
| **Stateless Processing** | The Python processor and Go ingestor are entirely stateless, allowing them to be aggressively destroyed and recreated without data loss. |

**Relevant definitions:** `kubernetes/apps/postgres.yaml`

---

## 5. Troubleshooting & SRE Methodology

The architecture is built for rapid diagnosis during 3 AM incidents.

| Pattern | Implementation |
|-------|----------------|
| **Centralized Logging** | Promtail streams all stdout/stderr to Loki, preventing the need to SSH into nodes or exec into dying pods. |
| **Telemetry** | Prometheus scrapes custom `/metrics` endpoints, exposing granular data like `ingestor_messages_received_total` and `nats_consumer_num_pending`. |
| **Runbooks** | Documented procedures for standard failure modes (`CrashLoopBackOff`, OOMKilled/Exit Code 137, Network Drops). |

**Relevant definitions:** `kubernetes/platform/`