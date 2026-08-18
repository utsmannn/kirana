import base64
import binascii
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.channel import Channel
from app.models.channel_mcp_server import ChannelMcpServer
from app.models.conversation import ConversationLog
from app.models.knowledge import Knowledge
from app.models.provider import ProviderCredential
from app.models.session import Session
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.mcp_http_client import McpHttpConnection
from app.services.rag_retrieval import retrieve_context
from app.tools.base import BaseTool
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.mcp_tool_adapter import McpToolAdapter
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

# --- DSML fallback ---------------------------------------------------------
# Some OpenAI-compatible providers (e.g. deepseek via proxy) do not return
# structured `tool_calls`; they emit tool invocations as raw markup inside the
# content. We parse that markup so tools still execute and the markup never
# leaks to end users.
DSML_STARTS = ("<｜DSML｜", "<｜｜DSML｜｜")
DSML_PREFIX_RE = re.compile(r"<｜{1,2}DSML")
DSML_TOOL_CALLS_RE = re.compile(
    r"<｜{1,2}DSML｜{1,2}(?:tool_calls|function_calls)>"
    r"(.*?)"
    r"</｜{1,2}DSML｜{1,2}(?:tool_calls|function_calls)>",
    re.DOTALL,
)
DSML_INVOKE_RE = re.compile(
    r'<｜{1,2}DSML｜{1,2}invoke name="([^"]+)">'
    r"(.*?)"
    r"</｜{1,2}DSML｜{1,2}invoke>",
    re.DOTALL,
)
DSML_PARAM_RE = re.compile(
    r'<｜{1,2}DSML｜{1,2}parameter name="([^"]+)"[^>]*>'
    r"(.*?)"
    r"</｜{1,2}DSML｜{1,2}parameter>",
    re.DOTALL,
)
DSML_ANY_RE = re.compile(r"</?｜{1,2}DSML｜{1,2}[^>]*>", re.DOTALL)


