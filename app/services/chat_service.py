import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.channel import Channel
from app.models.conversation import ConversationLog
from app.models.knowledge import Knowledge
from app.models.session import Session
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_knowledge_context(self, query: str = "") -> str:
        """Get active knowledge as context. Optionally filter by query."""
        result = await self.db.execute(
            select(Knowledge).where(Knowledge.is_active.is_(True))
        )
        items = result.scalars().all()
        if not items:
            return ""

        context = "\nRelevant Knowledge Base Information:\n"
        for item in items:
            context += f"--- {item.title} ---\n{item.content}\n"
        return context

    async def build_system_prompt(self, channel: Optional[Channel] = None) -> str:
        """Build system prompt from channel config or global fallback."""
        # Use channel system prompt if available
        if channel and channel.system_prompt:
            prompt = channel.system_prompt
            # Replace {personality_name} placeholder if present
            if channel.personality_name and '{personality_name}' in prompt:
                prompt = prompt.replace('{personality_name}', channel.personality_name)
        else:
            # Fallback to global settings
            ai_name = getattr(settings, 'AI_NAME', 'Kirana')
            custom_prompt = getattr(settings, 'CUSTOM_SYSTEM_PROMPT', None)

            if custom_prompt:
                prompt = custom_prompt
            else:
                prompt = (
                    f"You are {ai_name}, a helpful AI assistant. "
                    "You are helpful, harmless, and honest."
                )

        # Add personality name context if available
        if channel and channel.personality_name:
            prompt += f"\n\nYour name/personality is: {channel.personality_name}"

        # Add available tools info to system prompt
        tools = tool_registry.list_tools()
        if tools:
            prompt += "\n\nYou have access to the following tools:\n"
            for tool in tools:
                prompt += f"- {tool.name}: {tool.description}\n"
            prompt += "\nUse the tools when they would help answer the user's question."

        return prompt

    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute tool calls and return results."""
        results = []

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

            tool = tool_registry.get_tool(tool_name)
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

    async def _prepare_completion(
        self,
        request: ChatCompletionRequest,
    ) -> Tuple[Dict[str, Any], Optional[Session], str, List[Dict[str, Any]]]:
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
                # Load channel from session if not already loaded
                if not channel and session.channel_id:
                    c_result = await self.db.execute(
                        select(Channel).where(Channel.id == session.channel_id)
                    )
                    channel = c_result.scalar_one_or_none()

        # Build system prompt with channel config
        system_prompt = await self.build_system_prompt(channel)
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
                messages.append({"role": msg.role, "content": msg.content})

        # Add user messages
        for msg in request.messages:
            messages.append(msg.model_dump(exclude_unset=True))

        model = request.model if request.model != "default" else settings.DEFAULT_MODEL

        completion_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or 4096,
            "api_key": settings.OPENAI_API_KEY,
            "timeout": settings.LLM_TIMEOUT,
            "num_retries": settings.LLM_MAX_RETRIES,
        }

        # Add tools if available and not disabled
        available_tools = tool_registry.list_tools()
        if available_tools:
            completion_kwargs["tools"] = [tool.to_openai_tool() for tool in available_tools]
            completion_kwargs["tool_choice"] = request.tool_choice or "auto"
            logger.info("[TOOL] Passing %d tools to LLM", len(available_tools))

        if settings.OPENAI_BASE_URL:
            completion_kwargs["api_base"] = settings.OPENAI_BASE_URL
            if "/" not in model:
                completion_kwargs["model"] = f"openai/{model}"

        return completion_kwargs, session, model, messages

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
                content=user_msg.content,
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
        except Exception as e:
            logger.exception("[SAVE] Error saving conversation: %s", e)
            raise

    async def create_chat_completion(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        """Create a chat completion with tool support."""
        completion_kwargs, session, model, messages = await self._prepare_completion(request)

        start_time = time.monotonic()
        response = await litellm.acompletion(**completion_kwargs)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        message = response.choices[0].message
        content = message.content or ""
        usage = response.usage

        # Check if LLM wants to use tools
        if message.tool_calls:
            logger.info("[TOOL] LLM requested %d tool calls", len(message.tool_calls))

            # Execute tools
            tool_results = await self._execute_tool_calls(message.tool_calls)

            # Build new messages with tool calls and results
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in message.tool_calls]
            })
            messages.extend(tool_results)

            # Re-call LLM with tool results
            completion_kwargs["messages"] = messages
            # Remove tools for second call to avoid loops
            completion_kwargs.pop("tools", None)
            completion_kwargs.pop("tool_choice", None)

            logger.info("[TOOL] Re-calling LLM with tool results")
            final_response = await litellm.acompletion(**completion_kwargs)
            content = final_response.choices[0].message.content or ""
            usage = final_response.usage
            latency_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            "Chat completion: model=%s tokens=%d latency=%dms",
            model, usage.total_tokens, latency_ms,
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
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
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
        completion_kwargs, session, model, messages = await self._prepare_completion(request)
        completion_kwargs["stream"] = True

        start_time = time.monotonic()

        response = await litellm.acompletion(**completion_kwargs)

        full_content = ""
        tool_calls_accum: Dict[int, Dict[str, Any]] = {}
        has_tool_calls = False

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
                # Don't yield tool call chunks to client
                continue

            # Regular content - yield to client immediately
            content = delta.content or ""
            if content:
                full_content += content
                yield f"data: {json.dumps(chunk.model_dump())}\n\n"
            # Skip chunks with only reasoning_content and no actual content

        # If LLM requested tool calls, execute and stream final answer
        if has_tool_calls:
            tool_calls_list = [tool_calls_accum[i] for i in sorted(tool_calls_accum.keys())]
            logger.info("[TOOL STREAM] LLM requested %d tool calls", len(tool_calls_list))

            # Execute tools
            tool_results = await self._execute_tool_calls(tool_calls_list)

            # Build messages for second call
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
            final_response = await litellm.acompletion(**completion_kwargs)

            async for chunk in final_response:
                content = chunk.choices[0].delta.content or ""
                if content:
                    full_content += content
                    yield f"data: {json.dumps(chunk.model_dump())}\n\n"

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
