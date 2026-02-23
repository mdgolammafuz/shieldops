# Troubleshooting Runbooks

Quick reference for common operational issues encountered in the ShieldOps cluster.

---

## 1. CrashLoopBackOff

**Symptom:** Pod repeatedly crashes, status shows `CrashLoopBackOff`.

**Diagnosis:**
```bash
# Check the dying words of the previous container
kubectl logs -n shieldops <pod-name> --previous

# Check Kubernetes scheduling events
kubectl describe pod -n shieldops <pod-name> | grep -A 10 Events
```

**Common Causes & Fixes:**

| Cause | Log Pattern | Fix |
|-------|-------------|-----|
| Missing Config | `KeyError`, `ConfigError` | Check ConfigMap/Secret mounts in YAML. |
| DB Connection | `connection refused` | Verify PostgreSQL is `1/1 Running`. |
| First-Boot Trap | `FATAL: database "shieldops" does not exist` | The PVC wasn't wiped cleanly between tests. Delete the StatefulSet, delete the PVC, and reapply. |
| Dependency Wait | `NATS connection failed` | Pod will auto-recover once NATS boots. |

**Resolution:**
```bash
# Wipe corrupted Postgres state (if caught in First-Boot Trap)
kubectl delete statefulset postgres -n shieldops
kubectl delete pvc data-postgres-0 -n shieldops
kubectl apply -f kubernetes/apps/postgres.yaml
```

---

## 2. Service Unreachable

**Symptom:** `connection refused` or `no route to host` when a pod tries to access another service.

**Diagnosis:**
```bash
# Check if the service actually has healthy endpoints routed to it
kubectl get endpoints -n shieldops <service-name>
```

**Common Causes:**

| Cause | Check | Fix |
|-------|-------|-----|
| No Endpoints | `kubectl get endpoints` shows `<none>` | The pod labels don't match the Service `selector` labels. |
| Calico Block | Traffic drops or times out | A Zero Trust NetworkPolicy is blocking the port. Add an explicit allow rule. |
| Unhealthy Pod | Pod is `0/1 Running` | Readiness probe is failing. The Service will not route traffic to it. |

---

## 3. Persistent Volume Issues



**Symptom:** PersistentVolumeClaim stuck in `Pending` state, or Database refusing to initialize.

**Diagnosis:**
```bash
# Check PVC status and provisioning errors
kubectl describe pvc -n shieldops <pvc-name>
```

**Common Causes:**

| Cause | Event Message | Fix |
|-------|---------------|-----|
| Cloud Quota | `insufficient capacity` | GCP disk quota exceeded. Request limit increase or reduce `storage` request. |
| No Provisioner| `no persistent volumes available` | Ensure GKE `standard-rwo` StorageClass is set as default. |
| Corrupted Hostpath | Postgres skips `init.sql` | On Minikube Mac ARM64, local volumes aren't always scrubbed. Use `emptyDir` for local testing, or deploy to GKE. |

---

## 4. NetworkPolicy Blocking Traffic (Zero Trust)

**Symptom:** Connection timeouts (hanging) between pods that should normally communicate.

**Diagnosis:**
```bash
# List all active Calico policies
kubectl get networkpolicy -n shieldops

# Test connectivity directly from the source pod
kubectl exec -n shieldops <source-pod> -- nc -zv <dest-service> <port>
```

**Common Causes:**

| Cause | Fix |
|-------|-----|
| Missing Egress | Source pod lacks permission to leave its network namespace. |
| Missing Ingress | Destination pod lacks permission to receive from that specific source label. |
| CoreDNS Blocked| Pod cannot resolve `postgres` because port 53 UDP is blocked. |

**Resolution:**
Every pod must explicitly whitelist the exact port and destination app label. Review `kubernetes/security/`.

---

## 5. High Memory Usage & Node Starvation



**Symptom:** Pod status is `OOMKilled` (Exit Code 137), or the entire Node flips to `NotReady`.

**Diagnosis:**
```bash
# Check pod resource usage
kubectl top pods -n shieldops

# Check node pressure (Look for MemoryPressure)
kubectl describe node | grep -A 5 Conditions
```

**Common Causes:**

| Component | Log/Event | Fix |
|-----------|-----------|-----|
| Any Pod | `command terminated with exit code 137` | Container hit its hard memory limit. Increase `resources.limits.memory` in YAML. |
| Node | `NodeNotReady` / `Kubelet stopped posting node status` | The cluster lacks physical RAM for the enterprise stack. Migrate from Minikube to GKE `e2-standard-2` nodes. |
| Grafana | Endless restarts, `SIGTERM` | CPU starvation during boot. Increase `requests.cpu` to at least `250m`. |

**Resolution:**
```bash
# Verify the active limits on the dying pod
kubectl describe pod -n shieldops <pod> | grep -A 3 Limits
```

---

## Quick Reference Commands

```bash
# Overall cluster triage
kubectl get pods -n shieldops -o wide -w
kubectl get events -n shieldops --sort-by='.lastTimestamp' | tail -20

# Component-specific autopsy
kubectl logs -n shieldops deploy/processor --previous
kubectl logs -n shieldops statefulset/postgres --previous

# Network debugging (Launch a Swiss Army Knife container)
kubectl run netshoot --rm -it --image=nicolaka/netshoot -n shieldops -- bash
```

---

## Escalation Checklist

Before declaring a catastrophic failure, verify:

- [ ] Checked the dying words of the pod (`kubectl logs --previous`)
- [ ] Checked for Exit Code 137 or OOMKilled in events
- [ ] Verified Postgres is `1/1 Running` and not trapped in a first-boot error
- [ ] Confirmed the node has sufficient physical RAM (`kubectl describe node`)