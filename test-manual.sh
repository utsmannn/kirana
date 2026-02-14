#!/bin/bash

# Configuration
BASE_URL="http://localhost:8001/v1"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== Kirana Manual Test Workflow ===${NC}"

# 1. Register Client
echo -e "\n${GREEN}[1] Registering Client...${NC}"
RANDOM_NUM=$((1 + $RANDOM % 10000))
EMAIL="test_user_${RANDOM_NUM}@example.com"

RESPONSE=$(curl -s -X POST "${BASE_URL}/clients/" -H "Content-Type: application/json" -d "{\"name\": \"Manual Tester\", \"email\": \"${EMAIL}\"}")

if echo "$RESPONSE" | grep -q "error"; then
    echo -e "${RED}Registration Failed:${NC} $RESPONSE"
    exit 1
fi

API_KEY=$(echo "$RESPONSE" | jq -r '.api_key')
CLIENT_ID=$(echo "$RESPONSE" | jq -r '.id')

echo "API Key: $API_KEY"
echo "Client ID: $CLIENT_ID"

# 2. Get Client Info
echo -e "\n${GREEN}[2] Getting Client Info...${NC}"
curl -s -X GET "${BASE_URL}/clients/me" -H "Authorization: Bearer ${API_KEY}" | jq .

# 3. Create Knowledge 1: Concepts
echo -e "\n${GREEN}[3] Creating Knowledge (Concept)...${NC}"
KNOWLEDGE_CONTENT_1="Compose Remote Layout transforms JSON strings into dynamic Compose components. It acts as a chef interpreting a recipe (JSON) to produce UI. Architecture has 3 layers: Definition Layer (JSON matching Compose structure), Transformation Layer (step-by-step processing into virtual map), and Render Layer (showing UI, handling lifecycle and state)."

JSON_PAYLOAD=$(jq -n --arg title "Compose Remote Layout - Concepts" --arg content "$KNOWLEDGE_CONTENT_1" --arg type "text" '{title: $title, content: $content, content_type: $type, metadata: {category: "concepts"}}')
RESPONSE=$(curl -s -X POST "${BASE_URL}/knowledge/" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "$JSON_PAYLOAD")
echo "Created Knowledge ID: $(echo "$RESPONSE" | jq -r '.id')"

# 4. Create Knowledge 2: Usage
echo -e "\n${GREEN}[4] Creating Knowledge (Usage)...${NC}"
KNOWLEDGE_CONTENT_2="To use Compose Remote Layout, add the dependency. It supports Android and iOS. Key features include Value Binding (using curly braces like {counter}) and Custom Nodes for complex UI needs. JSON Builder Web provides a Live Editor for real-time preview."

JSON_PAYLOAD=$(jq -n --arg title "Compose Remote Layout - Usage" --arg content "$KNOWLEDGE_CONTENT_2" --arg type "text" '{title: $title, content: $content, content_type: $type, metadata: {category: "usage"}}')
RESPONSE=$(curl -s -X POST "${BASE_URL}/knowledge/" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "$JSON_PAYLOAD")
echo "Created Knowledge ID: $(echo "$RESPONSE" | jq -r '.id')"

# 5. List Knowledge
echo -e "\n${GREEN}[5] Listing Knowledge...${NC}"
curl -s -X GET "${BASE_URL}/knowledge/" -H "Authorization: Bearer ${API_KEY}" | jq .

# 6. Create Session
echo -e "\n${GREEN}[6] Creating Session...${NC}"
RESPONSE=$(curl -s -X POST "${BASE_URL}/sessions/" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "{\"name\": \"Compose UI Test\", \"metadata\": {\"type\": \"manual_test\"}}")
SESSION_ID=$(echo "$RESPONSE" | jq -r '.id')
echo "Session ID: $SESSION_ID"

# 7. Chat Completion (Testing Default Model & Knowledge Injection)
echo -e "\n${GREEN}[7] Chatting: Explain Compose Remote Layout (using default model)...${NC}"
echo "Question: Explain the core concept and its 3 layers."

# NOT defining 'model' in payload to test automatic default model behavior
CHAT_PAYLOAD=$(jq -n --arg session_id "$SESSION_ID" '{session_id: $session_id, messages: [{role: "user", content: "Based on the knowledge base provided, explain the core concept of Compose Remote Layout and its 3 layers."}]}')

curl -s -X POST "${BASE_URL}/chat/completions" -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" -d "$CHAT_PAYLOAD" | jq .

echo -e "\n${BLUE}=== Test Complete ===${NC}"