def parse_dsml_tool_calls(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Extract single- or double-separator DSML tool invocations.

    DeepSeek variants emit either ``tool_calls`` or ``function_calls`` wrappers.
    Returns OpenAI-shaped calls while removing all DSML from visible content.
    """
    calls: List[Dict[str, Any]] = []
    call_index = 0
    for match in DSML_TOOL_CALLS_RE.finditer(text):
        for invoke in DSML_INVOKE_RE.finditer(match.group(1)):
            name = invoke.group(1).strip()
            args: Dict[str, Any] = {}
            for param in DSML_PARAM_RE.finditer(invoke.group(2)):
                raw = param.group(2).strip()
                try:
                    args[param.group(1)] = json.loads(raw)
                except json.JSONDecodeError:
                    args[param.group(1)] = raw
            calls.append(
                {
                    "id": f"dsml_{call_index}_{name}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            )
            call_index += 1

    if not calls:
        # Fail closed on malformed or partial markup: keep only text before the
        # first DSML marker so raw tool syntax and arguments never reach users.
        marker = DSML_PREFIX_RE.search(text)
        return (text[: marker.start()].strip(), []) if marker else (text, [])

    clean = DSML_TOOL_CALLS_RE.sub("", text)
    residual = DSML_PREFIX_RE.search(clean)
    if residual:
        clean = clean[: residual.start()]
    else:
        clean = DSML_ANY_RE.sub("", clean)
    return clean.strip(), calls


def _dsml_marker_prefix_len(text: str) -> int:
    """Return the longest supported DSML marker prefix ending ``text``."""
    longest = 0
    for marker in DSML_STARTS:
        for size in range(min(len(marker) - 1, len(text)), 0, -1):
            if text.endswith(marker[:size]):
                longest = max(longest, size)
                break
    return longest


class DsmlStreamFilter:
    """Streaming guard: yields clean text, holds back DSML markup even when the
    marker is split across chunks."""

    def __init__(self):
        self.started = False
        self.pending = ""

    def feed(self, chunk: str) -> str:
        if self.started:
            self.pending += chunk
            return ""
        self.pending += chunk
        marker_indexes = [
            self.pending.find(marker)
            for marker in DSML_STARTS
            if self.pending.find(marker) != -1
        ]
        if marker_indexes:
            idx = min(marker_indexes)
            self.started = True
            out = self.pending[:idx]
            self.pending = self.pending[idx:]
            return out
        keep = _dsml_marker_prefix_len(self.pending)
        out = self.pending[: len(self.pending) - keep] if keep else self.pending
        self.pending = self.pending[len(self.pending) - keep:] if keep else ""
        return out

    def raw(self) -> str:
        return self.pending


CHAT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
CHAT_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
}
DATA_IMAGE_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", re.DOTALL)
HUMAN_HANDOFF_MESSAGE = (
    "Pertanyaanmu sudah diteruskan ke tim kami. "
    "Agent manusia akan segera membalas."
)


class ChatService:
    def __init__(self, db: AsyncSession):
        self._current_session_id = None
        self._current_channel_id = None
        self.db = db

    async def load_channel_mcp_tools(self, channel_id: str) -> List[McpToolAdapter]:
        """Load active MCP tools for a channel without mutating the global registry."""
        try:
            result = await self.db.execute(
                select(ChannelMcpServer).where(
                    ChannelMcpServer.channel_id == channel_id,
                    ChannelMcpServer.is_active.is_(True),
                )
            )
            servers = result.scalars().all()
            if not servers:
                return []

            adapters: List[McpToolAdapter] = []
            for server in servers:
                try:
                    conn = McpHttpConnection(
                        server_url=server.server_url,
                        transport=server.transport,
                        auth_type=server.auth_type,
                        auth_config=server.auth_config or {},
                        server_config=server.server_config or {},
                    )
                    tools = await conn.list_tools()
                    for tool in tools:
                        adapters.append(
                            McpToolAdapter(
                                connection=conn,
                                name=tool["name"],
                                description=tool["description"] or "MCP tool",
                                parameters=tool["input_schema"] or {"type": "object", "properties": {}},
                            )
                        )
                    logger.info(
                        "[MCP SYNC] Channel %s server %s discovered %d tool(s)",
                        channel_id,
                        server.name,
                        len(tools),
                    )
                except Exception as e:
                    logger.warning(
                        "[MCP SYNC] Failed to sync server '%s' for channel %s: %s",
                        server.name,
                        channel_id,
                        e,
                    )

            return adapters
        except Exception as e:
            logger.warning("[MCP SYNC] Failed to load channel MCP tools: %s", e)
            return []

    async def get_knowledge_context(self, channel_id: str, query: str = "") -> str:
        """Get active channel knowledge as context. Optionally filter by query."""
        result = await self.db.execute(
            select(Knowledge).where(
                Knowledge.channel_id == channel_id,
                Knowledge.is_active.is_(True),
            )
        )
        items = result.scalars().all()
        if not items:
            return ""

        context = "\nRelevant Knowledge Base Information:\n"
        for item in items:
            context += f"--- {item.title} ---\n{item.content}\n"
        return context

    async def build_system_prompt(
        self,
        channel: Optional[Channel] = None,
        available_tools: Optional[List[BaseTool]] = None,
    ) -> str:
        """Build system prompt from channel config or global fallback."""
        # Check if context guard will be applied
        has_context = channel and channel.context

        # Use channel system prompt if available
        if channel and channel.system_prompt:
            prompt = channel.system_prompt
            # Replace {personality_name} placeholder if present
            if channel.personality_name and '{personality_name}' in prompt:
                prompt = prompt.replace('{personality_name}', channel.personality_name)
        elif has_context:
            # If context exists but no custom system prompt, use minimal generic prompt
            # The context guard will provide identity
            prompt = (
                "Answer user questions helpfully and informatively. "
                "Always respond in the same language as the user."
            )
        else:
            # Fallback to personality name first, then global settings.
            # This prevents chat from identifying as "Kirana" when a channel has
            # a configured personality but does not define a custom system prompt.
            ai_name = (channel.personality_name if channel else None) or getattr(settings, 'AI_NAME', 'Kirana')
            custom_prompt = getattr(settings, 'CUSTOM_SYSTEM_PROMPT', None)

            if custom_prompt:
                prompt = custom_prompt
            else:
                prompt = (
                    f"You are {ai_name}, a helpful AI assistant. "
                    "You are helpful, harmless, and honest."
                )

        # Add personality name context if available (but not if context guard will override identity)
        if channel and channel.personality_name and not has_context:
            prompt += f"\n\nYour name/personality is: {channel.personality_name}"

        # Add available tools info to system prompt (only user-facing tools)
        user_tools = available_tools if available_tools is not None else tool_registry.list_user_tools()
        has_mcp_tools = any(isinstance(tool, McpToolAdapter) for tool in user_tools)

        # === CONTEXT GUARD INJECTION ===
        # Priority: context > knowledge/tools scope > unlimited
        if has_context:
            # Strong context guard - limit AI to specific context, but allow channel MCP tools
            # as authorized channel data sources.
            guard_prompt = self._build_context_guard(
                channel.context,
                channel.context_description,
                allow_channel_tools=has_mcp_tools,
            )
            prompt = guard_prompt + "\n\n" + prompt
        elif channel:
            # Check if channel knowledge exists for knowledge-only guard. If the channel has MCP tools,
            # those tools are also valid sources and should not be blocked by the knowledge guard.
            has_knowledge = await self._check_knowledge_exists(channel.id)
            if has_knowledge or has_mcp_tools:
                guard_prompt = self._build_knowledge_only_guard(allow_channel_tools=has_mcp_tools)
                prompt = guard_prompt + "\n\n" + prompt

        if user_tools:
            prompt += "\n\nYou have access to the following tools:\n"
            for tool in user_tools:
                prompt += f"- {tool.name}: {tool.description}\n"
            prompt += (
                "\nUse the tools when they would help answer the user's question. "
                "Channel MCP tools are authorized data sources for this channel; "
                "try them before saying information is unavailable when the question can be answered by a tool."
            )

        # Branding — always appended.
        # Personality name overrides the default AI name.
        # Channel context overrides the default developer/owner name.
        ai_name = (channel.personality_name if channel else None) or "Kirana"
        developer = (channel.context if channel and channel.context else "Kiat Koding")
        prompt += f"\n\nYou are {ai_name}, developed by {developer}."

        return prompt

    async def _check_knowledge_exists(self, channel_id: str) -> bool:
        """Check if any active knowledge exists for a channel."""
        result = await self.db.execute(
            select(Knowledge)
            .where(
                Knowledge.channel_id == channel_id,
                Knowledge.is_active.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    def _build_context_guard(
        self,
        context: str,
        description: Optional[str] = None,
        allow_channel_tools: bool = False,
    ) -> str:
        """Build strong context guard prompt."""
        guard = f"""## IDENTITY & SCOPE

You are an assistant for: {context}"""

        if description:
            guard += f"\n\nDescription: {description}"

        if allow_channel_tools:
            guard += """

Authorized channel MCP tools are part of this channel's approved data sources. Use them when they can answer channel-related questions that are not fully covered by this channel's knowledge base."""

        guard += f"""

## STRICT RULES (MUST BE FOLLOWED):

0. **IMPORTANT: You MUST always provide a response to EVERY question. NEVER stay silent or refuse to answer.**

1. You may ONLY answer questions RELATED to {context}.
2. You MUST NOT answer questions outside this scope, INCLUDING:
   - General knowledge questions (weather, news, world facts, gossip, etc.)
   - Requests for stories, poems, songs, code, or general creativity
   - Personal questions about yourself as an AI
   - Political, religious, or other sensitive topics
   - Questions about celebrities, entertainment, or pop culture
   - Requests to play games, puzzles, or tell jokes
   - Anything NOT related to {context}

3. If the user asks a question outside your scope:
   - Decline POLITELY and FIRMLY
   - State that you are an assistant for {context}
   - Offer help that is RELEVANT to {context}
   - NEVER answer the question, even if the user insists

4. If the question IS relevant to {context} but the specific information is NOT in this channel's knowledge base:
   - If channel tools are available and one may answer the question, use the tool first
   - HONESTLY state that the information is not yet available in the system only after this channel's knowledge base and relevant tools cannot answer it
   - NEVER fabricate information
   - Offer to help with other related questions

5. Never break character or admit you are restricted. Stay professional.

## RESPONSE STYLE:
Always respond in the same language the user used in their query.

## EXAMPLE RESPONSES:

**For RELEVANT questions where info is unavailable:**
- "Regarding that, the information is not yet available in our system. Is there another question about {context} I can help with?"
- "Sorry, I don't have that detail in my database. Please contact {context} directly or ask something else."

**For OUT-OF-SCOPE questions:**
- "Sorry, I am an assistant for {context}. I can only help with questions about {context}. Is there anything I can help with related to {context}?"
- "That question is outside my scope as a {context} assistant. Please ask something related to {context}." """

        return guard

    def _build_knowledge_only_guard(self, allow_channel_tools: bool = False) -> str:
        """Build knowledge/tool guard prompt (when scoped data sources exist)."""
        if allow_channel_tools:
            sources = "this channel's knowledge base and channel MCP tools"
            missing_rule = (
                "If the question is not answerable from this channel's knowledge base, use relevant "
                "channel MCP tools before saying the information is unavailable."
            )
        else:
            sources = "this channel's knowledge base"
            missing_rule = "If the question is not related to this channel's knowledge base or the information is unavailable:"

        return f"""## KNOWLEDGE AND TOOL SCOPE

You have access to {sources} that have been provided for this channel.

## RULES:

0. **IMPORTANT: You MUST always provide a response to EVERY question. NEVER stay silent or refuse to answer.**

1. Prioritize answering based on information available from {sources}.
2. {missing_rule}
   - HONESTLY state that the information is not available in the system only after checking relevant available sources
   - OFFER to help with other questions
   - NEVER fabricate information
3. Stay friendly and helpful even when you cannot provide a specific answer.

## RESPONSE STYLE:
Always respond in the same language the user used in their query.

## EXAMPLE RESPONSES:
- "Sorry, that information is not available in my database. Is there anything else I can help with?"
- "I don't have data about that yet. Please ask something else or contact the relevant party."
- "That detail is not in our system right now. Is there anything else you'd like to know?"
 """

    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        available_tools: Optional[List[BaseTool]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute tool calls and return results."""
        results = []
        tools = available_tools or tool_registry.list_tools()
        tools_by_name = {tool.name: tool for tool in tools}
        tool_context = {
            "session_id": (
                str(self._current_session_id) if self._current_session_id else None
            ),
            "channel_id": (
                str(self._current_channel_id) if self._current_channel_id else None
            ),
        }
        for tool in tools:
            tool.context = tool_context

        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            function_data = tool_call.get("function", {})
            tool_name = function_data.get("name")
            tool_args_str = function_data.get("arguments", "{}")

            try:
                tool_args = json.loads(tool_args_str) if tool_args_str else {}
            except json.JSONDecodeError:
                tool_args = {}

            logger.info("[TOOL] Executing tool '%s' with args: %s", tool_name, tool_args)

            tool = tools_by_name.get(tool_name)
            if not tool:
                logger.warning("[TOOL] Tool '%s' not found", tool_name)
                results.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps({"error": f"Tool '{tool_name}' not found"})
                })
                continue

            try:
                # Filter args to only allowed parameters
                allowed_params = set(tool.parameters.get("properties", {}).keys())
                filtered_args = {k: v for k, v in tool_args.items() if k in allowed_params}

                result = await tool.execute(**filtered_args)
                logger.info("[TOOL] Tool '%s' executed successfully", tool_name)

                results.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(result)
                })
            except Exception as e:
                logger.exception("[TOOL] Tool '%s' execution failed: %s", tool_name, e)
                results.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps({"error": str(e)})
                })

        return results

    def _build_client(self, api_key: str, api_base: Optional[str]) -> AsyncOpenAI:
        kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "max_retries": settings.LLM_MAX_RETRIES,
            "timeout": float(settings.LLM_TIMEOUT),
        }
        if api_base:
            kwargs["base_url"] = api_base
        return AsyncOpenAI(**kwargs)

    def _part_to_dict(self, part: Any) -> Dict[str, Any]:
        if isinstance(part, dict):
            return part
        if hasattr(part, "model_dump"):
            return part.model_dump(mode="json")
        return {}

    def _content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, list):
            return ""

        texts: List[str] = []
        for part in content:
            part_data = self._part_to_dict(part)
            if part_data.get("type") == "text":
                text = part_data.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
        return "\n".join(texts).strip()

    def _parse_data_image_url(self, url: str) -> Tuple[str, str, int]:
        match = DATA_IMAGE_RE.match(url)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_chat_image", "message": "Chat images must use a data:image/*;base64 URL."},
            )

        mime_type = match.group(1).lower()
        base64_data = re.sub(r"\s+", "", match.group(2))
        if mime_type not in CHAT_IMAGE_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "unsupported_chat_image", "message": f"Unsupported chat image type: {mime_type}"},
            )

        try:
            decoded_size = len(base64.b64decode(base64_data, validate=True))
        except (binascii.Error, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_chat_image", "message": "Chat image data is not valid base64."},
            ) from e

        if decoded_size > CHAT_IMAGE_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "chat_image_too_large",
                    "message": f"Chat images must be {CHAT_IMAGE_MAX_BYTES // (1024 * 1024)} MB or smaller.",
                },
            )

        return mime_type, base64_data, decoded_size

    def _validate_chat_content(self, content: Any) -> None:
        if isinstance(content, str):
            return
        if not isinstance(content, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_chat_content", "message": "Chat message content must be text or supported content parts."},
            )

        for part in content:
            part_data = self._part_to_dict(part)
            part_type = part_data.get("type")
            if part_type == "text":
                if not isinstance(part_data.get("text"), str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"code": "invalid_chat_content", "message": "Text content parts require a text string."},
                    )
            elif part_type == "image_url":
                image_url = part_data.get("image_url")
                if not isinstance(image_url, dict) or not isinstance(image_url.get("url"), str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"code": "invalid_chat_image", "message": "Image content parts require an image_url.url string."},
                    )
                self._parse_data_image_url(image_url["url"])
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "invalid_chat_content", "message": f"Unsupported chat content part type: {part_type}"},
                )

    def _serialize_content_for_storage(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(content)

        images: List[Dict[str, Any]] = []
        text = self._content_text(content)
        for part in content:
            part_data = self._part_to_dict(part)
            if part_data.get("type") != "image_url":
                continue
            url = part_data.get("image_url", {}).get("url", "")
            mime_type, _, decoded_size = self._parse_data_image_url(url)
            images.append({
                "mime_type": mime_type,
                "size": decoded_size,
                "redacted": True,
            })

        return json.dumps({
            "type": "multimodal",
            "text": text,
            "images": images,
        })

    def _storage_content_to_prompt_text(self, content: str) -> str:
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return content

        if not isinstance(parsed, dict) or parsed.get("type") != "multimodal":
            return content

        text = parsed.get("text") if isinstance(parsed.get("text"), str) else ""
        images = parsed.get("images") if isinstance(parsed.get("images"), list) else []
        note = f"[User attached {len(images)} image(s) in this previous message]" if images else ""
        return "\n".join(part for part in [note, text] if part).strip()

    def _raise_provider_error(self, error: Exception, model: str) -> None:
        """Map OpenAI-compatible provider errors to clear HTTP errors."""
        provider_message = str(error)
        logger.warning(
            "[PROVIDER ERROR] model=%s type=%s message=%s",
            model,
            error.__class__.__name__,
            provider_message,
        )

        if isinstance(error, AuthenticationError):
            status_code = status.HTTP_502_BAD_GATEWAY
            message = "AI provider authentication failed. Check the provider API key."
        elif isinstance(error, RateLimitError):
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
            message = "AI provider rate limit exceeded. Please try again later."
        elif isinstance(error, BadRequestError):
            status_code = status.HTTP_502_BAD_GATEWAY
            message = "AI provider rejected the request. Check the selected model and provider configuration."
        elif isinstance(error, (APITimeoutError, APIConnectionError)):
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
            message = "AI provider is unreachable or timed out. Check the provider base URL and network connection."
        elif isinstance(error, APIError):
            status_code = status.HTTP_502_BAD_GATEWAY
            message = "AI provider returned an error. Please check the provider configuration or try again."
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            message = "Unexpected error while calling the AI provider."

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": "provider_error",
                "message": message,
                "provider_error_type": error.__class__.__name__,
                "provider_message": provider_message,
                "model": model,
            },
        ) from error

    async def _prepare_completion(
        self,
        request: ChatCompletionRequest,
    ) -> Tuple[Dict[str, Any], Optional[Session], str, List[Dict[str, Any]], AsyncOpenAI, List[BaseTool]]:
        """Prepare completion kwargs and return session if applicable."""
        # Load session and channel if session_id provided
        session = None
        channel = None

        # First, try to load channel from channel_id if provided directly
        if request.channel_id:
            c_result = await self.db.execute(
                select(Channel).where(Channel.id == request.channel_id)
            )
            channel = c_result.scalar_one_or_none()

        # Load session if session_id provided
        if request.session_id:
            result = await self.db.execute(
                select(Session).where(Session.id == request.session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                session_visitor_id = str(
                    (session.extra_metadata or {}).get("visitor_id") or ""
                )
                if (
                    request.channel_id
                    and session.channel_id != request.channel_id
                ) or (
                    request.visitor_id
                    and session_visitor_id != request.visitor_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Session does not belong to this visitor",
                    )

                # Load channel from session if not already loaded
                if not channel and session.channel_id:
                    c_result = await self.db.execute(
                        select(Channel).where(Channel.id == session.channel_id)
                    )
                    channel = c_result.scalar_one_or_none()

        # Load channel-scoped MCP tools locally for this request.
        builtin_tools = tool_registry.list_user_tools()
        mcp_tools: List[McpToolAdapter] = []
        if channel:
            mcp_tools = await self.load_channel_mcp_tools(str(channel.id))

        available_tools: List[BaseTool] = list(builtin_tools)
        seen_tool_names = {tool.name for tool in available_tools}
        if channel and "query_knowledge" not in seen_tool_names:
            available_tools.append(KnowledgeTool(channel_id=channel.id))
            seen_tool_names.add("query_knowledge")
        for tool in mcp_tools:
            if tool.name in seen_tool_names:
                logger.warning("[MCP SYNC] Skipping duplicate MCP tool name: %s", tool.name)
                continue
            available_tools.append(tool)
            seen_tool_names.add(tool.name)

        # If no session but has channel_id and visitor_id (embed chat), create a new session
        # This allows embed chats to be saved to the database with unique visitor identification
        if not session and channel and request.visitor_id:
            embed_config = channel.embed_config or {}
            save_history = embed_config.get("save_history", True)

            if save_history:
                # Create new session for this embed chat visitor
                session_name = (
                    request.visitor_name or f"Embed - {request.visitor_id[:8]}"
                )
                session = Session(
                    name=session_name,
                    channel_id=channel.id,
                    extra_metadata={
                        "visitor_id": request.visitor_id,
                        "visitor_name": request.visitor_name,
                        "visitor_email": request.visitor_email,
                    },
                )
                self.db.add(session)
                # Commit (not just flush) so parallel connections — e.g. the
                # Telegram bridge resolving this session from a tool call —
                # can see the row before the conversation is saved.
                await self.db.commit()
                logger.info("[SESSION] Created new session for embed visitor: %s (channel: %s)", request.visitor_id[:8], channel.name)

        # Build system prompt with channel config
        system_prompt = await self.build_system_prompt(channel, available_tools=available_tools)

        for msg in request.messages:
            self._validate_chat_content(msg.content)

        latest_user_message = next(
            (self._content_text(msg.content) for msg in reversed(request.messages) if msg.role == "user"),
            "",
        )
        if latest_user_message and settings.RAG_ENABLED and channel:
            try:
                rag_result = await retrieve_context(
                    self.db,
                    latest_user_message,
                    channel_id=channel.id,
                    channel_context=channel.context,
                    channel_description=channel.context_description,
                )
                if rag_result.context:
                    system_prompt += (
                        "\n\n## CHANNEL KNOWLEDGE BASE CONTEXT\n"
                        "Use the following channel-scoped context as your primary source when answering. "
                        "If information is not in the context but a relevant channel MCP tool is available, use the tool before saying it is unavailable. "
                        "Cite [S1], [S2], etc. when relevant.\n\n"
                        f"{rag_result.context}"
                    )
                    logger.info("[RAG] Injected %d retrieved chunks", len(rag_result.chunks))
            except Exception as e:
                logger.warning("[RAG] Retrieval failed, continuing without RAG context: %s", e)

        messages = [{"role": "system", "content": system_prompt}]

        # Load session history
        if session:
            h_result = await self.db.execute(
                select(ConversationLog)
                .where(ConversationLog.session_id == session.id)
                .order_by(ConversationLog.created_at.desc())
                .limit(10)
            )
            history = h_result.scalars().all()
            for msg in reversed(history):
                messages.append({"role": msg.role, "content": self._storage_content_to_prompt_text(msg.content)})

        # Add user messages
        for msg in request.messages:
            messages.append(msg.model_dump(exclude_unset=True, mode="json"))

        model = request.model if request.model != "default" else settings.DEFAULT_MODEL

        # Resolve provider credentials: channel provider > default from .env
        api_key = settings.OPENAI_API_KEY
        api_base = settings.OPENAI_BASE_URL
        if channel:
            p_result = await self.db.execute(
                select(ProviderCredential).where(
                    ProviderCredential.id == channel.provider_id,
                    ProviderCredential.is_active.is_(True),
                )
            )
            provider = p_result.scalar_one_or_none()
            if provider:
                api_key = provider.api_key
                api_base = provider.base_url or api_base
                model = provider.model if request.model == "default" else model
                logger.info(
                    "[PROVIDER] Using channel provider: %s (model=%s)",
                    provider.name, model,
                )
            else:
                logger.warning(
                    "[PROVIDER] Channel provider inactive/not found: channel_id=%s provider_id=%s",
                    channel.id,
                    channel.provider_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "provider_config_error",
                        "message": "The selected channel's AI provider is inactive or no longer exists. Please update the channel provider configuration.",
                        "channel_id": str(channel.id),
                        "provider_id": str(channel.provider_id),
                    },
                )

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "provider_config_error",
                    "message": "No AI provider API key is configured. Please configure a provider or set OPENAI_API_KEY.",
                    "model": model,
                },
            )

        completion_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or 4096,
        }

        client = self._build_client(api_key, api_base)

        # Add tools if available and not disabled
        # Only pass user-facing tools to LLM (internal tools are for system use only)
        if available_tools:
            completion_kwargs["tools"] = [tool.to_openai_tool() for tool in available_tools]
            completion_kwargs["tool_choice"] = request.tool_choice or "auto"
            logger.info(
                "[TOOL] Passing %d user-facing tools to LLM: %s",
                len(available_tools),
                ", ".join(tool.name for tool in available_tools),
            )

        self._current_session_id = session.id if session else None
        self._current_channel_id = channel.id if channel else None
        return completion_kwargs, session, model, messages, client, available_tools

    async def _save_conversation(
        self,
        session: Session,
        user_msg: Any,
        assistant_content: str,
        model: str,
    ):
        """Save conversation to database."""
        try:
            logger.info("[SAVE] Starting save for session %s", session.id)

            # Save user message
            db_user_msg = ConversationLog(
                session_id=session.id,
                role=user_msg.role,
                content=self._serialize_content_for_storage(user_msg.content),
                model=model,
                tokens_used=0,
            )
            self.db.add(db_user_msg)
            logger.info("[SAVE] Added user message")

            # Save assistant message
            db_assistant_msg = ConversationLog(
                session_id=session.id,
                role="assistant",
                content=assistant_content,
                model=model,
                tokens_used=0,
            )
            self.db.add(db_assistant_msg)
            logger.info("[SAVE] Added assistant message")

            # Update session
            session.message_count += 2
            session.last_activity = datetime.now(timezone.utc)
            logger.info("[SAVE] Updated session message_count to %d", session.message_count)

            await self.db.commit()
            logger.info("[SAVE] Commit successful")

            # Publish session events (realtime subscribers + webhook)
            from app.services import event_bus
            await event_bus.publish(
                "message.user",
                session.id,
                session.channel_id,
                {
                    "message_id": str(db_user_msg.id),
                    "role": db_user_msg.role,
                    "content": db_user_msg.content,
                },
            )
            await event_bus.publish(
                "message.assistant",
                session.id,
                session.channel_id,
                {
                    "message_id": str(db_assistant_msg.id),
                    "role": "assistant",
                    "content": assistant_content,
                    "model": model,
                },
            )
        except Exception as e:
            logger.exception("[SAVE] Error saving conversation: %s", e)
            raise

    async def _save_user_message_human_mode(
        self,
        session: Session,
        user_msg: Any,
    ) -> ConversationLog:
        """Human mode: log the user message only — no LLM call."""
        log = ConversationLog(
            session_id=session.id,
            client_id=session.client_id,
            role=user_msg.role,
            content=self._serialize_content_for_storage(user_msg.content),
            model="human_mode",
            tokens_used=0,
        )
        self.db.add(log)
        session.message_count += 1
        session.last_activity = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(log)

        from app.services import event_bus
        await event_bus.publish(
            "message.user",
            session.id,
            session.channel_id,
            {
                "message_id": str(log.id),
                "role": log.role,
                "content": log.content,
                "queued_for_human": True,
            },
        )
        return log

    async def create_chat_completion(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """Create a chat completion with tool support."""
        completion_kwargs, session, model, messages, client, available_tools = await self._prepare_completion(request)

        # Human mode: a human agent owns this conversation — log only, no LLM.
        if session and session.mode == "human":
            await self._save_user_message_human_mode(session, request.messages[-1])
            return ChatCompletionResponse(
                id=f"human-{uuid.uuid4().hex[:12]}",
                created=int(time.time()),
                model="human_mode",
                choices=[
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": HUMAN_HANDOFF_MESSAGE,
                        },
                        "finish_reason": "human_handoff",
                    }
                ],
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                session={
                    "id": str(session.id),
                    "mode": "human",
                    "queued_for_human": True,
                },
            )

        start_time = time.monotonic()
        try:
            response = await client.chat.completions.create(**completion_kwargs)
        except Exception as e:
            self._raise_provider_error(e, model)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        message = response.choices[0].message
        content = message.content or ""
        dsml_clean, dsml_calls = parse_dsml_tool_calls(content)
        if dsml_calls:
            logger.info(
                "[TOOL] Parsed %d DSML tool calls from content",
                len(dsml_calls),
            )
        if dsml_clean != content:
            content = dsml_clean
        usage = response.usage

        # Check if LLM wants to use tools
        if message.tool_calls or dsml_calls:
            logger.info(
                "[TOOL] LLM requested %d tool calls",
                len(message.tool_calls or dsml_calls),
            )

            # Convert tool_calls to dicts for execute and for messages
            if message.tool_calls:
                tool_calls_dicts = [tc.model_dump() for tc in message.tool_calls]
            else:
                tool_calls_dicts = dsml_calls

            # Execute tools
            tool_results = await self._execute_tool_calls(tool_calls_dicts, available_tools)

            # Build new messages with tool calls and results
            if message.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls_dicts,
                })
                messages.extend(tool_results)
            else:
                # Provider emitted DSML markup: it does not understand OpenAI
                # tool roles, so feed results back as a plain user message.
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        "Hasil pemanggilan tool "
                        "(JSON, gunakan untuk menjawab):\n"
                    )
                    + json.dumps(
                        [
                            {"name": r["name"], "result": r["content"]}
                            for r in tool_results
                        ],
                        ensure_ascii=False,
                    ),
                })

            # Re-call LLM with tool results
            completion_kwargs["messages"] = messages
            # Remove tools for second call to avoid loops
            completion_kwargs.pop("tools", None)
            completion_kwargs.pop("tool_choice", None)

            logger.info("[TOOL] Re-calling LLM with tool results")
            try:
                final_response = await client.chat.completions.create(**completion_kwargs)
            except Exception as e:
                self._raise_provider_error(e, model)
            content, leftover_calls = parse_dsml_tool_calls(
                final_response.choices[0].message.content or ""
            )
            if leftover_calls:
                logger.warning(
                    "[TOOL] DSML tool calls leaked into final answer; discarded: %s",
                    [c["function"]["name"] for c in leftover_calls],
                )
            usage = final_response.usage
            latency_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            "Chat completion: model=%s tokens=%d latency=%dms",
            model, usage.total_tokens if usage else 0, latency_ms,
        )

        if session:
            logger.info("[CHAT] Saving conversation for session %s", session.id)
            await self._save_conversation(
                session, request.messages[-1], content, model
            )
        else:
            logger.info("[CHAT] No session provided, conversation not saved")

        return ChatCompletionResponse(
            id=response.id,
            created=int(time.time()),
            model=model,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
            session={"id": str(session.id)} if session else None,
        )

    async def create_chat_completion_stream(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncGenerator[str, None]:
        """Create a streaming chat completion with tool support.

        Fully streaming: streams the first LLM call, intercepts tool_calls
        from the stream if any, executes tools, then streams the second call.
        """
        completion_kwargs, session, model, messages, client, available_tools = await self._prepare_completion(request)
        completion_kwargs["stream"] = True

        # Announce the session before provider work. WebSocket adapters can attach
        # the event subscription now, so a fast Telegram reply is queued instead
        # of being lost while the AI stream is still running.
        if session:
            yield f"data: {json.dumps({'session_id': str(session.id)})}\n\n"

        # Human mode: a human agent owns this conversation — log only, no LLM.
        if session and session.mode == "human":
            await self._save_user_message_human_mode(session, request.messages[-1])
            handoff_chunk = {
                "id": f"human-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": HUMAN_HANDOFF_MESSAGE,
                        },
                        "finish_reason": "human_handoff",
                    }
                ],
            }
            yield f"data: {json.dumps(handoff_chunk)}\n\n"
            yield f"data: {json.dumps({'type': 'queued_for_human'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        start_time = time.monotonic()

        try:
            response = await client.chat.completions.create(**completion_kwargs)
        except Exception as e:
            self._raise_provider_error(e, model)

        full_content = ""
        tool_calls_accum: Dict[int, Dict[str, Any]] = {}
        has_tool_calls = False
        dsml_filter = DsmlStreamFilter()

        async for chunk in response:
            delta = chunk.choices[0].delta

            # Accumulate tool calls from stream chunks
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                has_tool_calls = True
                for tc in delta.tool_calls:
                    idx = tc.index if hasattr(tc, "index") else 0
                    if idx not in tool_calls_accum:
                        tool_calls_accum[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        }
                    if hasattr(tc, "id") and tc.id:
                        tool_calls_accum[idx]["id"] = tc.id
                    if hasattr(tc, "function") and tc.function:
                        if hasattr(tc.function, "name") and tc.function.name:
                            tool_calls_accum[idx]["function"]["name"] += tc.function.name
                        if hasattr(tc.function, "arguments") and tc.function.arguments:
                            tool_calls_accum[idx]["function"]["arguments"] += tc.function.arguments

                    event = {
                        "type": "tool_call_delta",
                        "index": idx,
                        "delta": tc.model_dump(exclude_none=True),
                        "tool_call": tool_calls_accum[idx],
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                continue

            # Regular content - filter DSML markup, yield clean text
            chunk_content = delta.content or ""
            if chunk_content:
                full_content += chunk_content
                clean_out = dsml_filter.feed(chunk_content)
                if clean_out:
                    event = {
                        "id": getattr(chunk, "id", None) or "chatcmpl-dsml",
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {"content": clean_out}}],
                    }
                    yield f"data: {json.dumps(event)}\n\n"
            # Skip chunks with only reasoning_content and no actual content

        # DSML fallback: provider emitted tool calls as raw markup in content
        dsml_clean, dsml_calls = parse_dsml_tool_calls(full_content)
        via_dsml = bool(dsml_calls)
        if via_dsml and not has_tool_calls:
            logger.info(
                "[TOOL STREAM] Parsed %d DSML tool calls from content",
                len(dsml_calls),
            )
            has_tool_calls = True
            tool_calls_accum = dict(enumerate(dsml_calls))
        if dsml_clean != full_content:
            full_content = dsml_clean

        # If LLM requested tool calls, execute and stream final answer
        if has_tool_calls:
            tool_calls_list = [tool_calls_accum[i] for i in sorted(tool_calls_accum.keys())]
            logger.info("[TOOL STREAM] LLM requested %d tool calls", len(tool_calls_list))

            for tool_call in tool_calls_list:
                event = {
                    "type": "tool_call_started",
                    "tool_call_id": tool_call.get("id"),
                    "name": tool_call.get("function", {}).get("name"),
                    "arguments": tool_call.get("function", {}).get("arguments"),
                }
                yield f"data: {json.dumps(event)}\n\n"

            # Execute tools
            tool_results = await self._execute_tool_calls(tool_calls_list, available_tools)

            for tool_result in tool_results:
                try:
                    parsed_content = json.loads(tool_result.get('content') or '{}')
                except json.JSONDecodeError:
                    parsed_content = {'raw': tool_result.get('content')}

                event_type = 'tool_call_failed' if parsed_content.get('error') or parsed_content.get('is_error') else 'tool_call_completed'
                event = {
                    "type": event_type,
                    "tool_call_id": tool_result.get("tool_call_id"),
                    "name": tool_result.get("name"),
                    "result": parsed_content,
                }
                yield f"data: {json.dumps(event)}\n\n"

            # Build messages for second call
            if via_dsml:
                # Provider does not understand OpenAI tool roles; feed results
                # back as a plain user message instead.
                messages.append({"role": "assistant", "content": full_content})
                messages.append({
                    "role": "user",
                    "content": (
                        "Hasil pemanggilan tool "
                        "(JSON, gunakan untuk menjawab):\n"
                    )
                    + json.dumps(
                        [
                            {"name": r["name"], "result": r["content"]}
                            for r in tool_results
                        ],
                        ensure_ascii=False,
                    ),
                })
            else:
                messages.append({
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": tool_calls_list
                })
                messages.extend(tool_results)

            # Stream the final answer (no tools to avoid loop)
            completion_kwargs["messages"] = messages
            completion_kwargs.pop("tools", None)
            completion_kwargs.pop("tool_choice", None)

            logger.info("[TOOL STREAM] Streaming final answer with tool results")
            try:
                final_response = await client.chat.completions.create(**completion_kwargs)
            except Exception as e:
                self._raise_provider_error(e, model)

            dsml_filter2 = DsmlStreamFilter()
            async for chunk in final_response:
                chunk_content = chunk.choices[0].delta.content or ""
                if chunk_content:
                    full_content += chunk_content
                    clean_out = dsml_filter2.feed(chunk_content)
                    if clean_out:
                        event = {
                            "id": getattr(chunk, "id", None) or "chatcmpl-dsml",
                            "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": {"content": clean_out}}],
                        }
                        yield f"data: {json.dumps(event)}\n\n"
            final_clean, leftover_calls = parse_dsml_tool_calls(full_content)
            if leftover_calls:
                logger.warning(
                    "[TOOL STREAM] DSML tool calls leaked into final answer; "
                    "discarded: %s",
                    [c["function"]["name"] for c in leftover_calls],
                )
            if final_clean != full_content:
                full_content = final_clean

        yield "data: [DONE]\n\n"

        latency_ms = int((time.monotonic() - start_time) * 1000)

        if session:
            logger.info("[CHAT STREAM] Saving conversation for session %s", session.id)
            await self._save_conversation(
                session, request.messages[-1], full_content, model
            )
        else:
            logger.info("[CHAT STREAM] No session provided, conversation not saved")

        logger.info(
            "Chat stream complete: model=%s latency=%dms",
            model, latency_ms,
        )
