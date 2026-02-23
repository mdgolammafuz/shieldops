# Demo: Zero Trust Network Security

## What This Demonstrates

Network isolation via strict Kubernetes NetworkPolicies. A compromised pod cannot access the database or message broker, even within the same namespace.

**Key insight:** Defense in depth — assume breach, limit the blast radius.



---

## The Scenario

```text
┌─────────────────────────────────────────────────────────────┐
│                   SHIELDOPS NAMESPACE                        │
│                                                              │
│   ┌──────────┐                         ┌──────────┐         │
│   │ Processor│────────────────────────►│PostgreSQL│         │
│   │ (allowed)│                         │          │         │
│   └──────────┘                         └──────────┘         │
│                                              ▲               │
│   ┌──────────┐                               │               │
│   │  Hacker  │───────────X───────────────────┘               │
│   │ (blocked)│     NetworkPolicy                             │
│   └──────────┘                                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Setup

```bash
# Verify NetworkPolicies are in place
kubectl get networkpolicies -n shieldops
# Expected: 11 policies including default-deny-all, allow-postgres-ingress
```

---

## Execute Demo

### Step 1: Verify Legitimate Access Works

```bash
# The Processor pod is explicitly whitelisted to reach PostgreSQL
kubectl exec -n shieldops deploy/processor -- \
  python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('postgres', 5432)); print('SUCCESS')"
# Expected Output: SUCCESS
```

### Step 2: Attempt Unauthorized Access

```bash
# Deploy a "rogue" pod (simulating a compromised workload)
kubectl run hacker -n shieldops --rm -it --image=busybox \
  --restart=Never -- nc -zv postgres 5432
```

### Step 3: Observe the Block

```text
Expected output:
nc: postgres (10.96.x.x:5432): Connection timed out
pod "hacker" deleted
```

The connection attempt times out because the Calico CNI silently drops packets from pods that do not possess the `app: processor` label. 

---

## How It Works

### The Default Deny Policy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: shieldops
spec:
  podSelector: {}          # Applies to ALL pods
  policyTypes:
  - Ingress
  - Egress
  # No rules = silently deny all traffic
```

### The Explicit Allow for the Processor

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-postgres-ingress
  namespace: shieldops
spec:
  podSelector:
    matchLabels:
      app: postgres        # Applies to the PostgreSQL pod
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: processor   # ONLY the processor can connect
    ports:
    - protocol: TCP
      port: 5432
```

### Why the Hacker Pod is Blocked

1. The hacker pod has no `app` label.
2. PostgreSQL's ingress policy strictly demands `app: processor`.
3. The `default-deny-all` policy blocks everything not explicitly allowed.
4. The connection times out (No ICMP unreachable response — strictly silent drop).

---

## Policy Inventory

| Policy | Effect |
|--------|--------|
| `default-deny-all` | Baseline: Block everything in the namespace |
| `allow-dns` | All pods can resolve CoreDNS (Port 53 UDP/TCP) |
| `allow-ingestor-egress` | Ingestor → Internet (CertStream WSS) |
| `allow-ingestor-to-nats` | Ingestor → NATS |
| `allow-processor-to-nats` | Processor → NATS |
| `allow-processor-to-postgres` | Processor → PostgreSQL |
| `allow-postgres-ingress` | Only processor reaches PostgreSQL |
| `allow-prometheus-egress` | Prometheus scrapes all internal pods |
| `allow-grafana-egress` | Grafana → Prometheus, Loki |
| `allow-promtail-egress` | Promtail → Loki |
| `allow-loki-ingress` | Promtail, Grafana → Loki |

---

## Attack Scenarios Blocked

| Attack Vector | Blocked By |
|---------------|------------|
| Compromised pod exfiltrating data | Default egress deny |
| Lateral movement to database | PostgreSQL ingress allow-list |
| DNS tunneling to unauthorized domains | Egress restricted to known external services |
| Pod-to-pod network scanning | Default deny between all workloads |

---

## Troubleshooting

### Policy Not Enforcing?

```bash
# Verify your cluster's Container Network Interface (CNI) supports NetworkPolicies.
# If running on Minikube, ensure it was started with Calico:
minikube start --cni=calico

# Google Kubernetes Engine (GKE) supports NetworkPolicies natively when Dataplane V2 is enabled.
```

### Legitimate Traffic Blocked?

```bash
# Check if the pod labels actually match the policy selectors
kubectl get pods -n shieldops --show-labels

# Verify the exact policy selector constraints
kubectl describe networkpolicy -n shieldops allow-postgres-ingress
```

---

## Why This Matters

Traditional perimeter security assumes a trusted internal network. In Kubernetes:
- Pods from different teams share underlying physical nodes.
- Compromised containers can scan the flat internal network.
- Service discovery automatically exposes internal endpoints via DNS.

NetworkPolicies implement **microsegmentation** — every workload possesses explicit, auditable communication rules at the TCP/IP level, ensuring a breach of the Ingestor does not equal a breach of the Database.