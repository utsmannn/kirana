<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import {
		getSessions,
		createSession,
		deleteSession,
		getChannels,
		ApiError,
		type Session,
		type PaginatedResponse,
		type Channel
	} from '$lib/api';
	import { adminToken } from '$lib/stores.svelte';
	import { showToast } from '$lib/toast.svelte';
	import Button from '$lib/components/Button.svelte';
	import Modal from '$lib/components/Modal.svelte';

	let sessions = $state<Session[]>([]);
	let loading = $state(true);
	let currentPage = $state(1);
	let totalPages = $state(1);
	let total = $state(0);

	// Create
	let showCreateModal = $state(false);
	let newSessionName = $state('');
	let selectedChannelId = $state('');
	let creating = $state(false);

	// Channels
	let channels = $state<Channel[]>([]);
	let defaultChannel = $state<Channel | null>(null);

	// Delete
	let deleteTarget = $state<Session | null>(null);
	let deleting = $state(false);

	onMount(() => {
		loadSessions();
		loadChannels();
	});

	async function loadSessions() {
		if (!adminToken.value) {
			loading = false;
			return;
		}
		loading = true;
		try {
			const result: PaginatedResponse<Session> = await getSessions(
				undefined,
				currentPage,
				20
			);
			sessions = result.items;
			totalPages = result.pages;
			total = result.total;
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			loading = false;
		}
	}

	async function loadChannels() {
		try {
			const result = await getChannels();
			channels = result.channels || [];
			defaultChannel = result.default_channel;
			// Pre-select default channel
			if (defaultChannel) {
				selectedChannelId = defaultChannel.id;
			} else if (channels.length > 0) {
				selectedChannelId = channels[0].id;
			}
		} catch {
			// ignore - channels might fail but sessions should still work
		}
	}

	async function handleCreateSession() {
		if (!newSessionName.trim()) return;

		creating = true;
		try {
			const sessionData = {
				name: newSessionName.trim(),
				channel_id: selectedChannelId || undefined
			};
			const session = await createSession(sessionData);
			showToast('Session created', 'success');
			showCreateModal = false;
			newSessionName = '';
			// Navigate to the new session
			window.location.href = `${base}/sessions/${session.id}`;
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			} else {
				showToast('Failed to create session', 'error');
			}
		} finally {
			creating = false;
		}
	}

	function goToPage(page: number) {
		currentPage = page;
		loadSessions();
	}

	function confirmDelete(session: Session) {
		deleteTarget = session;
	}

	async function handleDelete() {
		if (!deleteTarget) return;

		deleting = true;
		try {
			await deleteSession(deleteTarget.id);
			showToast('Session deleted', 'success');
			deleteTarget = null;
			await loadSessions();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			deleting = false;
		}
	}

	function formatDate(dateStr: string): string {
		const d = new Date(dateStr);
		return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}
</script>

<div class="mx-auto max-w-5xl p-6">
	<!-- Header -->
	<div class="mb-6 flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold text-zinc-100">Sessions</h1>
			<p class="mt-1 text-sm text-zinc-400">
				{total} {total === 1 ? 'session' : 'sessions'}
			</p>
		</div>
		<Button onclick={() => (showCreateModal = true)} size="sm">New Session</Button>
	</div>

	<!-- List -->
	{#if loading}
		<div class="space-y-3">
			{#each [1, 2, 3, 4] as _}
				<div class="animate-pulse rounded-xl border border-zinc-800 bg-zinc-900 p-5">
					<div class="h-4 w-40 rounded bg-zinc-800"></div>
					<div class="mt-3 h-3 w-24 rounded bg-zinc-800"></div>
				</div>
			{/each}
		</div>
	{:else if sessions.length === 0}
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-12 text-center">
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
			<p class="mt-3 text-sm text-zinc-400">No sessions yet</p>
			<p class="mt-1 text-xs text-zinc-500">Sessions are created when you start chatting</p>
		</div>
	{:else}
		<div class="space-y-2">
			{#each sessions as session}
				<div
					class="group flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-zinc-700"
				>
					<a
						href="{base}/sessions/{session.id}"
						class="flex min-w-0 flex-1 items-center gap-4"
					>
						<div
							class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-zinc-500"
						>
							<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="1.5"
									d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
								/>
							</svg>
						</div>
						<div class="min-w-0 flex-1">
							<p class="truncate text-sm font-medium text-zinc-200">{session.name}</p>
							<div class="mt-1 flex items-center gap-3 text-xs text-zinc-500">
								{#if session.message_count !== undefined}
									<span>{session.message_count} messages</span>
								{/if}
								<span>{formatDate(session.updated_at)}</span>
							</div>
						</div>
					</a>

					<button
						onclick={() => confirmDelete(session)}
						class="shrink-0 rounded-md p-1.5 text-zinc-500 opacity-0 transition-all hover:bg-red-950 hover:text-red-400 group-hover:opacity-100"
						aria-label="Delete session"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
							/>
						</svg>
					</button>
				</div>
			{/each}
		</div>

		<!-- Pagination -->
		{#if totalPages > 1}
			<div class="mt-6 flex items-center justify-center gap-2">
				<Button
					variant="ghost"
					size="sm"
					disabled={currentPage <= 1}
					onclick={() => goToPage(currentPage - 1)}
				>
					Previous
				</Button>
				<span class="px-3 text-sm text-zinc-400">
					Page {currentPage} of {totalPages}
				</span>
				<Button
					variant="ghost"
					size="sm"
					disabled={currentPage >= totalPages}
					onclick={() => goToPage(currentPage + 1)}
				>
					Next
				</Button>
			</div>
		{/if}
	{/if}
</div>

<!-- Create Session Modal -->
<Modal open={showCreateModal} title="New Session" onClose={() => (showCreateModal = false)}>
	<div class="space-y-4">
		<div>
			<label class="block text-sm font-medium text-zinc-300">Session Name</label>
			<input
				type="text"
				bind:value={newSessionName}
				placeholder="e.g. Project Discussion"
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
				onkeydown={(e) => e.key === 'Enter' && handleCreateSession()}
			/>
		</div>
		<div>
			<label class="block text-sm font-medium text-zinc-300">Channel</label>
			<select
				bind:value={selectedChannelId}
				class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
			>
				{#each channels as channel}
					<option value={channel.id}>
						{channel.name}{channel.is_default ? ' (Default)' : ''}
					</option>
				{/each}
			</select>
			<p class="mt-1 text-xs text-zinc-500">
				Select which AI personality to use for this session
			</p>
		</div>
		<div class="flex justify-end gap-3 pt-2">
			<Button variant="secondary" onclick={() => (showCreateModal = false)}>Cancel</Button>
			<Button loading={creating} onclick={handleCreateSession}>
				{creating ? 'Creating...' : 'Create'}
			</Button>
		</div>
	</div>
</Modal>

<!-- Delete Confirmation -->
<Modal open={!!deleteTarget} title="Delete Session" onClose={() => (deleteTarget = null)}>
	<p class="text-sm text-zinc-300">
		Are you sure you want to delete session
		<span class="font-semibold text-zinc-100">"{deleteTarget?.name}"</span>?
		All messages in this session will be lost.
	</p>
	<div class="mt-6 flex justify-end gap-3">
		<Button variant="secondary" onclick={() => (deleteTarget = null)}>Cancel</Button>
		<Button variant="danger" loading={deleting} onclick={handleDelete}>
			{deleting ? 'Deleting...' : 'Delete'}
		</Button>
	</div>
</Modal>
