<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';

	// Get channel_id and token from URL
	let channelId = $derived($page.params.channel_id);
	let token = $derived($page.url.searchParams.get('token'));

	// Theme from URL params (with defaults)
	// URL params override config for flexibility
	let urlTheme = $derived($page.url.searchParams.get('theme'));
	let urlFont = $derived($page.url.searchParams.get('font'));
	let urlPrimaryColor = $derived($page.url.searchParams.get('primaryColor'));
	let urlBgColor = $derived($page.url.searchParams.get('bgColor'));
	let urlTextColor = $derived($page.url.searchParams.get('textColor'));

	// State
	let loading = $state(true);
	let error = $state<string | null>(null);
	let config = $state<{
		embed_enabled: boolean;
		public: boolean;
		save_history: boolean;
		stream_mode: boolean;
		theme?: string;
		primary_color?: string;
		bg_color?: string;
		text_color?: string;
		font_family?: string;
	} | null>(null);

	// Computed theme values (URL params > config > defaults)
	let theme = $derived(urlTheme || config?.theme || 'dark');
	let fontFamily = $derived(urlFont || config?.font_family || 'system-ui');
	let primaryColor = $derived(urlPrimaryColor || config?.primary_color || '#6366f1');
	let bgColor = $derived(urlBgColor || config?.bg_color || (theme === 'light' ? '#ffffff' : '#09090b'));
	let textColor = $derived(urlTextColor || config?.text_color || (theme === 'light' ? '#1f2937' : '#f4f4f5'));
	let inputBg = $derived((theme === 'light' ? '#f3f4f6' : '#18181b'));

	// Chat state
	let messages = $state<{ role: string; content: string }[]>([]);
	let input = $state('');
	let streaming = $state(false);
	let waiting = $state(false); // For non-stream mode

	// History key per channel
	const HISTORY_KEY = 'kirana_embed_history';

	// Computed CSS variables
	const cssVars = $derived(`
		--primary-color: ${primaryColor};
		--bg-color: ${bgColor};
		--text-color: ${textColor};
		--input-bg: ${inputBg};
		--font-family: ${fontFamily}, system-ui, sans-serif;
	`);

	onMount(async () => {
		// Load config from API
		try {
			const resp = await fetch(`/v1/channels/${channelId}/embed`, {
				headers: {
					Authorization: `Bearer kirana-default-api-key-change-me`
				}
			});

			if (!resp.ok) {
				error = 'Embed not configured for this channel';
				loading = false;
				return;
			}

			config = await resp.json();

			// Load history from localStorage if enabled
			if (config.save_history) {
				const saved = localStorage.getItem(`${HISTORY_KEY}_${channelId}`);
				if (saved) {
					try {
						messages = JSON.parse(saved);
					} catch {
						messages = [];
					}
				}
			}
		} catch (e) {
			error = 'Failed to load embed configuration';
		}
		loading = false;
	});

	// Save history when messages change
	$effect(() => {
		if (config?.save_history && messages.length > 0) {
			localStorage.setItem(`${HISTORY_KEY}_${channelId}`, JSON.stringify(messages));
		}
	});

	async function doSendMessage() {
		if (!input.trim() || streaming || waiting) return;

		const userMessage = input.trim();
		input = '';

		messages = [...messages, { role: 'user', content: userMessage }];

		const streamMode = config?.stream_mode ?? true;

		if (streamMode) {
			// Stream mode: add empty assistant message and stream into it
			messages = [...messages, { role: 'assistant', content: '' }];
			const assistantIdx = messages.length - 1;
			streaming = true;

			try {
				await streamResponse(userMessage, (chunk) => {
					messages[assistantIdx] = {
						...messages[assistantIdx],
						content: messages[assistantIdx].content + chunk
					};
				});
			} catch (e) {
				messages[assistantIdx] = {
					role: 'assistant',
					content: `Error: ${e instanceof Error ? e.message : 'Failed to get response'}`
				};
			} finally {
				streaming = false;
			}
		} else {
			// Non-stream mode: wait for complete response
			waiting = true;

			try {
				const response = await fetchCompleteResponse(userMessage);
				messages = [...messages, { role: 'assistant', content: response }];
			} catch (e) {
				messages = [...messages, {
					role: 'assistant',
					content: `Error: ${e instanceof Error ? e.message : 'Failed to get response'}`
				}];
			} finally {
				waiting = false;
			}
		}
	}

	async function streamResponse(
		userMessage: string,
		onChunk: (chunk: string) => void
	): Promise<void> {
		const url = token
			? `/v1/chat/completions?embed_token=${token}`
			: '/v1/chat/completions';

		const response = await fetch(url, {
			method: 'POST',
			headers: {
				'Authorization': `Bearer kirana-default-api-key-change-me`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				model: 'default',
				messages: messages.slice(0, -1).map(m => ({ role: m.role, content: m.content })),
				stream: true
			})
		});

		if (!response.ok) {
			const err = await response.json();
			throw new Error(err.detail || 'Request failed');
		}

		const reader = response.body?.getReader();
		if (!reader) throw new Error('No stream');

		const decoder = new TextDecoder();
		let buffer = '';

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split('\n');
			buffer = lines.pop() || '';

			for (const line of lines) {
				if (line.startsWith('data: ')) {
					const data = line.slice(6);
					if (data === '[DONE]') continue;
					try {
						const parsed = JSON.parse(data);
						const content = parsed.choices?.[0]?.delta?.content;
						if (content) {
							onChunk(content);
						}
					} catch {
						// skip
					}
				}
			}
		}
	}

	async function fetchCompleteResponse(userMessage: string): Promise<string> {
		const url = token
			? `/v1/chat/completions?embed_token=${token}`
			: '/v1/chat/completions';

		const allMessages = messages.map(m => ({ role: m.role, content: m.content }));

		const response = await fetch(url, {
			method: 'POST',
			headers: {
				'Authorization': `Bearer kirana-default-api-key-change-me`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				model: 'default',
				messages: allMessages,
				stream: false
			})
		});

		if (!response.ok) {
			const err = await response.json();
			throw new Error(err.detail || 'Request failed');
		}

		const data = await response.json();
		return data.choices?.[0]?.message?.content || '';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			doSendMessage();
		}
	}

	function clearHistory() {
		messages = [];
		localStorage.removeItem(`${HISTORY_KEY}_${channelId}`);
	}

	const isLoading = $derived(streaming || waiting);
