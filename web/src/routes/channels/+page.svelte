<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getProviders,
		getChannels,
		getTools,
		createChannel,
		updateChannel,
		deleteChannel,
		setDefaultChannel,
		getEmbedConfig,
		configureEmbed,
		disableEmbed,
		ApiError,
		type Provider,
		type Channel,
		type Tool,
		type ChannelCreate,
		type ToolsResponse,
		type EmbedConfigResponse
	} from '$lib/api';
	import { apiKey } from '$lib/stores.svelte';
	import { showToast } from '$lib/toast.svelte';
	import Button from '$lib/components/Button.svelte';
	import Modal from '$lib/components/Modal.svelte';

	// Data
	let providers = $state<Provider[]>([]);
	let channels = $state<Channel[]>([]);
	let defaultChannel = $state<Channel | null>(null);
	let tools = $state<Tool[]>([]);
	let loading = $state(true);

	// Modal states
	let showChannelModal = $state(false);
	let editingChannel = $state<Channel | null>(null);
	let saving = $state(false);

	// Channel form
	let channelForm = $state({
		name: '',
		provider_id: '',
		system_prompt: '',
		personality_name: '',
		context: '',
		context_description: ''
	});

	// Embed modal
	let showEmbedModal = $state(false);
	let embedChannel = $state<Channel | null>(null);
	let embedConfig = $state<EmbedConfigResponse | null>(null);
	let embedLoading = $state(false);
	let embedSaving = $state(false);
	let embedForm = $state({
		public: true,
		save_history: true,
		stream_mode: true,
		regenerate_token: false,
		theme: 'dark',
		primary_color: '#6366f1',
		bg_color: '',
		text_color: '',
		font_family: '',
		bubble_style: 'rounded',
		header_title: ''
	});

	onMount(async () => {
		if (!apiKey.value) {
			loading = false;
			return;
		}
		await loadData();
	});

	async function loadData() {
		loading = true;
		try {
			const [providersResult, channelsResult, toolsResult] = await Promise.all([
				getProviders(apiKey.value),
				getChannels(apiKey.value).catch(() => ({ channels: [], default_channel: null })),
				getTools(apiKey.value).catch(() => ({ tools: [] }))
			]);

			providers = providersResult.providers || [];
			channels = channelsResult.channels || [];
			defaultChannel = channelsResult.default_channel;
			tools = toolsResult.tools || [];
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			loading = false;
		}
	}

	function openChannelModal(channel?: Channel) {
		editingChannel = channel || null;
		channelForm = {
			name: channel?.name || '',
			provider_id: channel?.provider_id || providers[0]?.id || '',
			system_prompt: channel?.system_prompt || '',
			personality_name: channel?.personality_name || '',
			context: channel?.context || '',
			context_description: channel?.context_description || ''
		};
		showChannelModal = true;
	}

	async function handleSaveChannel() {
		if (!apiKey.value) return;
		if (!channelForm.name || !channelForm.provider_id) {
			showToast('Name and provider are required', 'error');
			return;
		}

		saving = true;
		try {
			const data: ChannelCreate = {
				name: channelForm.name,
				provider_id: channelForm.provider_id,
				system_prompt: channelForm.system_prompt || undefined,
				personality_name: channelForm.personality_name || undefined,
				context: channelForm.context || undefined,
				context_description: channelForm.context_description || undefined
			};

			if (editingChannel) {
				await updateChannel(apiKey.value, editingChannel.id, data);
				showToast('Channel updated', 'success');
			} else {
				await createChannel(apiKey.value, data);
				showToast('Channel created', 'success');
			}
			showChannelModal = false;
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			} else {
				showToast('Failed to save channel', 'error');
			}
		} finally {
			saving = false;
		}
	}

	async function handleDeleteChannel(channel: Channel) {
		if (!apiKey.value) return;
		if (channel.is_default) {
			showToast('Cannot delete default channel', 'error');
			return;
		}
		if (!confirm(`Delete channel "${channel.name}"?`)) return;

		try {
			await deleteChannel(apiKey.value, channel.id);
			showToast('Channel deleted', 'success');
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		}
	}

	async function handleSetDefaultChannel(channel: Channel) {
		if (!apiKey.value) return;
		try {
			await setDefaultChannel(apiKey.value, channel.id);
			showToast(`"${channel.name}" is now default channel`, 'success');
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		}
	}

	async function openEmbedModal(channel: Channel) {
		if (!apiKey.value) return;
		embedChannel = channel;
		embedLoading = true;
		showEmbedModal = true;
		try {
			embedConfig = await getEmbedConfig(apiKey.value, channel.id);
			embedForm = {
				public: embedConfig.public,
				save_history: embedConfig.save_history,
				stream_mode: embedConfig.stream_mode,
				regenerate_token: false,
				theme: embedConfig.theme || 'dark',
				primary_color: embedConfig.primary_color || '#6366f1',
				bg_color: embedConfig.bg_color || '',
				text_color: embedConfig.text_color || '',
				font_family: embedConfig.font_family || '',
				bubble_style: embedConfig.bubble_style || 'rounded',
				header_title: embedConfig.header_title || ''
			};
		} catch (err) {
			// If no embed config exists, use defaults
			embedConfig = null;
			embedForm = {
				public: true,
				save_history: true,
				stream_mode: true,
				regenerate_token: false,
				theme: 'dark',
				primary_color: '#6366f1',
				bg_color: '',
				text_color: '',
				font_family: '',
				bubble_style: 'rounded',
				header_title: ''
			};
		} finally {
			embedLoading = false;
		}
	}

	async function handleSaveEmbed() {
		if (!apiKey.value || !embedChannel) return;
		embedSaving = true;
		try {
			embedConfig = await configureEmbed(apiKey.value, embedChannel.id, embedForm);
			showToast('Embed configuration saved', 'success');
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			} else {
				showToast('Failed to save embed config', 'error');
			}
		} finally {
			embedSaving = false;
		}
	}

	async function handleDisableEmbed() {
		if (!apiKey.value || !embedChannel) return;
		if (!confirm('Disable embed for this channel?')) return;
		embedSaving = true;
		try {
			await disableEmbed(apiKey.value, embedChannel.id);
			embedConfig = null;
			showToast('Embed disabled', 'success');
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			embedSaving = false;
		}
	}

	function getEmbedUrl(): string {
		const baseUrl = window.location.origin;
		// Use embed_url from backend response if available, but always prepend host
		if (embedConfig?.embed_url) {
			// If backend returns relative path, prepend host
			if (embedConfig.embed_url.startsWith('/')) {
				return `${baseUrl}${embedConfig.embed_url}`;
			}
			return embedConfig.embed_url;
		}
		// Fallback to constructing URL
		return `${baseUrl}/embed/${embedChannel?.id}`;
	}

	function copyEmbedUrl() {
		const url = getEmbedUrl();
		navigator.clipboard.writeText(url);
		showToast('Embed URL copied to clipboard', 'success');
	}

	function formatDate(dateStr: string): string {
		const d = new Date(dateStr);
		return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}
