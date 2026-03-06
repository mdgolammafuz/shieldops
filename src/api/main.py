import os
import asyncpg
import httpx
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="ShieldOps Threat Radar")

DB_SECRET_FILE = "/etc/secrets/database-url"
# Use the environment variable injected by Kubernetes, defaulting to the correct service name and port
BASE_PROM_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-server:80")
PROMETHEUS_URL = f"{BASE_PROM_URL}/api/v1/query"

def get_db_url():
    if os.path.exists(DB_SECRET_FILE):
        with open(DB_SECRET_FILE, "r") as f:
            return f.read().strip()
    return "postgresql://shieldops:shieldops-secret-2024@postgres:5432/shieldops"

async def fetch_prom_metric(query: str, default_val="0.0"):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(PROMETHEUS_URL, params={"query": query}, timeout=2.0)
            data = resp.json()
            if data.get("status") == "success" and data["data"]["result"]:
                return str(round(float(data["data"]["result"][0]["value"][1]), 2))
    except Exception:
        pass
    return default_val

async def fetch_top_category():
    """Extracts the label of the highest targeted category from Prometheus."""
    query = 'topk(1, sum by (keyword) (rate(processor_threats_total[24h])))'
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(PROMETHEUS_URL, params={"query": query}, timeout=2.0)
            data = resp.json()
            if data.get("status") == "success" and data["data"]["result"]:
                res = data["data"]["result"][0]
                brand = res["metric"].get("keyword", "N/A").capitalize()
                return brand
    except Exception:
        pass
    return "N/A"

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    with open("index.html", "r") as f:
        return f.read()

@app.get("/api/data")
async def get_dashboard_data():
    try:
        # 1. Fetch Database Threats
        conn = await asyncpg.connect(get_db_url())
        rows = await conn.fetch(
            """
            SELECT domain, matched_keyword, entropy, confidence, not_before, created_at, received_at 
            FROM threats
            ORDER BY created_at DESC 
            LIMIT 50;
            """
        )
        await conn.close()

        threats = []
        latencies = []
        for row in rows:
            threat_dict = dict(row)
            
            # Calculate Latency: Time between ingestion and our database write
            if row['received_at'] and row['created_at']:
                latency_seconds = (row['created_at'] - row['received_at']).total_seconds()
                if latency_seconds > 0:
                    latencies.append(latency_seconds)
                threat_dict['latency'] = round(latency_seconds, 2)
            else:
                threat_dict['latency'] = "N/A"
            
            threat_dict['not_before'] = row['not_before'].isoformat() if row['not_before'] else None
            threat_dict['created_at'] = row['created_at'].isoformat() if row['created_at'] else None
            threats.append(threat_dict)

        avg_latency = round(sum(latencies)/len(latencies), 2) if latencies else 0.0

        # 2. Fetch Prometheus Telemetry & Business Insights Concurrently
        ingestion_rate, buffer_depth, high_conf, duplicates, top_category = await asyncio.gather(
            fetch_prom_metric("sum(rate(ingestor_messages_received_total[1m]))"),
            fetch_prom_metric("sum(nats_consumer_num_pending)"),
            fetch_prom_metric('sum(increase(processor_threats_total{confidence="high"}[24h]))'),
            fetch_prom_metric('sum(increase(processor_db_duplicates_total[24h]))'),
            fetch_top_category()
        )

        return {
            "telemetry": {
                "ingestion_rate": ingestion_rate,
                "avg_latency": avg_latency,
                "buffer_depth": buffer_depth
            },
            "business": {
                "top_category": top_category,
                "high_confidence_total": high_conf,
                "duplicates_blocked": duplicates
            },
            "threats": threats
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Backend Error: {str(e)}")

@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}