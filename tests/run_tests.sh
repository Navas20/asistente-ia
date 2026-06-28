#!/bin/bash
echo ""
echo "=== JARVIS Test Runner ==="
echo ""

read -p "API URL [http://localhost:8000]: " input_api
API_URL="${input_api:-http://localhost:8000}"

read -p "Auth Token [test-token]: " input_token
AUTH_TOKEN="${input_token:-test-token}"

export API_URL="$API_URL"
export AUTH_TOKEN="$AUTH_TOKEN"

cd "$(dirname "$0")"
python3 test_api.py

if [ $? -eq 0 ]; then
    echo ""
    echo "[OK] Todos los tests pasaron"
else
    echo ""
    echo "[FAIL] Algunos tests fallaron"
fi
