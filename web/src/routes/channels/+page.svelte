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
		extractBrandStyle,
		ApiError,
		type Provider,
		type Channel,
		type Tool,
		type ChannelCreate,
		type ToolsResponse,
		type EmbedConfigResponse
	} from '$lib/api';
	import { adminToken } from '$lib/stores.svelte';
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
	let isCustomFont = $state(false);
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
		google_fonts_url: '',
		bubble_style: 'rounded',
		header_title: ''
	});

	// Brand style extraction
	let brandUrl = $state('');
	let brandExtracting = $state(false);
	let extractedGoogleFontsUrl = $state<string | null>(null);

	onMount(async () => {
		if (!adminToken.value) {
			loading = false;
			return;
		}
		await loadData();
	});

	async function loadData() {
		loading = true;
		try {
			const [providersResult, channelsResult, toolsResult] = await Promise.all([
				getProviders(),
				getChannels().catch(() => ({ channels: [], default_channel: null })),
				getTools().catch(() => ({ tools: [] }))
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
				await updateChannel(editingChannel.id, data);
				showToast('Channel updated', 'success');
			} else {
				await createChannel(data);
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
		if (channel.is_default) {
			showToast('Cannot delete default channel', 'error');
			return;
		}
		if (!confirm(`Delete channel "${channel.name}"?`)) return;

		try {
			await deleteChannel(channel.id);
			showToast('Channel deleted', 'success');
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		}
	}

	async function handleSetDefaultChannel(channel: Channel) {
		try {
			await setDefaultChannel(channel.id);
			showToast(`"${channel.name}" is now default channel`, 'success');
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		}
	}

	async function openEmbedModal(channel: Channel) {
		const standardFonts = ['', 'Inter, sans-serif', "'Roboto', sans-serif", "'Open Sans', sans-serif", "'JetBrains Mono', monospace", 'Georgia, serif'];
		embedChannel = channel;
		embedLoading = true;
		showEmbedModal = true;
		extractedGoogleFontsUrl = null; // Reset
		try {
			embedConfig = await getEmbedConfig(channel.id);
			embedForm = {
				public: embedConfig.public,
				save_history: embedConfig.save_history,
				stream_mode: embedConfig.stream_mode,
				regenerate_token: false,
				theme: embedConfig.theme || 'dark',
				primary_color: embedConfig.primary_color || '#4f46e5',
				bg_color: embedConfig.bg_color || '',
				text_color: embedConfig.text_color || '',
				font_family: embedConfig.font_family || '',
				google_fonts_url: embedConfig.google_fonts_url || '',
				bubble_style: embedConfig.bubble_style || 'rounded',
				header_title: embedConfig.header_title || ''
			};
			isCustomFont = !standardFonts.includes(embedForm.font_family);
		} catch (err) {
			// If no embed config exists, use defaults
			embedConfig = null;
			embedForm = {
				public: true,
				save_history: true,
				stream_mode: true,
				regenerate_token: false,
				theme: 'dark',
				primary_color: '#4f46e5',
				bg_color: '',
				text_color: '',
				font_family: '',
				google_fonts_url: '',
				bubble_style: 'rounded',
				header_title: ''
			};
			isCustomFont = false;
		} finally {
			embedLoading = false;
		}
	}

	async function handleSaveEmbed() {
		if (!embedChannel) return;
		embedSaving = true;
		try {
			embedConfig = await configureEmbed(embedChannel.id, embedForm);
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
		if (!embedChannel) return;
		if (!confirm('Disable embed for this channel?')) return;
		embedSaving = true;
		try {
			await disableEmbed(embedChannel.id);
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

	async function handleExtractBrandStyle() {
		if (!brandUrl.trim()) {
			showToast('Please enter a website URL', 'error');
			return;
		}

		brandExtracting = true;
		try {
			const result = await extractBrandStyle(brandUrl.trim());

			if (!result.success) {
				showToast(result.error || 'Failed to extract brand style', 'error');
				return;
			}

			// Apply extracted styles to form
			if (result.primary_color) {
				embedForm.primary_color = result.primary_color;
			}
			if (result.bg_color) {
				embedForm.bg_color = result.bg_color;
			}
			if (result.text_color) {
				embedForm.text_color = result.text_color;
			}
			if (result.font_family) {
				// Use the Google Fonts name if available
				const fontName = result.google_fonts_name || result.font_family;
				embedForm.font_family = fontName + ', sans-serif';
				isCustomFont = true; // Always mark as custom when extracted
			}
			// Store Google Fonts URL in form
			if (result.google_fonts_url) {
				embedForm.google_fonts_url = result.google_fonts_url;
				extractedGoogleFontsUrl = result.google_fonts_url;
			}

			// Determine theme based on background color brightness
			if (result.bg_color) {
				const hex = result.bg_color.replace('#', '');
				const r = parseInt(hex.substr(0, 2), 16);
				const g = parseInt(hex.substr(2, 2), 16);
				const b = parseInt(hex.substr(4, 2), 16);
				const brightness = (r * 299 + g * 587 + b * 114) / 1000;
				embedForm.theme = brightness > 128 ? 'light' : 'dark';
			}

			showToast('Brand style extracted successfully!', 'success');
			brandUrl = '';
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			} else {
				showToast('Failed to extract brand style', 'error');
			}
		} finally {
			brandExtracting = false;
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
	closable={!brandExtracting}
	title="Embed Configuration"
	size="xl"
>
	{#if embedLoading}
		<div class="flex flex-col items-center justify-center py-20">
			<div class="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent"></div>
			<p class="mt-4 text-sm text-zinc-400 font-medium">Loading configuration...</p>
		</div>
	{:else}
		<div class="flex flex-col lg:flex-row gap-8 h-[650px]">
			<!-- Left Column: Settings -->
			<div class="w-full lg:w-80 shrink-0 flex flex-col h-full overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-zinc-700">
				<!-- Status Section -->
				<div class="mb-6">
					{#if embedConfig?.embed_enabled}
						<div class="rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-4">
							<div class="flex items-center gap-2.5 mb-3">
								<div class="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></div>
								<span class="text-sm font-semibold text-emerald-400 uppercase tracking-wider">Active</span>
							</div>
							<div class="space-y-3">
								<div class="relative">
									<input
										type="text"
										readonly
										value={getEmbedUrl()}
										class="w-full rounded-lg bg-zinc-900 px-3 py-2 text-xs text-zinc-400 border border-zinc-700 focus:outline-none pr-12"
									/>
									<button
										onclick={copyEmbedUrl}
										class="absolute right-1 top-1 bottom-1 px-2 rounded-md bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
										title="Copy URL"
									>
										<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"></path>
										</svg>
									</button>
								</div>
								<p class="text-[10px] text-zinc-500 italic">Share this URL to allow users to chat with this channel.</p>
							</div>
						</div>
					{:else}
						<div class="rounded-xl bg-zinc-900 border border-zinc-800 p-4">
							<div class="flex items-center gap-2.5 mb-2">
								<div class="h-2 w-2 rounded-full bg-zinc-600"></div>
								<span class="text-sm font-semibold text-zinc-500 uppercase tracking-wider">Inactive</span>
							</div>
							<p class="text-xs text-zinc-400">Enable embedding to get a public chat URL for this channel.</p>
						</div>
					{/if}
				</div>

				<!-- Settings Sections -->
				<div class="space-y-6 flex-1">
					<!-- General Section -->
					<section>
						<h4 class="text-[11px] font-bold text-zinc-500 mb-4 uppercase tracking-widest border-b border-zinc-800 pb-2">Behavior</h4>
						<div class="space-y-4">
							<label class="group flex items-start justify-between cursor-pointer">
								<div class="flex flex-col">
									<span class="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors">Public Access</span>
									<span class="text-[10px] text-zinc-500">Allow anyone with the link to chat</span>
								</div>
								<input type="checkbox" bind:checked={embedForm.public} class="mt-1 h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600 focus:ring-offset-zinc-800 focus:ring-indigo-600" />
							</label>
							<label class="group flex items-start justify-between cursor-pointer">
								<div class="flex flex-col">
									<span class="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors">Save History</span>
									<span class="text-[10px] text-zinc-500">Persist chat sessions in the database</span>
								</div>
								<input type="checkbox" bind:checked={embedForm.save_history} class="mt-1 h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600 focus:ring-offset-zinc-800 focus:ring-indigo-600" />
							</label>
							<label class="group flex items-start justify-between cursor-pointer">
								<div class="flex flex-col">
									<span class="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors">Stream Mode</span>
									<span class="text-[10px] text-zinc-500">Display AI responses as they are generated</span>
								</div>
								<input type="checkbox" bind:checked={embedForm.stream_mode} class="mt-1 h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600 focus:ring-offset-zinc-800 focus:ring-indigo-600" />
							</label>
							{#if embedConfig?.embed_enabled}
								<label class="group flex items-start justify-between cursor-pointer">
									<div class="flex flex-col">
										<span class="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors">Rotate Token</span>
										<span class="text-[10px] text-zinc-500">Generates a new URL and invalidates the old one</span>
									</div>
									<input type="checkbox" bind:checked={embedForm.regenerate_token} class="mt-1 h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-indigo-600 focus:ring-offset-zinc-800 focus:ring-indigo-600" />
								</label>
							{/if}
						</div>
					</section>

					<!-- Style Section -->
					<section>
						<h4 class="text-[11px] font-bold text-zinc-500 mb-4 uppercase tracking-widest border-b border-zinc-800 pb-2">Customization</h4>
						<div class="space-y-4">
							<!-- Brand Style Extractor -->
							<div class="p-3 rounded-lg bg-gradient-to-r from-indigo-500/10 to-purple-500/10 border border-indigo-500/20">
								<div class="flex items-center gap-2 mb-2">
									<svg class="h-4 w-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"></path>
									</svg>
									<span class="text-xs font-semibold text-indigo-300">Extract Style from Brand</span>
								</div>
								<p class="text-[10px] text-zinc-500 mb-3">Enter a website URL to automatically extract colors and font</p>
								<div class="space-y-2">
									<input
										type="url"
										bind:value={brandUrl}
										placeholder="https://example.com"
										disabled={brandExtracting}
										class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none transition-all disabled:opacity-50"
									/>
									<button
										onclick={handleExtractBrandStyle}
										disabled={brandExtracting || !brandUrl.trim()}
										class="w-full px-3 py-2 rounded-lg bg-indigo-600 text-sm font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
									>
										{#if brandExtracting}
											<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
												<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
												<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
											</svg>
											Extracting...
										{:else}
											<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path>
											</svg>
											Extract Style
										{/if}
									</button>
								</div>
							</div>

							<div>
								<label class="block text-xs font-medium text-zinc-400 mb-1.5">Window Title</label>
								<input type="text" bind:value={embedForm.header_title} placeholder="Chat" maxlength="50"
									class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all" />
							</div>

							<div class="grid grid-cols-2 gap-3">
								<div>
									<label class="block text-xs font-medium text-zinc-400 mb-1.5">Theme</label>
									<div class="relative">
										<select bind:value={embedForm.theme}
											class="w-full appearance-none rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none cursor-pointer">
											<option value="dark">Dark</option>
											<option value="light">Light</option>
										</select>
										<div class="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-500">
											<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
										</div>
									</div>
								</div>
								<div>
									<label class="block text-xs font-medium text-zinc-400 mb-1.5">Bubbles</label>
									<div class="relative">
										<select bind:value={embedForm.bubble_style}
											class="w-full appearance-none rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none cursor-pointer">
											<option value="rounded">Rounded</option>
											<option value="square">Square</option>
											<option value="minimal">Minimal</option>
										</select>
										<div class="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-500">
											<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
										</div>
									</div>
								</div>
							</div>

							<div>
								<label class="block text-xs font-medium text-zinc-400 mb-1.5">Brand Color</label>
								<div class="flex gap-2">
									<div class="relative h-9 w-9 shrink-0 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900">
										<input 
											type="color" 
											value={embedForm.primary_color || '#4f46e5'} 
											oninput={(e) => embedForm.primary_color = e.currentTarget.value}
											class="absolute -inset-2 h-14 w-14 cursor-pointer border-none bg-transparent" 
										/>
									</div>
									<input type="text" bind:value={embedForm.primary_color} placeholder="#4f46e5"
										class="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 font-mono focus:border-indigo-500 outline-none transition-all uppercase" />
								</div>
							</div>

							<div>
								<label class="block text-xs font-medium text-zinc-400 mb-1.5">Background Color</label>
								<div class="flex gap-2">
									<div class="relative h-9 w-9 shrink-0 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900">
										<input 
											type="color" 
											value={embedForm.bg_color || (embedForm.theme === 'dark' ? '#09090b' : '#ffffff')} 
											oninput={(e) => embedForm.bg_color = e.currentTarget.value}
											class="absolute -inset-2 h-14 w-14 cursor-pointer border-none bg-transparent" 
										/>
									</div>
									<input type="text" bind:value={embedForm.bg_color} placeholder="Auto (Theme default)"
										class="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 font-mono focus:border-indigo-500 outline-none transition-all uppercase" />
								</div>
							</div>

							<div>
								<label class="block text-xs font-medium text-zinc-400 mb-1.5">Text Color</label>
								<div class="flex gap-2">
									<div class="relative h-9 w-9 shrink-0 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900">
										<input 
											type="color" 
											value={embedForm.text_color || (embedForm.theme === 'dark' ? '#e4e4e7' : '#1f2937')} 
											oninput={(e) => embedForm.text_color = e.currentTarget.value}
											class="absolute -inset-2 h-14 w-14 cursor-pointer border-none bg-transparent" 
										/>
									</div>
									<input type="text" bind:value={embedForm.text_color} placeholder="Auto (Theme default)"
										class="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 font-mono focus:border-indigo-500 outline-none transition-all uppercase" />
								</div>
							</div>

							<div>
								<label class="block text-xs font-medium text-zinc-400 mb-1.5">Font Family</label>
								<div class="relative">
									<select 
										value={isCustomFont ? 'custom' : embedForm.font_family}
										onchange={(e) => {
											const val = e.currentTarget.value;
											if (val === 'custom') {
												isCustomFont = true;
											} else {
												isCustomFont = false;
												embedForm.font_family = val;
											}
										}}
										class="w-full appearance-none rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none cursor-pointer">
										<option value="">Default (System Sans)</option>
										<option value="Inter, sans-serif">Inter</option>
										<option value="'Roboto', sans-serif">Roboto</option>
										<option value="'Open Sans', sans-serif">Open Sans</option>
										<option value="'JetBrains Mono', monospace">JetBrains Mono</option>
										<option value="Georgia, serif">Georgia</option>
										<option value="custom">Custom Font...</option>
									</select>
									<div class="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-500">
										<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
									</div>
								</div>
								{#if isCustomFont}
									<input type="text" 
										bind:value={embedForm.font_family}
										placeholder="e.g. 'Poppins', sans-serif"
										class="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none transition-all" />
								{/if}
							</div>
						</div>
					</section>
				</div>

				<!-- Modal Actions -->
				<div class="mt-8 pt-6 border-t border-zinc-800 flex flex-col gap-2">
					<div class="flex gap-2">
						<Button class="flex-1" variant="secondary" size="sm" onclick={() => (showEmbedModal = false)} disabled={brandExtracting}>Cancel</Button>
						{#if embedConfig?.embed_enabled}
							<Button class="flex-1" size="sm" onclick={handleSaveEmbed} loading={embedSaving} disabled={brandExtracting}>Update</Button>
						{:else}
							<Button class="flex-1" size="sm" onclick={handleSaveEmbed} loading={embedSaving} disabled={brandExtracting}>Enable</Button>
						{/if}
					</div>
					{#if embedConfig?.embed_enabled}
						<button 
							onclick={handleDisableEmbed}
							disabled={embedSaving}
							class="text-xs text-red-400/70 hover:text-red-400 py-2 transition-colors disabled:opacity-50"
						>
							Disable Embedding
						</button>
					{/if}
				</div>
			</div>

			<!-- Right Column: Preview -->
			<div class="flex-1 bg-zinc-900/50 rounded-2xl border border-zinc-800 p-8 flex flex-col items-center justify-center relative overflow-hidden group">
				<!-- Background pattern -->
				<div class="absolute inset-0 opacity-[0.03] pointer-events-none">
					<div class="absolute inset-0" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
				</div>
				
				<div class="text-center mb-8 relative z-10">
					<h4 class="text-[11px] font-bold text-zinc-500 uppercase tracking-[0.2em] mb-1">Live Preview</h4>
					<p class="text-[10px] text-zinc-600">See how your widget appears to visitors</p>
				</div>

				<!-- Preview Container -->
				<div
					class="w-full max-w-[400px] h-[450px] shadow-2xl rounded-2xl border flex flex-col relative z-10 transition-all duration-300"
					style="
						background: {embedForm.bg_color || (embedForm.theme === 'dark' ? '#09090b' : '#ffffff')};
						color: {embedForm.text_color || (embedForm.theme === 'dark' ? '#e4e4e7' : '#1f2937')};
						font-family: {embedForm.font_family || '-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif'};
						border-color: {embedForm.theme === 'dark' ? '#27272a' : '#e5e7eb'};
					"
				>
					<!-- Header -->
					<div
						class="flex items-center justify-between px-4 py-2 shrink-0"
						style="border-bottom: 1px solid {embedForm.theme === 'dark' ? '#27272a' : '#e5e7eb'}"
					>
						<div class="flex items-center">
							<span class="text-sm font-medium truncate max-w-[150px]">{embedForm.header_title || 'Chat'}</span>
							<span class="ml-2 text-[10px] px-1.5 py-0.5 rounded-full" style="background: rgba(34, 197, 94, 0.12); color: #22c55e">connected</span>
						</div>
						<button class="text-[11px] opacity-50 hover:opacity-100 transition-opacity">Clear</button>
					</div>

					<!-- Messages -->
					<div class="p-4 space-y-4 flex-1 overflow-y-auto">
						<!-- User message -->
						<div class="flex justify-end">
							<div
								class="px-4 py-2 max-w-[85%] text-[13.5px] leading-relaxed text-white shadow-sm"
								style="
									background: {embedForm.bubble_style === 'minimal' ? 'transparent' : (embedForm.primary_color || '#4f46e5')};
									border: {embedForm.bubble_style === 'minimal' ? '1.5px solid ' + (embedForm.primary_color || '#4f46e5') : 'none'};
									border-radius: {embedForm.bubble_style === 'square' ? '0.375rem' : embedForm.bubble_style === 'minimal' ? '0.375rem' : '1.125rem 1.125rem 0.25rem 1.125rem'};
									{embedForm.bubble_style === 'minimal' ? 'color: ' + (embedForm.primary_color || '#4f46e5') + '; font-weight: 600;' : ''}
								"
							>
								I'd like to learn more about the features.
							</div>
						</div>

						<!-- Assistant message -->
						<div class="flex justify-start">
							<div
								class="px-4 py-2 max-w-[85%] text-[13.5px] leading-relaxed shadow-sm"
								style="
									background: {embedForm.bubble_style === 'minimal' ? 'transparent' : (embedForm.theme === 'dark' ? '#27272a' : '#f3f4f6')};
									color: {embedForm.text_color || (embedForm.theme === 'dark' ? '#e4e4e7' : '#1f2937')};
									border: {embedForm.bubble_style === 'minimal' ? '1px solid ' + (embedForm.theme === 'dark' ? '#27272a' : '#e5e7eb') : 'none'};
									border-radius: {embedForm.bubble_style === 'square' ? '0.375rem' : embedForm.bubble_style === 'minimal' ? '0.375rem' : '1.125rem 1.125rem 1.125rem 0.25rem'};
								"
							>
								Hello! How can I help you today?
							</div>
						</div>
						
						<!-- Assistant typing -->
						<div class="flex justify-start">
							<div 
								class="flex items-center gap-1 px-4 py-2.5 shadow-sm"
								style="
									background: {embedForm.bubble_style === 'minimal' ? 'transparent' : (embedForm.theme === 'dark' ? '#27272a' : '#f3f4f6')};
									border: {embedForm.bubble_style === 'minimal' ? '1px solid ' + (embedForm.theme === 'dark' ? '#27272a' : '#e5e7eb') : 'none'};
									border-radius: {embedForm.bubble_style === 'square' ? '0.375rem' : embedForm.bubble_style === 'minimal' ? '0.375rem' : '1.125rem 1.125rem 1.125rem 0.25rem'};
								"
							>
								<div class="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce [animation-duration:1.4s] [animation-delay:-0.32s]"></div>
								<div class="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce [animation-duration:1.4s] [animation-delay:-0.16s]"></div>
								<div class="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce [animation-duration:1.4s]"></div>
							</div>
						</div>
					</div>

					<!-- Input Area -->
					<div
						class="p-4 shrink-0"
						style="border-top: 1px solid {embedForm.theme === 'dark' ? '#27272a' : '#e5e7eb'}"
					>
						<div class="flex gap-2">
							<div
								class="flex-1 px-4 py-2 rounded-full border text-[13px] opacity-50"
								style="
									background: {embedForm.theme === 'dark' ? '#18181b' : '#f9fafb'};
									border-color: {embedForm.theme === 'dark' ? '#3f3f46' : '#e5e7eb'};
								"
							>
								Type a message...
							</div>
							<div
								class="h-9 w-9 rounded-full flex items-center justify-center text-white shrink-0"
								style="background: {embedForm.primary_color || '#4f46e5'}"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 12h14M12 5l7 7-7 7"></path>
								</svg>
							</div>
						</div>
					</div>
				</div>

				<!-- Floating Widget Icon Hint -->
				<div class="absolute bottom-4 right-4 animate-bounce hidden group-hover:block transition-all">
					<div class="h-10 w-10 rounded-full shadow-lg flex items-center justify-center text-white" style="background: {embedForm.primary_color}">
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012-2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
						</svg>
					</div>
				</div>
			</div>
		</div>
	{/if}
</Modal>
