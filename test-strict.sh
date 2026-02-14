#!/bin/bash

# Configuration
BASE_URL="http://localhost:8001/v1"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== Kirana Manual Test Workflow (Strict Mode) ===${NC}"

# 1. Register Client
echo -e "\n${GREEN}[1] Registering Client...${NC}"
RANDOM_NUM=$((1 + $RANDOM % 10000))
EMAIL="strict_test_${RANDOM_NUM}@example.com"

# Use jq to build JSON safely
JSON_DATA=$(jq -n --arg name "Strict User" --arg email "${EMAIL}" '{name: $name, email: $email}')
RESPONSE=$(curl -s -X POST "${BASE_URL}/clients/" -H "Content-Type: application/json" -d "${JSON_DATA}")

if echo "${RESPONSE}" | grep -q "error"; then
    echo -e "${RED}Registration Failed:${NC} ${RESPONSE}"
    exit 1
fi

API_KEY=$(echo "${RESPONSE}" | jq -r '.api_key')
CLIENT_ID=$(echo "${RESPONSE}" | jq -r '.id')

echo "API Key: ${API_KEY}"
echo "Client ID: ${CLIENT_ID}"

# 2. Enable Strict Knowledge Mode
echo -e "\n${GREEN}[2] Enabling Strict Knowledge Mode...${NC}"
RESPONSE=$(curl -s -X PATCH "${BASE_URL}/config/" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"restrict_to_knowledge": true}')
echo "${RESPONSE}" | jq .

# 3. Create Knowledge (Concept)
echo -e "\n${GREEN}[3] Creating Knowledge...${NC}"
KNOWLEDGE_CONTENT="Kirana is a strict AI that only talks about itself. It is built using FastAPI and Python."
JSON_PAYLOAD=$(jq -n --arg title "Kirana Info" --arg content "${KNOWLEDGE_CONTENT}" --arg type "text" '{title: $title, content: $content, content_type: $type, metadata: {category: "concepts"}}')

RESPONSE=$(curl -s -X POST "${BASE_URL}/knowledge/" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "${JSON_PAYLOAD}")
echo "Created Knowledge ID: $(echo "${RESPONSE}" | jq -r '.id')"

# 4. Create Session
echo -e "\n${GREEN}[4] Creating Session...${NC}"
RESPONSE=$(curl -s -X POST "${BASE_URL}/sessions/" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "{\"name\": \"Strict Chat\", \"metadata\": {\"type\": \"strict_test\"}}")
SESSION_ID=$(echo "${RESPONSE}" | jq -r '.id')
echo "Session ID: ${SESSION_ID}"

# 5. Chat: Valid Question
echo -e "\n${GREEN}[5] Chatting: Valid Question (About Knowledge)...${NC}"
echo "User: What is Kirana built with?"
CHAT_PAYLOAD=$(jq -n --arg session_id "${SESSION_ID}" '{session_id: $session_id, messages: [{role: "user", content: "What is Kirana built with?"}]}')
curl -s -X POST "${BASE_URL}/chat/completions" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "${CHAT_PAYLOAD}" | jq .

# 6. Chat: Invalid Question (Trap)
echo -e "\n${GREEN}[6] Chatting: Invalid Question (General Knowledge)...${NC}"
echo "User: Who won the World Cup 2022?"
CHAT_PAYLOAD=$(jq -n --arg session_id "${SESSION_ID}" '{session_id: $session_id, messages: [{role: "user", content: "Who won the World Cup 2022?"}]}')
curl -s -X POST "${BASE_URL}/chat/completions" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "${CHAT_PAYLOAD}" | jq .

echo -e "\n${BLUE}=== Test Complete ===${NC}"
