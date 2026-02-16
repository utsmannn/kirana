<script lang="ts">
	import { onMount } from 'svelte';
	import {
		streamChat,
		sendChat,
		getSessions,
		createSession,
		getSessionMessages,
		getConfig,
		getChannels,
		getStreamChunks,
		ApiError,
		type ChatMessage,
		type Session,
		type SessionMessage,
		type Channel
	} from '$lib/api';
	import { adminToken } from '$lib/stores.svelte';
	import { showToast } from '$lib/toast.svelte';
	import Button from '$lib/components/Button.svelte';

	interface DisplayMessage {
		role: 'user' | 'assistant';
		content: string;
	}

	// UUID generator for stream_id
	function generateUUID(): string {
		return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
			const r = (Math.random() * 16) | 0;
			const v = c === 'x' ? r : (r & 0x3) | 0x8;
			return v.toString(16);
		});
	}

	let messages = $state<DisplayMessage[]>([]);
	let input = $state('');
	let streaming = $state(false);
	let model = $state('');

	// Sessions
	let sessions = $state<Session[]>([]);
	let currentSessionId = $state<string | null>(null);
	let loadingSessions = $state(false);
	let showSessions = $state(false);
	let sessionName = $state('');
	let creatingSess = $state(false);
	let initialized = false;

	// Channels
	let channels = $state<Channel[]>([]);
	let selectedChannelId = $state<string>('');
	let loadingChannels = $state(false);

	// Stream toggle
	let useStream = $state(true);
	const STREAM_STORAGE_KEY = 'kirana_use_stream';

	// Stream resume
	const RESUME_STORAGE_KEY = 'kirana_stream_resume';
	let resuming = $state(false);

	interface ResumeState {
		stream_id: string;
		session_id: string | null;
		user_message: string;
	}

	// Auto-scroll
	let chatContainer: HTMLDivElement | undefined = $state();

	const SESSION_STORAGE_KEY = 'kirana_current_session_id';

	const currentSessionName = $derived(
		sessions.find((s) => s.id === currentSessionId)?.name ?? 'New Chat'
	);

	$effect(() => {
		if (chatContainer && messages.length > 0) {
			chatContainer.scrollTop = chatContainer.scrollHeight;
		}
	});

	// Only persist AFTER initialization
	$effect(() => {
		const id = currentSessionId;
		if (!initialized) return;
		if (id) {
			localStorage.setItem(SESSION_STORAGE_KEY, id);
		} else {
			localStorage.removeItem(SESSION_STORAGE_KEY);
		}
	});

	// Track pending resume state for visibilitychange save
	let pendingResume: ResumeState | null = $state(null);

	onMount(() => {
		async function init() {
			if (!adminToken.value) return;

			// Restore stream preference
			const savedStream = localStorage.getItem(STREAM_STORAGE_KEY);
			if (savedStream !== null) {
				useStream = savedStream !== 'false';
			}

			await Promise.all([loadSessions(), loadChannels()]);
			try {
				const config = await getConfig();
				model = config.model || 'default';
			} catch {
				// config may not be available yet
			}

			// Restore session from localStorage
			const savedId = localStorage.getItem(SESSION_STORAGE_KEY);
			if (savedId) {
				const session = sessions.find(s => s.id === savedId);
				if (session) {
					await selectSession(session);
				} else {
					localStorage.removeItem(SESSION_STORAGE_KEY);
				}
			}

			// Check for stream to resume
			const resumeJson = localStorage.getItem(RESUME_STORAGE_KEY);
			if (resumeJson) {
				try {
					const resume: ResumeState = JSON.parse(resumeJson);
					await resumeStream(resume);
				} catch {
					localStorage.removeItem(RESUME_STORAGE_KEY);
				}
			}

			initialized = true;
		}
		init();

		// Save pending state on page hide/refresh
		const handleVisibilityChange = () => {
			if (document.visibilityState === 'hidden' && pendingResume) {
				localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(pendingResume));
			}
		};
		document.addEventListener('visibilitychange', handleVisibilityChange);

		return () => {
			document.removeEventListener('visibilitychange', handleVisibilityChange);
		};
	});

	async function loadSessions() {
		loadingSessions = true;
		try {
			const result = await getSessions(undefined, 1, 50);
			sessions = result.items;
		} catch {
			// ignore
		} finally {
			loadingSessions = false;
		}
	}

	async function loadChannels() {
		loadingChannels = true;
		try {
			const result = await getChannels();
			channels = result.channels || [];
			const defaultChannel = result.default_channel;
			if (defaultChannel) {
				selectedChannelId = defaultChannel.id;
			} else if (channels.length > 0) {
				selectedChannelId = channels[0].id;
			}
		} catch {
			// ignore
		} finally {
			loadingChannels = false;
		}
	}

	async function selectSession(session: Session) {
		currentSessionId = session.id;
		showSessions = false;

		try {
			const resp = await getSessionMessages(session.id);
			messages = (resp.messages || []).map((m: SessionMessage) => ({
				role: m.role as 'user' | 'assistant',
				content: m.content
			}));
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		}
	}

	async function handleNewSession(e: Event) {
		e.preventDefault();
		if (!sessionName.trim()) return;

		creatingSess = true;
		try {
			const sessionData = {
				name: sessionName.trim(),
				channel_id: selectedChannelId || undefined
			};
			const session = await createSession(sessionData);
			sessions = [session, ...sessions];
			currentSessionId = session.id;
			messages = [];
			sessionName = '';
			showSessions = false;
			showToast('Session created', 'success');
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			creatingSess = false;
		}
	}

	function startNewChat() {
		currentSessionId = null;
		messages = [];
		showSessions = false;
	}

	function toggleStream() {
		useStream = !useStream;
		localStorage.setItem(STREAM_STORAGE_KEY, String(useStream));
	}

	async function resumeStream(resume: ResumeState) {
		streaming = true;
		resuming = true;

		try {
			// Load session messages if session exists
			if (resume.session_id) {
				currentSessionId = resume.session_id;
				try {
					const resp = await getSessionMessages(resume.session_id);
					const loaded = (resp.messages || []).map((m: SessionMessage) => ({
						role: m.role as 'user' | 'assistant',
						content: m.content
					}));
					// If last message is assistant with content, stream already saved
					if (loaded.length > 0 && loaded[loaded.length - 1].role === 'assistant' && loaded[loaded.length - 1].content) {
						messages = loaded;
						return;
					}
					messages = loaded;
				} catch {
					// ignore - will use user_message fallback below
				}
			}

			// Ensure user message is visible (backend saves after stream completes, so it might not be in session yet)
			const lastUserMsg = messages.findLast(m => m.role === 'user');
			if (!lastUserMsg || lastUserMsg.content !== resume.user_message) {
				messages = [...messages, { role: 'user', content: resume.user_message }];
			}

			// Add empty assistant message for streaming content
			messages = [...messages, { role: 'assistant', content: '' }];
			const assistantIdx = messages.length - 1;

			// Poll for stream chunks
			let offset = 0;
			let done = false;
			let retries = 0;

			while (!done && retries < 3) {
				try {
					const result = await getStreamChunks(resume.stream_id, undefined, offset);
					retries = 0;

					for (const chunk of result.chunks) {
						messages[assistantIdx] = {
							...messages[assistantIdx],
							content: messages[assistantIdx].content + chunk
						};
					}

					offset = result.total;
					done = result.done;

					if (!done) {
						await new Promise(r => setTimeout(r, 500));
					}
				} catch {
					retries++;
					if (retries >= 3) {
						if (!messages[assistantIdx].content) {
							messages[assistantIdx] = { role: 'assistant', content: 'Stream expired. Please send your message again.' };
						}
						break;
					}
					await new Promise(r => setTimeout(r, 1000));
				}
			}
		} finally {
			streaming = false;
			resuming = false;
			pendingResume = null;
			localStorage.removeItem(RESUME_STORAGE_KEY);
		}
	}

	async function doSendMessage() {
		if (!input.trim() || streaming) return;

		const activeSessionId = currentSessionId;
		const userMessage = input.trim();
		input = '';

		messages = [...messages, { role: 'user', content: userMessage }];

		const apiMessages: ChatMessage[] = messages.map((m) => ({
			role: m.role,
			content: m.content
		}));

		messages = [...messages, { role: 'assistant', content: '' }];
		const assistantIdx = messages.length - 1;

		streaming = true;

		// Generate stream_id for resume support
		const streamId = generateUUID();

		// Save resume state immediately (before fetch starts)
		if (useStream) {
			pendingResume = {
				stream_id: streamId,
				session_id: activeSessionId,
				user_message: userMessage
			};
			localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(pendingResume));
		}

		try {
			if (useStream) {
				const gen = streamChat({
					model: model || 'default',
					messages: apiMessages,
					stream: true,
					stream_id: streamId,
					session_id: activeSessionId ?? undefined
				}, undefined, (sid: string) => {
					// Update resume state with stream_id
					pendingResume = {
						stream_id: sid,
						session_id: activeSessionId,
						user_message: userMessage
					};
					localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(pendingResume));
				});

				for await (const chunk of gen) {
					messages[assistantIdx] = {
						...messages[assistantIdx],
						content: messages[assistantIdx].content + chunk
					};
				}
			} else {
				const response = await sendChat({
					model: model || 'default',
					messages: apiMessages,
					stream: false,
					session_id: activeSessionId ?? undefined
				}, undefined);

				const content = response.choices?.[0]?.message?.content || '';
				messages[assistantIdx] = { role: 'assistant', content };
			}
		} catch (err) {
			if (err instanceof ApiError) {
				messages[assistantIdx] = { role: 'assistant', content: `Error: ${err.message}` };
			} else {
				messages[assistantIdx] = { role: 'assistant', content: 'Error: Failed to get response' };
			}
		} finally {
			streaming = false;
			pendingResume = null;
			localStorage.removeItem(RESUME_STORAGE_KEY);
			if (!activeSessionId) {
				loadSessions().catch(() => {});
			}
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			doSendMessage();
		}
	}