</script>

<div class="mx-auto max-w-4xl p-6">
	<div class="mb-8">
		<h1 class="text-2xl font-bold text-zinc-100">Channels</h1>
		<p class="mt-1 text-sm text-zinc-400">
			Manage AI personalities and behavior configurations
		</p>
	</div>

	{#if loading}
		<div class="space-y-6">
			{#each [1, 2, 3] as _}
				<div class="animate-pulse rounded-xl border border-zinc-800 bg-zinc-900 p-6">
					<div class="h-5 w-32 rounded bg-zinc-800"></div>
					<div class="mt-4 h-10 w-full rounded bg-zinc-800"></div>
				</div>
			{/each}
		</div>
	{:else}
		<div class="space-y-6">
			<!-- Channels List -->
			<section class="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
				<div class="mb-4 flex items-center justify-between">
					<div>
						<h2 class="text-base font-semibold text-zinc-200">All Channels</h2>
						<p class="text-xs text-zinc-500">
							{channels.length} {channels.length === 1 ? 'channel' : 'channels'}
						</p>
					</div>
					<Button onclick={() => openChannelModal()} size="sm">Add Channel</Button>
				</div>

				{#if channels.length === 0}
					<div class="rounded-xl border border-zinc-800 bg-zinc-900/50 p-12 text-center">
						<svg
							class="mx-auto h-10 w-10 text-zinc-600"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="1.5"
								d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
							/>
						</svg>
						<p class="mt-3 text-sm text-zinc-400">No channels configured</p>
						<p class="mt-1 text-xs text-zinc-500">
							Create a channel to define AI personality and behavior
						</p>
					</div>
				{:else}
					<div class="space-y-3">
						{#each channels as channel (channel.id)}
							<div
								class="rounded-lg border p-4 transition-colors
								{channel.is_default
									? 'border-emerald-500/50 bg-emerald-500/10'
									: 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'}"
							>
								<div class="flex items-start justify-between gap-4">
									<div class="min-w-0 flex-1">
										<div class="flex items-center gap-2">
											<p class="font-medium text-zinc-200">{channel.name}</p>
											{#if channel.is_default}
												<span class="rounded bg-emerald-600 px-1.5 py-0.5 text-xs text-white">Default</span>
											{/if}
											{#if channel.embed_enabled}
												<span class="rounded bg-indigo-600 px-1.5 py-0.5 text-xs text-white">Embed</span>
											{/if}
										</div>
										<div class="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-500">
											<span>Provider: <span class="text-zinc-400">{channel.provider_name}</span></span>
											{#if channel.personality_name}
												<span>Personality: <span class="text-zinc-400">{channel.personality_name}</span></span>
											{/if}
										</div>
										{#if channel.system_prompt}
											<div class="mt-2 rounded bg-zinc-800/50 p-2">
												<p class="text-xs text-zinc-500 line-clamp-2">{channel.system_prompt}</p>
											</div>
										{/if}
										<p class="mt-2 text-xs text-zinc-600">Created {formatDate(channel.created_at)}</p>
									</div>
									<div class="flex shrink-0 flex-col gap-2">
										{#if !channel.is_default}
											<button
												onclick={() => handleSetDefaultChannel(channel)}
												class="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-500"
											>
												Set Default
											</button>
										{/if}
										<div class="flex gap-2">
											<button
												onclick={() => openChannelModal(channel)}
												class="rounded-lg bg-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-600"
											>
												Edit
											</button>
											<button
												onclick={() => openEmbedModal(channel)}
												class="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500"
											>
												Embed
											</button>
											{#if !channel.is_default}
												<button
													onclick={() => handleDeleteChannel(channel)}
													class="rounded-lg bg-zinc-800 px-3 py-1.5 text-sm text-red-400 hover:bg-zinc-700"
												>
													Delete
												</button>
											{/if}
										</div>
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}

				<div class="mt-4 rounded-lg bg-zinc-800/30 p-4">
					<h3 class="text-sm font-medium text-zinc-300">About Channels</h3>
					<p class="mt-1 text-xs text-zinc-500">
						Channels define how the AI behaves. Each channel combines an AI provider (connection)
						with a personality configuration (system prompt). The default channel is used for
						new sessions. Create different channels for different use cases like
						"Code Assistant", "Creative Writer", or "Technical Support".
					</p>
				</div>
			</section>

			<!-- Available Tools -->
			{#if tools.length > 0}
				<section class="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
					<h2 class="mb-4 text-base font-semibold text-zinc-200">Available Tools ({tools.length})</h2>
					<div class="grid gap-2 sm:grid-cols-2">
						{#each tools as tool}
							<div class="rounded-lg bg-zinc-800/50 px-4 py-3">
								<p class="font-mono text-sm text-zinc-200">{tool.name}</p>
								<p class="mt-0.5 text-xs text-zinc-500">{tool.description}</p>
							</div>
						{/each}
					</div>
				</section>
			{/if}
		</div>
	{/if}
</div>

<!-- Channel Modal -->
<Modal
	open={showChannelModal}
	onClose={() => (showChannelModal = false)}
	title={editingChannel ? 'Edit Channel' : 'Add Channel'}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm font-medium text-zinc-300">Name</label>
			<input
				type="text"
				bind:value={channelForm.name}
				placeholder="e.g. Professional Assistant"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			/>
		</div>

		<div>
			<label class="block text-sm font-medium text-zinc-300">Provider</label>
			<select
				bind:value={channelForm.provider_id}
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			>
				{#each providers as p}
					<option value={p.id}>{p.name} ({p.model})</option>
				{/each}
			</select>
			<p class="mt-1 text-xs text-zinc-500">Select which AI provider this channel uses</p>
		</div>

		<div>
			<label class="block text-sm font-medium text-zinc-300">Personality Name (optional)</label>
			<input
				type="text"
				bind:value={channelForm.personality_name}
				placeholder="e.g. Friendly Helper, Code Expert"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			/>
		</div>

		<div class="border-t border-zinc-700 pt-4">
			<label class="block text-sm font-medium text-zinc-300">Context Guard</label>
			<p class="mt-1 text-xs text-zinc-500">
				Limit AI responses to a specific context (e.g., school, product, service).
				If empty and knowledge exists, AI will be limited to knowledge-only.
			</p>
			<div class="mt-3 space-y-3">
				<div>
					<label class="block text-xs text-zinc-400">Context Name</label>
					<input
						type="text"
						bind:value={channelForm.context}
						placeholder="e.g. SMK Negeri 1, TokoBaju App, Customer Service Bank ABC"
						class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
					/>
				</div>
				<div>
					<label class="block text-xs text-zinc-400">Context Description (optional)</label>
					<textarea
						bind:value={channelForm.context_description}
						placeholder="Detailed description of the context, e.g. school programs, product features, services offered..."
						rows="3"
						class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
					></textarea>
				</div>
			</div>
		</div>

		<div>
			<label class="block text-sm font-medium text-zinc-300">System Prompt</label>
			<textarea
				bind:value={channelForm.system_prompt}
				placeholder="You are a helpful assistant..."
				rows="5"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			></textarea>
			<p class="mt-1 text-xs text-zinc-500">
				Defines how the AI behaves in this channel. This is sent as the system message
				to the AI provider.
			</p>
		</div>

		<div class="flex justify-end gap-3 pt-4">
			<Button variant="secondary" onclick={() => (showChannelModal = false)}>Cancel</Button>
			<Button onclick={handleSaveChannel} loading={saving}>
				{editingChannel ? 'Update' : 'Create'}
			</Button>
		</div>
	</div>
</Modal>

<!-- Embed Configuration Modal -->
<Modal
	open={showEmbedModal}
	onClose={() => (showEmbedModal = false)}
	title="Embed Configuration"
>
	{#if embedLoading}
		<div class="flex justify-center py-8">
			<div class="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent"></div>
		</div>
	{:else}
		<div class="flex gap-6 min-w-[800px]">
			<!-- Left Column: Settings -->
			<div class="w-80 shrink-0 space-y-4">
				<!-- Embed URL -->
				{#if embedConfig?.embed_enabled}
					<div class="rounded-lg bg-emerald-900/30 border border-emerald-600/50 p-3">
						<div class="flex items-center gap-2 mb-2">
							<svg class="h-4 w-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
							</svg>
							<span class="text-sm font-medium text-emerald-200">Embed Enabled</span>
						</div>
						<div class="flex gap-2">
							<input
								type="text"
								readonly
								value={getEmbedUrl()}
								class="flex-1 rounded bg-zinc-800 px-2 py-1.5 text-xs text-zinc-300 border border-zinc-600"
							/>
							<button
								onclick={copyEmbedUrl}
								class="rounded bg-zinc-700 px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-600"
							>
								Copy
							</button>
						</div>
					</div>
				{/if}

				<!-- Options -->
				<div class="space-y-2">
					<label class="flex items-center gap-2 cursor-pointer">
						<input type="checkbox" bind:checked={embedForm.public} class="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600" />
						<span class="text-sm text-zinc-300">Public Access</span>
					</label>
					<label class="flex items-center gap-2 cursor-pointer">
						<input type="checkbox" bind:checked={embedForm.save_history} class="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600" />
						<span class="text-sm text-zinc-300">Save History</span>
					</label>
					<label class="flex items-center gap-2 cursor-pointer">
						<input type="checkbox" bind:checked={embedForm.stream_mode} class="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600" />
						<span class="text-sm text-zinc-300">Stream Mode</span>
					</label>
					{#if embedConfig?.embed_enabled}
						<label class="flex items-center gap-2 cursor-pointer">
							<input type="checkbox" bind:checked={embedForm.regenerate_token} class="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600" />
							<span class="text-sm text-zinc-300">Regenerate Token</span>
						</label>
					{/if}
				</div>

				<!-- Appearance -->
				<div class="border-t border-zinc-700 pt-4">
					<h4 class="text-xs font-medium text-zinc-400 mb-3 uppercase tracking-wide">Appearance</h4>
					<div class="space-y-3">
						<div>
							<label class="block text-xs text-zinc-500 mb-1">Header Title</label>
							<input type="text" bind:value={embedForm.header_title} placeholder="Chat" maxlength="50"
								class="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 focus:outline-none" />
						</div>
						<div class="grid grid-cols-2 gap-2">
							<div>
								<label class="block text-xs text-zinc-500 mb-1">Theme</label>
								<select bind:value={embedForm.theme}
									class="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-200 focus:outline-none">
									<option value="dark">Dark</option>
									<option value="light">Light</option>
								</select>
							</div>
							<div>
								<label class="block text-xs text-zinc-500 mb-1">Bubble Style</label>
								<select bind:value={embedForm.bubble_style}
									class="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-200 focus:outline-none">
									<option value="rounded">Rounded</option>
									<option value="square">Square</option>
									<option value="minimal">Minimal</option>
								</select>
							</div>
						</div>
						<div>
							<label class="block text-xs text-zinc-500 mb-1">Primary Color</label>
							<div class="flex gap-2">
								<input type="color" bind:value={embedForm.primary_color} class="h-8 w-10 rounded border border-zinc-700 bg-zinc-800 cursor-pointer" />
								<input type="text" bind:value={embedForm.primary_color} placeholder="#6366f1"
									class="flex-1 rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-200 font-mono focus:outline-none" />
							</div>
						</div>
					</div>
				</div>

				<!-- Actions -->
				<div class="border-t border-zinc-700 pt-4 flex justify-between">
					{#if embedConfig?.embed_enabled}
						<Button variant="secondary" size="sm" onclick={handleDisableEmbed} loading={embedSaving}>Disable</Button>
					{:else}
						<Button variant="secondary" size="sm" onclick={handleSaveEmbed} loading={embedSaving}>Enable</Button>
					{/if}
					<div class="flex gap-2">
						<Button variant="secondary" size="sm" onclick={() => (showEmbedModal = false)}>Cancel</Button>
						{#if embedConfig?.embed_enabled}
							<Button size="sm" onclick={handleSaveEmbed} loading={embedSaving}>Save</Button>
						{/if}
					</div>
				</div>
			</div>

			<!-- Right Column: Preview -->
			<div class="flex-1 flex flex-col">
				<h4 class="text-xs font-medium text-zinc-400 mb-3 uppercase tracking-wide">Preview</h4>
				<div
					class="rounded-lg border overflow-hidden flex-1 flex flex-col"
					style="
						background: {embedForm.bg_color || (embedForm.theme === 'dark' ? '#09090b' : '#ffffff')};
						color: {embedForm.text_color || (embedForm.theme === 'dark' ? '#e4e4e7' : '#1f2937')};
						font-family: {embedForm.font_family || 'system-ui, sans-serif'};
					"
				>
					<!-- Header -->
					<div
						class="flex items-center justify-between px-3 py-2 shrink-0"
						style="border-bottom: 1px solid {embedForm.theme === 'dark' ? '#27272a' : '#e5e7eb'}"
					>
						<span class="text-sm font-medium">{embedForm.header_title || 'Chat'}</span>
						<span class="text-xs px-2 py-0.5 rounded-full" style="background: rgba(34, 197, 94, 0.2); color: #22c55e">connected</span>
					</div>
					<!-- Messages -->
					<div class="p-3 space-y-2 flex-1 overflow-y-auto">
						<!-- User message -->
						<div class="flex justify-end">
							<div
								class="px-3 py-1.5 max-w-[80%] text-sm text-white"
								style="
									background: {embedForm.bubble_style === 'minimal' ? 'transparent' : embedForm.primary_color};
									border-radius: {embedForm.bubble_style === 'square' ? '0.25rem' : embedForm.bubble_style === 'minimal' ? '0' : '1rem'};
									{embedForm.bubble_style === 'minimal' ? 'color: ' + embedForm.primary_color + '; font-weight: 500;' : ''}
								"
							>
								Hello! How can I help?
							</div>
						</div>
						<!-- Assistant message -->
						<div class="flex justify-start">
							<div
								class="px-3 py-1.5 max-w-[80%] text-sm"
								style="
									background: {embedForm.bubble_style === 'minimal' ? 'transparent' : (embedForm.theme === 'dark' ? '#27272a' : '#f3f4f6')};
									color: {embedForm.text_color || (embedForm.theme === 'dark' ? '#e4e4e7' : '#1f2937')};
									border-radius: {embedForm.bubble_style === 'square' ? '0.25rem' : embedForm.bubble_style === 'minimal' ? '0' : '1rem'};
								"
							>
								Hi! I'm here to assist you with any questions.
							</div>
						</div>
					</div>
					<!-- Input -->
					<div
						class="p-2 shrink-0"
						style="border-top: 1px solid {embedForm.theme === 'dark' ? '#27272a' : '#e5e7eb'}"
					>
						<div class="flex gap-2">
							<input
								type="text"
								placeholder="Type a message..."
								disabled
								class="flex-1 px-3 py-1.5 rounded text-sm"
								style="
									background: {embedForm.theme === 'dark' ? '#18181b' : '#f9fafb'};
									border: 1px solid {embedForm.theme === 'dark' ? '#3f3f46' : '#e5e7eb'};
									color: {embedForm.text_color || (embedForm.theme === 'dark' ? '#f4f4f5' : '#1f2937')};
								"
							/>
							<button
								class="px-3 py-1.5 rounded text-sm text-white"
								style="background: {embedForm.primary_color}"
							>
								Send
							</button>
						</div>
					</div>
				</div>
			</div>
		</div>
	{/if}
</Modal>
