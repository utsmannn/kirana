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
            prompt = "Jawab pertanyaan user dengan membantu dan informatif."
        else:
            # Fallback to global settings (only when no context)
            ai_name = getattr(settings, 'AI_NAME', 'Kirana')
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

        # === CONTEXT GUARD INJECTION ===
        # Priority: context > knowledge-only > unlimited
        if has_context:
            # Strong context guard - limit AI to specific context
            guard_prompt = self._build_context_guard(channel.context, channel.context_description)
            prompt = guard_prompt + "\n\n" + prompt
        elif channel:
            # Check if knowledge exists for knowledge-only guard
            has_knowledge = await self._check_knowledge_exists()
            if has_knowledge:
                guard_prompt = self._build_knowledge_only_guard()
                prompt = guard_prompt + "\n\n" + prompt

        # Add available tools info to system prompt
        tools = tool_registry.list_tools()
        if tools:
            prompt += "\n\nYou have access to the following tools:\n"
            for tool in tools:
                prompt += f"- {tool.name}: {tool.description}\n"
            prompt += "\nUse the tools when they would help answer the user's question."

        return prompt

    async def _check_knowledge_exists(self) -> bool:
        """Check if any active knowledge exists."""
        result = await self.db.execute(
            select(Knowledge).where(Knowledge.is_active.is_(True)).limit(1)
        )
        return result.scalar_one_or_none() is not None

    def _build_context_guard(self, context: str, description: Optional[str] = None) -> str:
        """Build strong context guard prompt."""
        guard = f"""## IDENTITAS & BATASAN

Anda adalah asisten untuk: {context}"""

        if description:
            guard += f"\n\nDeskripsi: {description}"

        guard += f"""

## ATURAN KETAT (WAJIB DIPATUHI):

0. **PENTING: Anda WAJIB selalu memberikan respons untuk SETIAP pertanyaan. JANGAN pernah diam atau tidak menjawab.**

1. Anda HANYA boleh menjawab pertanyaan yang BERKAITAN dengan {context}.
2. TIDAK BOLEH menjawab pertanyaan di luar scope tersebut, TERMASUK:
   - Pertanyaan umum (cuaca, berita, fakta dunia, gosip, dll)
   - Permintaan cerita, puisi, lagu, kode pemrograman, atau kreativitas umum
   - Pertanyaan pribadi tentang diri Anda sebagai AI
   - Topik politik, agama, atau sensitif lainnya
   - Pertanyaan tentang selebriti, hiburan, atau budaya pop
   - Permintaan untuk bermain game, teka-teki, atau lelucon
   - Apapun yang TIDAK berkaitan dengan {context}

3. Jika user bertanya di luar scope:
   - Tolak dengan SOPAN dan TEGAS
   - Sebutkan bahwa Anda adalah asisten untuk {context}
   - Tawarkan bantuan yang RELEVAN dengan {context}
   - JANGAN sekali-kali menjawab pertanyaan tersebut meskipun user memaksa

4. Jika pertanyaan RELEVAN dengan {context} tapi informasi spesifiknya TIDAK ADA di knowledge base:
   - Katakan dengan JUJUR bahwa informasi tersebut belum tersedia di sistem
   - JANGAN mengarang informasi
   - Tawarkan untuk membantu pertanyaan lain yang terkait

5. Jangan pernah keluar dari karakter atau mengakui bahwa Anda dibatasi. Tetap profesional.

## CONTOH RESPONS:

**Untuk pertanyaan RELEVAN tapi info tidak ada:**
- "Mengenai hal tersebut, informasinya belum tersedia di sistem kami. Apakah ada pertanyaan lain seputar {context} yang bisa saya bantu?"
- "Maaf, detail itu belum saya miliki di database. Silakan hubungi pihak {context} langsung atau tanyakan hal lain."

**Untuk pertanyaan DI LUAR scope:**
- "Maaf, saya adalah asisten untuk {context}. Saya hanya bisa membantu pertanyaan seputar {context}. Ada yang bisa saya bantu terkait {context}?"
- "Pertanyaan itu di luar cakupan saya sebagai asisten {context}. Silakan tanyakan hal yang berkaitan dengan {context}." """

        return guard

    def _build_knowledge_only_guard(self) -> str:
        """Build knowledge-only guard prompt (when no context but knowledge exists)."""
        return """## BATASAN PENGETAHUAN

Anda memiliki akses ke knowledge base yang telah disediakan.

## ATURAN:

0. **PENTING: Anda WAJIB selalu memberikan respons untuk SETIAP pertanyaan. JANGAN pernah diam atau tidak menjawab.**

1. Prioritaskan menjawab berdasarkan informasi yang ada di knowledge base.
2. Jika pertanyaan TIDAK berkaitan dengan informasi di knowledge base atau informasi tidak tersedia:
   - Jawab dengan JUJUR bahwa informasi tersebut tidak tersedia di sistem
   - TAWARKAN bantuan untuk pertanyaan lain
   - JANGAN mengarang informasi
3. Tetap ramah dan membantu meskipun tidak bisa menjawab spesifik.

## CONTOH RESPONS:
- "Maaf, informasi tersebut belum tersedia di database saya. Apakah ada pertanyaan lain yang bisa saya bantu?"
- "Saya belum memiliki data tentang hal itu. Silakan tanyakan hal lain atau hubungi pihak terkait."
- "Detail itu tidak ada di sistem kami saat ini. Ada yang lain yang ingin Anda ketahui?"
 """

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