</script>

<style>
	:global(.markdown-content p) {
		margin-bottom: 0.75rem;
	}
	:global(.markdown-content p:last-child) {
		margin-bottom: 0;
	}
	:global(.markdown-content pre) {
		background-color: #18181b;
		padding: 1rem;
		border-radius: 0.5rem;
		overflow-x: auto;
		margin: 0.75rem 0;
		border: 1px solid #27272a;
	}
	:global(.markdown-content code) {
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
		font-size: 0.85em;
		background-color: rgba(255, 255, 255, 0.1);
		padding: 0.125rem 0.25rem;
		border-radius: 0.25rem;
	}
	:global(.markdown-content pre code) {
		background-color: transparent;
		padding: 0;
		font-size: 0.8rem;
	}
	:global(.markdown-content ul, .markdown-content ol) {
		margin: 0.75rem 0;
		padding-left: 1.5rem;
	}
	:global(.markdown-content ul) {
		list-style-type: disc;
	}
	:global(.markdown-content ol) {
		list-style-type: decimal;
	}
	:global(.markdown-content li) {
		margin-bottom: 0.25rem;
	}
	:global(.markdown-content blockquote) {
		border-left: 3px solid #4f46e5;
		padding-left: 1rem;
		margin: 1rem 0;
		font-style: italic;
		color: #a1a1aa;
	}
	:global(.markdown-content a) {
		color: #6366f1;
		text-decoration: underline;
	}
