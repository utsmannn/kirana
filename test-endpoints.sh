#!/bin/bash

BASE_URL="http://localhost:8001"
V1_URL="${BASE_URL}/v1"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== Kirana Comprehensive Endpoint Test ===${NC}"

# Function to check result
check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}Command Failed${NC}"
        exit 1
    fi
    # Check if response contains "error" or "detail" (FastAPI error)
    if echo "$1" | grep -qE '"error"|"detail":'; then
        echo -e "${RED}API Error Response:${NC}"
        echo "$1" | jq .
        exit 1
    fi
}

# 1. Health Check
echo -e "\n${GREEN}[1] GET /health${NC}"
RESP=$(curl -s "${BASE_URL}/health")
echo "$RESP" | jq .
check_error "$RESP"

# 2. Register Client
echo -e "\n${GREEN}[2] POST /v1/clients/${NC}"
RAND=$((RANDOM % 10000))
EMAIL="endpoint_test_${RAND}@example.com"
RESP=$(curl -s -X POST "${V1_URL}/clients/" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Endpoint Tester\", \"email\": \"${EMAIL}\"}")
echo "$RESP" | jq .
check_error "$RESP"

API_KEY=$(echo "$RESP" | jq -r '.api_key')
echo "API Key: $API_KEY"

# 3. Get Me
echo -e "\n${GREEN}[3] GET /v1/clients/me${NC}"
RESP=$(curl -s "${V1_URL}/clients/me" -H "Authorization: Bearer ${API_KEY}")
echo "$RESP" | jq .
check_error "$RESP"

# 4. Get Config
echo -e "\n${GREEN}[4] GET /v1/config/${NC}"
RESP=$(curl -s "${V1_URL}/config/" -H "Authorization: Bearer ${API_KEY}")
echo "$RESP" | jq .
check_error "$RESP"

# 5. Create Knowledge
echo -e "\n${GREEN}[5] POST /v1/knowledge/${NC}"
RESP=$(curl -s -X POST "${V1_URL}/knowledge/" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Doc", "content": "This is a test document.", "metadata": {"tag": "test"}}')
echo "$RESP" | jq .
check_error "$RESP"
KNOWLEDGE_ID=$(echo "$RESP" | jq -r '.id')

# 6. List Knowledge
echo -e "\n${GREEN}[6] GET /v1/knowledge/${NC}"
RESP=$(curl -s "${V1_URL}/knowledge/" -H "Authorization: Bearer ${API_KEY}")
echo "$RESP" | jq .
check_error "$RESP"

# 7. Create Session
echo -e "\n${GREEN}[7] POST /v1/sessions/${NC}"
RESP=$(curl -s -X POST "${V1_URL}/sessions/" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"name": "Endpoint Session", "metadata": {"test": true}}')
echo "$RESP" | jq .
check_error "$RESP"
SESSION_ID=$(echo "$RESP" | jq -r '.id')

# 8. List Sessions
echo -e "\n${GREEN}[8] GET /v1/sessions/${NC}"
RESP=$(curl -s "${V1_URL}/sessions/" -H "Authorization: Bearer ${API_KEY}")
echo "$RESP" | jq .
check_error "$RESP"

# 9. Chat (Stateless)
echo -e "\n${GREEN}[9] POST /v1/chat/completions (Stateless)${NC}"
RESP=$(curl -s -X POST "${V1_URL}/chat/completions" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}')
# Check length to avoid spamming console with big JSON, just check ID
echo "Response ID: $(echo "$RESP" | jq -r '.id')"
check_error "$RESP"

# 10. Chat (Session)
echo -e "\n${GREEN}[10] POST /v1/chat/completions (With Session)${NC}"
RESP=$(curl -s -X POST "${V1_URL}/chat/completions" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"${SESSION_ID}\", \"messages\": [{\"role\": \"user\", \"content\": \"Remember this number: 42\"}]}")
echo "Response ID: $(echo "$RESP" | jq -r '.id')"
check_error "$RESP"

# 11. Get Session Messages
echo -e "\n${GREEN}[11] GET /v1/sessions/${SESSION_ID}/messages${NC}"
RESP=$(curl -s "${V1_URL}/sessions/${SESSION_ID}/messages" -H "Authorization: Bearer ${API_KEY}")
echo "$RESP" | jq .
check_error "$RESP"

# 12. Get Usage
echo -e "\n${GREEN}[12] GET /v1/usage/${NC}"
RESP=$(curl -s "${V1_URL}/usage/" -H "Authorization: Bearer ${API_KEY}")
echo "$RESP" | jq .
check_error "$RESP"

echo -e "\n${GREEN}=== ALL ENDPOINTS PASSED ===${NC}"
