#!/bin/bash
# ShieldOps App Layer Verification - Direct Execution

echo "========================================"
echo "  ShieldOps App Layer Verification"
echo "  (Direct Execution Mode)"
echo "========================================"
echo ""

PASS=0
FAIL=0
TOTAL=21

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

check() {
    local num="$1"
    local name="$2"
    local cmd="$3"
    printf "[%02d/%02d] %-45s" "$num" "$TOTAL" "$name"
    OUTPUT=$(eval "$cmd" 2>&1)
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[PASS]${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}[FAIL]${NC}"
        echo "        Error: $(echo "$OUTPUT" | head -n 1)"
        FAIL=$((FAIL + 1))
    fi
}

echo "--- Pod Status Tests ---"
echo ""

check 1 "Ingestor pod Running" "kubectl get pods -n shieldops -l app=ingestor | grep -q 'Running'"
check 2 "Processor pod Running" "kubectl get pods -n shieldops -l app=processor | grep -q 'Running'"
check 3 "CertStream pod Running" "kubectl get pods -n shieldops -l app=certstream-server | grep -q 'Running'"
check 4 "API pod Running" "kubectl get pods -n shieldops -l app=api | grep -q 'Running'"
check 5 "Cleanup CronJob exists" "kubectl get cronjob -n shieldops cleanup >/dev/null 2>&1"
check 6 "No crash loops (Ingestor)" "kubectl get pods -n shieldops -l app=ingestor -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}' | awk '{if (\$1 < 10) exit 0; else exit 1}'"
check 7 "No crash loops (Processor)" "kubectl get pods -n shieldops -l app=processor -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}' | awk '{if (\$1 < 30) exit 0; else exit 1}'"

echo ""
echo "--- Probe & Lifecycle Tests ---"
echo ""

check 8 "Ingestor has startup probe" "kubectl get deployment -n shieldops ingestor -o yaml | grep -q 'startupProbe'"
check 9 "Processor has startup probe" "kubectl get deployment -n shieldops processor -o yaml | grep -q 'startupProbe'"
check 10 "Processor has preStop hook" "kubectl get deployment -n shieldops processor -o yaml | grep -q 'preStop'"

echo ""
echo "--- Security Tests ---"
echo ""

check 11 "Secret mounted as file" "kubectl get deployment -n shieldops processor -o yaml | grep -q 'postgres-secret'"
check 12 "Secret mount is read-only" "kubectl get deployment -n shieldops processor -o yaml | grep -q 'readOnly: true'"

echo ""
echo "--- Health Endpoint Tests ---"
echo ""

# Get dynamic pod names to avoid deployment proxy issues
PROC_POD=$(kubectl get pods -n shieldops -l app=processor -o jsonpath='{.items[0].metadata.name}')

check 13 "Ingestor /healthz responds" "kubectl exec -n shieldops \$PROC_POD -- python -c \"import urllib.request; print(urllib.request.urlopen('http://ingestor:8080/healthz').read().decode())\" | grep -q 'ok'"

check 14 "Processor /healthz responds" "kubectl exec -n shieldops \$PROC_POD -- python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8080/healthz').read().decode())\" | grep -q 'ok'"
check 15 "API /healthz responds" "kubectl exec -n shieldops \$PROC_POD -- python -c \"import urllib.request; print(urllib.request.urlopen('http://api:80/healthz').read().decode())\" | grep -q 'healthy'"

echo ""
echo "--- Data Flow Tests (End-to-End) ---"
echo ""

check 16 "Ingestor connected to CertStream" "kubectl logs -n shieldops -l app=ingestor --tail=100 | grep -i -q 'connected to certstream'"

echo -e "${YELLOW}   Checking current data flow...${NC}"

check 17 "Ingestor receiving messages" "kubectl exec -n shieldops \$PROC_POD -- python -c \"import urllib.request; print(urllib.request.urlopen('http://ingestor:8080/metrics').read().decode())\" | grep 'ingestor_messages_received_total' | awk '{if (\$2 > 0) exit 0; else exit 1}'"

check 18 "Processor processing messages" "kubectl exec -n shieldops \$PROC_POD -- python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8080/metrics').read().decode())\" | grep 'processor_messages_total' | awk '{if (\$2 > 0) exit 0; else exit 1}'"

check 19 "Threats detected in database" "kubectl exec -n shieldops sts/postgres -- psql -U shieldops -d shieldops -tAc 'SELECT COUNT(*) FROM threats' | awk '{if (\$1 > 0) exit 0; else exit 1}'"

echo ""
echo "--- Data Quality Tests ---"
echo ""

check 20 "Threats detected in database" "kubectl exec -n shieldops postgres-0 -- psql -U shieldops -d shieldops -tAc 'SELECT COUNT(*) FROM threats' | awk '{if (\$1 > 0) exit 0; else exit 1}'"

check 21 "No duplicate fingerprints" "kubectl exec -n shieldops postgres-0 -- psql -U shieldops -d shieldops -tAc 'SELECT COUNT(*) - COUNT(DISTINCT fingerprint) FROM threats' | grep -q '^0$'"

echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"

if [ $FAIL -eq 0 ]; then
    echo -e "\n${GREEN}[SUCCESS] App Layer Verification Complete!${NC}"
    exit 0
else
    echo -e "\n${RED}[ERROR] $FAIL test(s) failed.${NC}"
    exit 1
fi