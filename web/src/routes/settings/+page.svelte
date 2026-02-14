<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getProviders,
		getChannels,
		getTools,
		createProvider,
		updateProvider,
		deleteProvider,
		activateProvider,
		createChannel,
		updateChannel,
		deleteChannel,
		setDefaultChannel,
		ApiError,
		type Provider,
		type Channel,
		type Tool,
		type ProviderCreate,
		type ChannelCreate,
		type ToolsResponse
	} from '$lib/api';
	import { apiKey } from '$lib/stores.svelte';
	import { showToast } from '$lib/toast.svelte';
	import Button from '$lib/components/Button.svelte';
	import Modal from '$lib/components/Modal.svelte';

	// Data
	let providers = $state<Provider[]>([]);
	let activeProvider = $state<Provider | null>(null);
	let channels = $state<Channel[]>([]);
	let defaultChannel = $state<Channel | null>(null);
	let tools = $state<Tool[]>([]);
	let loading = $state(true);

	// Modal states
	let showProviderModal = $state(false);
	let showChannelModal = $state(false);
	let editingProvider = $state<Provider | null>(null);
	let editingChannel = $state<Channel | null>(null);
	let saving = $state(false);

	// Provider form
	let providerForm = $state({
		name: '',
		model: '',
		api_key: '',
		base_url: ''
	});

	// Channel form
	let channelForm = $state({
		name: '',
		provider_id: '',
		system_prompt: '',
		personality_name: ''
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
			activeProvider = providersResult.active_provider;
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

	// Provider functions
	function openProviderModal(provider?: Provider) {
		editingProvider = provider || null;
		providerForm = {
			name: provider?.name || '',
			model: provider?.model || '',
			api_key: '',
			base_url: provider?.base_url || ''
		};
		showProviderModal = true;
	}

	async function handleSaveProvider() {
		if (!apiKey.value) return;
		if (!providerForm.name || !providerForm.model || !providerForm.api_key) {
			showToast('Name, model, and API key are required', 'error');
			return;
		}

		saving = true;
		try {
			const data: ProviderCreate = {
				name: providerForm.name,
				model: providerForm.model,
				api_key: providerForm.api_key,
				base_url: providerForm.base_url || undefined
			};

			if (editingProvider) {
				await updateProvider(apiKey.value, editingProvider.id, data);
				showToast('Provider updated', 'success');
			} else {
				await createProvider(apiKey.value, data);
				showToast('Provider created', 'success');
			}
			showProviderModal = false;
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			} else {
				showToast('Failed to save provider', 'error');
			}
		} finally {
			saving = false;
		}
	}

	async function handleDeleteProvider(provider: Provider) {
		if (!apiKey.value) return;
		if (provider.is_default) {
			showToast('Cannot delete default provider', 'error');
			return;
		}
		if (!confirm(`Delete provider "${provider.name}"?`)) return;

		try {
			await deleteProvider(apiKey.value, provider.id);
			showToast('Provider deleted', 'success');
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		}
	}

	async function handleActivateProvider(provider: Provider) {
		if (!apiKey.value) return;
		try {
			await activateProvider(apiKey.value, provider.id);
			showToast(`"${provider.name}" is now active`, 'success');
			await loadData();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		}
	}

	// Channel functions
	function openChannelModal(channel?: Channel) {
		editingChannel = channel || null;
		channelForm = {
			name: channel?.name || '',
			provider_id: channel?.provider_id || activeProvider?.id || '',
			system_prompt: channel?.system_prompt || '',
			personality_name: channel?.personality_name || ''
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
				personality_name: channelForm.personality_name || undefined
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
</script>

<div class="mx-auto max-w-4xl p-6">
	<div class="mb-8">
		<h1 class="text-2xl font-bold text-zinc-100">Settings</h1>
		<p class="mt-1 text-sm text-zinc-400">Manage AI providers, channels, and configurations</p>
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
			<!-- AI Providers -->
			<section class="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
				<div class="mb-4 flex items-center justify-between">
					<div>
						<h2 class="text-base font-semibold text-zinc-200">AI Providers</h2>
						<p class="text-xs text-zinc-500">Connection settings for AI models</p>
					</div>
					<Button onclick={() => openProviderModal()} size="sm">Add Provider</Button>
				</div>

				{#if providers.length === 0}
					<p class="py-8 text-center text-sm text-zinc-500">No providers configured</p>
				{:else}
					<div class="space-y-3">
						{#each providers as provider (provider.id)}
							<div
								class="flex items-center justify-between rounded-lg border p-4 transition-colors
								{provider.is_active
									? 'border-indigo-500/50 bg-indigo-500/10'
									: 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'}"
							>
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										<p class="font-medium text-zinc-200">{provider.name}</p>
										{#if provider.is_default}
											<span class="rounded bg-zinc-700 px-1.5 py-0.5 text-xs text-zinc-400">Default</span>
										{/if}
										{#if provider.is_active}
											<span class="rounded bg-indigo-600 px-1.5 py-0.5 text-xs text-white">Active</span>
										{/if}
									</div>
									<p class="mt-1 truncate text-sm text-zinc-500">
										{provider.model}
										{#if provider.base_url}
											· {provider.base_url}
										{/if}
									</p>
								</div>
								<div class="ml-4 flex items-center gap-2">
									{#if !provider.is_active}
										<button
											onclick={() => handleActivateProvider(provider)}
											class="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500"
										>
											Set Active
										</button>
									{/if}
									<button
										onclick={() => openProviderModal(provider)}
										class="rounded-lg bg-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-600"
									>
										Edit
									</button>
									{#if !provider.is_default}
										<button
											onclick={() => handleDeleteProvider(provider)}
											class="rounded-lg bg-zinc-800 px-3 py-1.5 text-sm text-red-400 hover:bg-zinc-700"
										>
											Delete
										</button>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</section>

			<!-- Channels -->
			<section class="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
				<div class="mb-4 flex items-center justify-between">
					<div>
						<h2 class="text-base font-semibold text-zinc-200">Channels</h2>
						<p class="text-xs text-zinc-500">Personality and behavior configurations</p>
					</div>
					<Button onclick={() => openChannelModal()} size="sm">Add Channel</Button>
				</div>

				{#if channels.length === 0}
					<p class="py-8 text-center text-sm text-zinc-500">No channels configured</p>
				{:else}
					<div class="space-y-3">
						{#each channels as channel (channel.id)}
							<div
								class="flex items-center justify-between rounded-lg border p-4 transition-colors
								{channel.is_default
									? 'border-emerald-500/50 bg-emerald-500/10'
									: 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'}"
							>
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										<p class="font-medium text-zinc-200">{channel.name}</p>
										{#if channel.is_default}
											<span class="rounded bg-emerald-600 px-1.5 py-0.5 text-xs text-white">Default</span>
										{/if}
									</div>
									<p class="mt-1 text-sm text-zinc-500">
										Provider: {channel.provider_name}
										{#if channel.personality_name}
											· Personality: {channel.personality_name}
										{/if}
									</p>
									{#if channel.system_prompt}
										<p class="mt-1 truncate text-xs text-zinc-600">
											{channel.system_prompt.slice(0, 80)}{channel.system_prompt.length > 80 ? '...' : ''}
										</p>
									{/if}
								</div>
								<div class="ml-4 flex items-center gap-2">
									{#if !channel.is_default}
										<button
											onclick={() => handleSetDefaultChannel(channel)}
											class="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-500"
										>
											Set Default
										</button>
									{/if}
									<button
										onclick={() => openChannelModal(channel)}
										class="rounded-lg bg-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-600"
									>
										Edit
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
						{/each}
					</div>
				{/if}

				<p class="mt-4 text-xs text-zinc-500">
					The default channel determines the personality and behavior for new sessions.
					Each session uses one channel, which combines a provider (AI connection) with
					personality settings.
				</p>
			</section>

			<!-- Available Tools -->
			<section class="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
				<h2 class="mb-4 text-base font-semibold text-zinc-200">Available Tools ({tools.length})</h2>
				{#if tools.length > 0}
					<div class="space-y-2">
						{#each tools as tool}
							{@const fn = tool.function || tool}
							<div class="rounded-lg bg-zinc-800/50 px-4 py-3">
								<p class="font-mono text-sm text-zinc-200">{fn.name}</p>
								<p class="mt-0.5 text-xs text-zinc-500">{fn.description}</p>
							</div>
						{/each}
					</div>
				{:else}
					<p class="text-sm text-zinc-500">No tools available</p>
				{/if}
			</section>
		</div>
	{/if}
</div>

<!-- Provider Modal -->
<Modal
	open={showProviderModal}
	onClose={() => (showProviderModal = false)}
	title={editingProvider ? 'Edit Provider' : 'Add Provider'}
>
	<div class="space-y-4">
		<div>
			<label class="block text-sm font-medium text-zinc-300">Name</label>
			<input
				type="text"
				bind:value={providerForm.name}
				placeholder="e.g. OpenAI Production"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			/>
		</div>

		<div>
			<label class="block text-sm font-medium text-zinc-300">Model</label>
			<input
				type="text"
				bind:value={providerForm.model}
				placeholder="e.g. gpt-4, glm-4, claude-3-opus"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			/>
		</div>

		<div>
			<label class="block text-sm font-medium text-zinc-300">
				API Key {editingProvider ? '(leave blank to keep current)' : ''}
			</label>
			<input
				type="password"
				bind:value={providerForm.api_key}
				placeholder="sk-..."
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			/>
		</div>

		<div>
			<label class="block text-sm font-medium text-zinc-300">Base URL (optional)</label>
			<input
				type="url"
				bind:value={providerForm.base_url}
				placeholder="https://api.openai.com/v1"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			/>
		</div>

		<div class="flex justify-end gap-3 pt-4">
			<Button variant="secondary" onclick={() => (showProviderModal = false)}>Cancel</Button>
			<Button onclick={handleSaveProvider} loading={saving}>
				{editingProvider ? 'Update' : 'Create'}
			</Button>
		</div>
	</div>
</Modal>

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

		<div>
			<label class="block text-sm font-medium text-zinc-300">System Prompt</label>
			<textarea
				bind:value={channelForm.system_prompt}
				placeholder="You are a helpful assistant..."
				rows="5"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			></textarea>
			<p class="mt-1 text-xs text-zinc-500">
				Defines how the AI behaves in this channel. Leave empty to use default behavior.
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
