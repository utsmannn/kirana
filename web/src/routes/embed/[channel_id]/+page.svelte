<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';

	// Get channel_id and token from URL
	let channelId = $derived($page.params.channel_id);
	let token = $derived($page.url.searchParams.get('token'));

	// State
	let loading = $state(true);
	let error = $state<string | null>(null);
	let config = $state<{
		embed_enabled: boolean;
		public: boolean;
		save_history: boolean;
	} | null>(null);

	// Chat state
	let messages = $state<{ role: string; content: string }[]>([]);
	let input = $state('');
	let streaming = $state(false);
	let apiKey = $state('');

	// History key per channel
	const HISTORY_KEY = 'kirana_embed_history';

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

			// Check token if not public
			if (!config.public && token !== config.token) {
				// Note: we don't have access to the full token from URL, so we'll send it and let server validate
			}

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
		if (!input.trim() || streaming) return;

		const userMessage = input.trim();
		input = '';

		messages = [...messages, { role: 'user', content: userMessage }];
		messages = [...messages, { role: 'assistant', content: '' }];
		const assistantIdx = messages.length - 1;

		streaming = true;

		try {
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
								messages[assistantIdx] = {
									...messages[assistantIdx],
									content: messages[assistantIdx].content + content
								};
							}
						} catch {
							// skip
						}
					}
				}
			}
		} catch (e) {
			messages[assistantIdx] = {
				role: 'assistant',
				content: `Error: ${e instanceof Error ? e.message : 'Failed to get response'}`
			};
		} finally {
			streaming = false;
		}
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
</script>

<svelte:head>
	<title>Chat</title>
</svelte:head>

{#if loading}
	<div class="flex h-screen items-center justify-center bg-zinc-950 text-zinc-400">
		Loading...
	</div>
{:else if error}
	<div class="flex h-screen items-center justify-center bg-zinc-950 text-red-400">
		{error}
	</div>
{:else}
	<div class="flex h-screen flex-col bg-zinc-950">
		<!-- Header -->
		<div class="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
			<span class="text-sm font-medium text-zinc-300">Chat</span>
			{#if messages.length > 0}
				<button
					onclick={clearHistory}
					class="text-xs text-zinc-500 hover:text-zinc-300"
				>
					Clear
				</button>
			{/if}
		</div>

		<!-- Messages -->
		<div class="flex-1 overflow-y-auto px-4 py-4">
			{#if messages.length === 0}
				<div class="flex h-full items-center justify-center">
					<p class="text-sm text-zinc-500">Start a conversation</p>
				</div>
			{:else}
				<div class="mx-auto max-w-md space-y-4">
					{#each messages as message}
						<div class="flex {message.role === 'user' ? 'justify-end' : ''}">
							<div
								class="max-w-[80%] rounded-2xl px-4 py-2 text-sm
									{message.role === 'user'
										? 'bg-indigo-600 text-white'
										: 'bg-zinc-800 text-zinc-200'}"
							>
								{message.content || (streaming && message.role === 'assistant' ? '...' : '')}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Input -->
		<div class="border-t border-zinc-800 p-3">
			<div class="mx-auto flex gap-2 max-w-md">
				<input
					type="text"
					bind:value={input}
					placeholder="Type a message..."
					disabled={streaming}
					onkeydown={handleKeydown}
					class="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
				/>
				<button
					onclick={doSendMessage}
					disabled={!input.trim() || streaming}
					class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
				>
					Send
				</button>
			</div>
		</div>
	</div>
{/if}