</style>

<svelte:head>
	<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</svelte:head>

<div class="flex h-full flex-col">
	<!-- Chat header -->
	<div class="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
		<div class="flex items-center gap-3">
			<button
				onclick={() => (showSessions = !showSessions)}
				class="rounded-md px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:bg-zinc-800"
			>
				<span class="hidden sm:inline">{currentSessionName}</span>
				<span class="sm:hidden">Sessions</span>
				<svg
					class="ml-1.5 inline h-3 w-3 text-zinc-500"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M19 9l-7 7-7-7"
					/>
				</svg>
			</button>
			{#if model}
				<span class="rounded bg-zinc-800 px-2 py-0.5 font-mono text-xs text-zinc-400">
					{model}
				</span>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<button
				onclick={toggleStream}
				class="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors
					{useStream
						? 'bg-emerald-600/15 text-emerald-400 hover:bg-emerald-600/25'
						: 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}"
				title={useStream ? 'Streaming enabled (click to disable)' : 'Streaming disabled (click to enable)'}
			>
				<span class="h-1.5 w-1.5 rounded-full {useStream ? 'bg-emerald-400' : 'bg-zinc-500'}"></span>
				{useStream ? 'Stream' : 'Sync'}
			</button>
			{#if streaming}
				<span class="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs bg-indigo-600/15 text-indigo-400">
					<svg class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
					</svg>
					{resuming ? 'Resuming' : useStream ? 'SSE' : 'HTTP'}
				</span>
			{/if}
			<Button variant="ghost" size="sm" onclick={startNewChat}>
				New Chat
			</Button>
		</div>
	</div>

	<div class="relative flex flex-1 overflow-hidden">
		<!-- Sessions sidebar -->
		{#if showSessions}
			<div
				class="absolute inset-y-0 left-0 z-30 w-72 border-r border-zinc-800 bg-zinc-900 shadow-xl lg:relative lg:shadow-none"
			>
				<div class="flex h-full flex-col">
					<div class="border-b border-zinc-800 p-3 space-y-3">
						<form onsubmit={handleNewSession} class="flex gap-2">
							<input
								type="text"
								bind:value={sessionName}
								placeholder="Session name..."
								class="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none"
							/>
							<Button type="submit" size="sm" loading={creatingSess}>Create</Button>
						</form>
						<div>
							<select
								bind:value={selectedChannelId}
								class="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-100 focus:border-indigo-500 focus:outline-none"
								disabled={loadingChannels}
							>
								{#each channels as channel}
									<option value={channel.id}>
										{channel.name}{channel.is_default ? ' (Default)' : ''}
									</option>
								{/each}
							</select>
						</div>
					</div>

					<div class="flex-1 overflow-y-auto p-2">
						{#if loadingSessions}
							<div class="p-4 text-center text-sm text-zinc-500">Loading...</div>
						{:else if sessions.length === 0}
							<div class="p-4 text-center text-sm text-zinc-500">No sessions yet</div>
						{:else}
							{#each sessions as session}
								<button
									onclick={() => selectSession(session)}
									class="mb-1 w-full rounded-lg px-3 py-2 text-left transition-colors
										{session.id === currentSessionId
										? 'bg-indigo-600/15 text-indigo-300'
										: 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}"
								>
									<p class="truncate text-sm font-medium">{session.name}</p>
									<p class="mt-0.5 text-xs opacity-60">
										{new Date(session.created_at).toLocaleDateString()}
									</p>
								</button>
							{/each}
						{/if}
					</div>
				</div>
			</div>
		{/if}

		<!-- Chat area -->
		<div class="flex min-w-0 flex-1 flex-col">
			<!-- Messages -->
			<div bind:this={chatContainer} class="flex-1 overflow-y-auto px-4 py-6">
				{#if messages.length === 0}
					<div class="flex h-full items-center justify-center">
						<div class="text-center">
							<div
								class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-800"
							>
								<svg
									class="h-8 w-8 text-zinc-500"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="1.5"
										d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
									/>
								</svg>
							</div>
							<p class="text-lg font-medium text-zinc-300">Start a conversation</p>
							<p class="mt-1 text-sm text-zinc-500">
								{adminToken.value
									? 'Send a message to begin chatting with your AI'
									: 'Please log in to start chatting'}
							</p>
						</div>
					</div>
				{:else}
					<div class="mx-auto max-w-3xl space-y-6">
						{#each messages as message, i}
							<div class="flex gap-3 {message.role === 'user' ? 'justify-end' : ''}">
								{#if message.role === 'assistant'}
									<div
										class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-xs font-bold text-white"
									>
										AI
									</div>
								{/if}
								<div
									class="max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed
										{message.role === 'user'
										? 'bg-indigo-600 text-white'
										: 'bg-zinc-800 text-zinc-200'}"
								>
									{#if message.role === 'assistant' && !message.content && streaming && i === messages.length - 1}
										<div class="flex items-center gap-2">
											<div class="flex items-center gap-1">
												<span class="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400"></span>
												<span
													class="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400"
													style="animation-delay: 0.15s"
												></span>
												<span
													class="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400"
													style="animation-delay: 0.3s"
												></span>
											</div>
											<span class="rounded px-1.5 py-0.5 text-[10px] font-medium
												{resuming
													? 'bg-indigo-600/20 text-indigo-400'
													: useStream
														? 'bg-emerald-600/20 text-emerald-400'
														: 'bg-zinc-700 text-zinc-400'}">
												{resuming ? 'Resuming' : useStream ? 'SSE' : 'HTTP'}
											</span>
										</div>
									{:else}
										{#if message.role === 'assistant'}
											<div class="prose prose-invert prose-sm max-w-none markdown-content">
												<!-- svelte-ignore svelte_dom_stringify -->
												{@html (window as any).marked ? (window as any).marked.parse(message.content) : message.content}
											</div>
										{:else}
											<p class="whitespace-pre-wrap">{message.content}</p>
										{/if}
									{/if}
								</div>
								{#if message.role === 'user'}
									<div
										class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-700 text-xs font-bold text-zinc-300"
									>
										You
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Input -->
			<div class="border-t border-zinc-800 p-4">
				<div class="mx-auto flex max-w-3xl gap-3">
					<input
						type="text"
						bind:value={input}
						placeholder={adminToken.value
							? 'Type your message...'
							: 'Please log in'}
						disabled={streaming || !adminToken.value}
						onkeydown={handleKeydown}
						class="flex-1 rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 transition-colors focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none disabled:opacity-50"
					/>
					<Button
						onclick={() => doSendMessage()}
						disabled={!input.trim() || streaming || !adminToken.value}
						loading={streaming}
					>
						Send
					</Button>
				</div>
			</div>
		</div>
	</div>
</div>