</script>

<svelte:head>
	<title>Chat</title>
	<style>
		/* Reset for embed context */
		body {
			margin: 0;
			padding: 0;
		}
	</style>
</svelte:head>

{#if loading}
	<div class="loading-screen" style="background-color: {bgColor}; color: {textColor}">
		<div class="spinner"></div>
	</div>
{:else if error}
	<div class="error-screen" style="background-color: {bgColor}; color: #ef4444;">
		{error}
	</div>
{:else}
	<div class="embed-container" style={cssVars}>
		<!-- Header -->
		<div class="header">
			<span class="header-title">Chat</span>
			{#if messages.length > 0}
				<button onclick={clearHistory} class="clear-btn">
					Clear
				</button>
			{/if}
		</div>

		<!-- Messages -->
		<div class="messages-container">
			{#if messages.length === 0}
				<div class="empty-state">
					<p>Start a conversation</p>
				</div>
			{:else}
				<div class="messages-list">
					{#each messages as message}
						<div class="message-wrapper {message.role}">
							<div class="message {message.role}">
								{message.content || (isLoading && message.role === 'assistant' ? '' : '')}
							</div>
						</div>
					{/each}

					<!-- Typing indicator -->
					{#if isLoading && (config?.stream_mode ? messages[messages.length - 1]?.content !== '' : true)}
						{#if !config?.stream_mode || messages.length === 0 || messages[messages.length - 1]?.role !== 'assistant'}
							<div class="message-wrapper assistant">
								<div class="message assistant typing">
									<span class="dot"></span>
									<span class="dot"></span>
									<span class="dot"></span>
								</div>
							</div>
						{/if}
					{/if}
				</div>
			{/if}
		</div>

		<!-- Input -->
		<div class="input-container">
			<input
				type="text"
				bind:value={input}
				placeholder="Type a message..."
				disabled={isLoading}
				onkeydown={handleKeydown}
				class="input"
			/>
			<button
				onclick={doSendMessage}
				disabled={!input.trim() || isLoading}
				class="send-btn"
			>
				<svg class="send-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
				</svg>
			</button>
		</div>
	</div>
{/if}

<style>
	.loading-screen,
	.error-screen {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 100%;
		height: 100%;
		font-family: var(--font-family, system-ui);
	}

	.spinner {
		width: 24px;
		height: 24px;
		border: 2px solid var(--text-color, #f4f4f5);
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.embed-container {
		display: flex;
		flex-direction: column;
		width: 100%;
		height: 100%;
		background-color: var(--bg-color, #09090b);
		color: var(--text-color, #f4f4f5);
		font-family: var(--font-family, system-ui);
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.625rem 1rem;
		border-bottom: 1px solid color-mix(in srgb, var(--text-color) 15%, transparent);
		flex-shrink: 0;
	}

	.header-title {
		font-size: 0.875rem;
		font-weight: 500;
	}

	.clear-btn {
		font-size: 0.75rem;
		color: color-mix(in srgb, var(--text-color) 50%, transparent);
		background: none;
		border: none;
		cursor: pointer;
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		transition: color 0.15s;
	}

	.clear-btn:hover {
		color: var(--text-color);
	}

	.messages-container {
		flex: 1;
		overflow-y: auto;
		padding: 1rem;
		min-height: 0;
	}

	.empty-state {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
	}

	.empty-state p {
		font-size: 0.875rem;
		color: color-mix(in srgb, var(--text-color) 40%, transparent);
	}

	.messages-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		max-width: 100%;
	}

	.message-wrapper {
		display: flex;
	}

	.message-wrapper.user {
		justify-content: flex-end;
	}

	.message-wrapper.assistant {
		justify-content: flex-start;
	}

	.message {
		max-width: 85%;
		padding: 0.625rem 1rem;
		border-radius: 1rem;
		font-size: 0.875rem;
		line-height: 1.5;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.message.user {
		background-color: var(--primary-color, #6366f1);
		color: white;
		border-bottom-right-radius: 0.25rem;
	}

	.message.assistant {
		background-color: color-mix(in srgb, var(--text-color) 10%, transparent);
		color: var(--text-color);
		border-bottom-left-radius: 0.25rem;
	}

	/* Typing indicator */
	.message.typing {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.75rem 1rem;
	}

	.dot {
		width: 0.5rem;
		height: 0.5rem;
		background-color: color-mix(in srgb, var(--text-color) 50%, transparent);
		border-radius: 50%;
		animation: bounce 1.4s infinite ease-in-out both;
	}

	.dot:nth-child(1) { animation-delay: -0.32s; }
	.dot:nth-child(2) { animation-delay: -0.16s; }
	.dot:nth-child(3) { animation-delay: 0s; }

	@keyframes bounce {
		0%, 80%, 100% {
			transform: scale(0.6);
			opacity: 0.4;
		}
		40% {
			transform: scale(1);
			opacity: 1;
		}
	}

	.input-container {
		display: flex;
		gap: 0.5rem;
		padding: 0.75rem;
		border-top: 1px solid color-mix(in srgb, var(--text-color) 15%, transparent);
		flex-shrink: 0;
	}

	.input {
		flex: 1;
		padding: 0.625rem 0.875rem;
		font-size: 0.875rem;
		background-color: var(--input-bg, #18181b);
		color: var(--text-color);
		border: 1px solid color-mix(in srgb, var(--text-color) 15%, transparent);
		border-radius: 0.5rem;
		outline: none;
		font-family: inherit;
		transition: border-color 0.15s;
	}

	.input:focus {
		border-color: var(--primary-color, #6366f1);
	}

	.input::placeholder {
		color: color-mix(in srgb, var(--text-color) 40%, transparent);
	}

	.input:disabled {
		opacity: 0.5;
	}

	.send-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2.5rem;
		height: 2.5rem;
		background-color: var(--primary-color, #6366f1);
		color: white;
		border: none;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: opacity 0.15s, filter 0.15s;
		flex-shrink: 0;
	}

	.send-btn:hover:not(:disabled) {
		filter: brightness(1.1);
	}

	.send-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.send-icon {
		width: 1.25rem;
		height: 1.25rem;
	}
</style>
