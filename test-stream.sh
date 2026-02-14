#!/bin/bash

BASE_URL="http://localhost:8001/v1"
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${BLUE}=== Kirana Streaming Test ===${NC}"

# 1. Register
echo -e "\n${GREEN}[1] Registering...${NC}"
EMAIL="stream_test_$((RANDOM % 10000))@example.com"
RESPONSE=$(curl -s -X POST "${BASE_URL}/clients/" -H "Content-Type: application/json" -d "{\"name\": \"Stream User\", \"email\": \"${EMAIL}\"}")
API_KEY=$(echo "$RESPONSE" | jq -r '.api_key')
echo "API Key: $API_KEY"

# 2. Stream Chat
echo -e "\n${GREEN}[2] Chatting with Stream...${NC}"
curl -N -X POST "${BASE_URL}/chat/completions" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Count from 1 to 5"}],
    "stream": true
  }'

echo -e "\n\n${GREEN}=== Done ===${NC}"

