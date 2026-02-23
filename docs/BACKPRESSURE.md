# Demo: Backpressure & System Resilience

## What This Demonstrates

Zero data loss during downstream micro-outages. When the processor crashes or is scaled down, the NATS message broker buffers the incoming Certificate Transparency firehose in-memory. When the processor recovers, it drains the backlog without manual intervention.

**Key insight:** Production reliability isn't about preventing failures — it's about recovering gracefully without dropping packets.



---

## The Scenario

```text
Timeline:
─────────────────────────────────────────────────────────────────────►
     │                    │                    │
     │                    │                    │
   Normal              Processor            Processor
   operation           stopped              restarted
     │                    │                    │
     ▼                    ▼                    ▼
  Certs flow          Buffer grows         Backlog
  through             (in-memory)          processed
```

---

## Setup

Instead of relying on third-party CLI tools, we will observe the raw telemetry emitted directly by your Go and Python microservices.

Open two separate terminal windows.

```bash
# Terminal 1: Watch the Ingestor Firehose (Incoming)
watch -n 2 'kubectl exec -n shieldops deploy/ingestor -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^ingestor_messages_received_total"'

# Terminal 2: Watch the Processor (Outgoing/Processed)
watch -n 2 'kubectl exec -n shieldops deploy/processor -- wget -qO- http://localhost:8080/metrics 2>/dev/null | grep "^processor_threats_total"'
```

---

## Execute Demo

### Step 1: Verify Normal Operation

Look at both terminals. You should see the `ingestor_messages_received_total` climbing rapidly, and the `processor_threats_total` climbing alongside it. The pipeline is flowing.

### Step 2: Simulate a Downstream Outage

We will simulate a scenario where the Python processing engine crashes or is taken offline for an emergency patch.

```bash
kubectl scale deploy -n shieldops processor --replicas=0
```

### Step 3: Observe the Shock Absorber

Look at your terminals. 
* **Terminal 2 (Processor):** Will throw connection refused errors because the pod is dead.
* **Terminal 1 (Ingestor):** The `ingestor_messages_received_total` metric **continues to climb**. 

The Go WebSocket client is still ripping certificates from the internet and pushing them into the NATS in-memory buffer. The ingestor does not crash just because the processor is down.

### Step 4: Recover the System

Bring the processor back online.

```bash
kubectl scale deploy -n shieldops processor --replicas=1
```

### Step 5: Watch the Catch-Up Phase

Once the processor boots and connects to PostgreSQL, watch Terminal 2. The metrics will reappear, and the processor will immediately begin draining the accumulated NATS buffer, processing messages at a higher-than-normal rate until the queue is cleared.

---

## Expected Results

| Phase | Ingestor State | Processor State | NATS Buffer |
|-------|----------------|-----------------|-------------|
| Normal | ~100 msgs/sec | Active | ~0 |
| Outage | ~100 msgs/sec | Offline (0 Pods)| Growing rapidly |
| Recovery | ~100 msgs/sec | Booting | Draining |
| Stabilized | ~100 msgs/sec | Active | ~0 |

---

## Why This Matters

In production systems, downstream components inevitably fail:
- Database maintenance windows lock tables.
- Node upgrades trigger pod evictions.
- Memory pressure causes OOM kills (Exit Code 137).

Without an decoupled buffer, these failures cause immediate **data loss** because the WebSocket stream cannot be paused. 

By inserting NATS between the Go and Python layers, the architecture absorbs the shock.
- Messages are held in memory.
- Recovery is automatic and stateless.
- No human intervention is required to restart the pipeline.

---

## Cleanup

```bash
# Ensure processor is running at standard capacity
kubectl scale deploy -n shieldops processor --replicas=1
```