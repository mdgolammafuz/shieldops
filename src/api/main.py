import os
import asyncpg
import httpx
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="ShieldOps Threat Radar")

DB_SECRET_FILE = "/etc/secrets/database-url"
PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"

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
            SELECT domain, matched_keyword, entropy, confidence, not_before, created_at 
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
            
            # Calculate Latency: Time between certificate issuance and our database write
            if row['not_before'] and row['created_at']:
                latency_seconds = (row['created_at'] - row['not_before']).total_seconds()
                if latency_seconds > 0:
                    latencies.append(latency_seconds)
                threat_dict['latency'] = round(latency_seconds, 2)
            else:
                threat_dict['latency'] = "N/A"
            
            threat_dict['not_before'] = row['not_before'].isoformat() if row['not_before'] else None
            threat_dict['created_at'] = row['created_at'].isoformat() if row['created_at'] else None
            threats.append(threat_dict)

        avg_latency = round(sum(latencies)/len(latencies), 2) if latencies else 0.0

        # 2. Fetch Prometheus Telemetry Concurrently
        ingestion_rate, buffer_depth = await asyncio.gather(
            fetch_prom_metric("sum(rate(ingestor_messages_received_total[1m]))"),
            fetch_prom_metric("sum(nats_consumer_num_pending)")
        )

        return {
            "telemetry": {
                "ingestion_rate": ingestion_rate,
                "avg_latency": avg_latency,
                "buffer_depth": buffer_depth
            },
            "threats": threats
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Backend Error: {str(e)}")

@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}