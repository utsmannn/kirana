<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { base } from '$app/paths';
	import {
		getSession,
		getSessionMessages,
		deleteSession,
		ApiError,
		type Session,
		type SessionMessage,
		type SessionMessagesResponse
	} from '$lib/api';
	import { adminToken } from '$lib/stores.svelte';
	import { showToast } from '$lib/toast.svelte';
	import { goto } from '$app/navigation';
	import Button from '$lib/components/Button.svelte';
	import Modal from '$lib/components/Modal.svelte';

	let session = $state<Session | null>(null);
	let messages = $state<SessionMessage[]>([]);
	let loading = $state(true);
	let showDeleteModal = $state(false);
	let deleting = $state(false);

	const sessionId = $derived(page.params.id);

	onMount(async () => {
		if (!adminToken.value || !sessionId) return;

		loading = true;
		try {
			const [sess, msgsResp] = await Promise.all([
				getSession(sessionId),
				getSessionMessages(sessionId)
			]);
			session = sess;
			messages = msgsResp.messages || [];
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			loading = false;
		}
	});

	async function handleDelete() {
		if (!sessionId) return;

		deleting = true;
		try {
			await deleteSession(sessionId);
			showToast('Session deleted', 'success');
			goto(`${base}/sessions`);
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			deleting = false;
		}
	}

	function formatTime(dateStr: string): string {
		return new Date(dateStr).toLocaleTimeString([], {
			hour: '2-digit',
			minute: '2-digit'
		});
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

<div class="mx-auto max-w-4xl p-6">
	<!-- Back link -->
	<a
		href="{base}/sessions"
		class="mb-4 inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M15 19l-7-7 7-7"
			/>
		</svg>
		Back to Sessions
	</a>

	{#if loading}
		<div class="space-y-4">
			<div class="animate-pulse">
				<div class="h-6 w-48 rounded bg-zinc-800"></div>
				<div class="mt-2 h-4 w-32 rounded bg-zinc-800"></div>
			</div>
			<div class="mt-6 space-y-4">
				{#each [1, 2, 3] as _}
					<div class="animate-pulse rounded-xl bg-zinc-800 p-4">
						<div class="h-4 w-2/3 rounded bg-zinc-700"></div>
					</div>
				{/each}
			</div>
		</div>
	{:else if session}
		<!-- Header -->
		<div class="mb-6 flex items-start justify-between">
			<div>
				<h1 class="text-2xl font-bold text-zinc-100">{session.name}</h1>
				<p class="mt-1 text-sm text-zinc-400">
					{messages.length} messages -- Created {new Date(session.created_at).toLocaleDateString()}
				</p>
			</div>
			<Button variant="danger" size="sm" onclick={() => (showDeleteModal = true)}>
				Delete
			</Button>
		</div>

		<!-- Messages -->
		{#if messages.length === 0}
			<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-12 text-center">
				<p class="text-sm text-zinc-400">No messages in this session</p>
			</div>
		{:else}
			<div class="space-y-4">
				{#each messages as message}
					<div class="flex gap-3 {message.role === 'user' ? 'justify-end' : ''}">
						{#if message.role !== 'user'}
							<div
								class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg
									{message.role === 'assistant'
									? 'bg-indigo-600 text-white'
									: 'bg-zinc-700 text-zinc-400'}
									text-xs font-bold"
							>
								{message.role === 'assistant' ? 'AI' : 'S'}
							</div>
						{/if}
						<div
							class="max-w-[80%] rounded-2xl px-4 py-3
								{message.role === 'user'
								? 'bg-indigo-600 text-white'
								: message.role === 'assistant'
									? 'bg-zinc-800 text-zinc-200'
									: 'bg-zinc-800/50 text-zinc-400 italic'}"
						>
							{#if message.role === 'assistant'}
								<div class="prose prose-invert prose-sm max-w-none markdown-content text-sm leading-relaxed text-zinc-200">
									<!-- svelte-ignore svelte_dom_stringify -->
									{@html (window as any).marked ? (window as any).marked.parse(message.content) : message.content}
								</div>
							{:else}
								<p class="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
							{/if}
							<p class="mt-1 text-[10px] opacity-50">
								{formatTime(message.created_at)}
							</p>
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
	{:else}
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-12 text-center">
			<p class="text-sm text-zinc-400">Session not found</p>
		</div>
	{/if}
</div>

<!-- Delete Confirmation -->
<Modal open={showDeleteModal} title="Delete Session" onClose={() => (showDeleteModal = false)}>
	<p class="text-sm text-zinc-300">
		Are you sure you want to delete this session? All messages will be permanently lost.
	</p>
	<div class="mt-6 flex justify-end gap-3">
		<Button variant="secondary" onclick={() => (showDeleteModal = false)}>Cancel</Button>
		<Button variant="danger" loading={deleting} onclick={handleDelete}>
			{deleting ? 'Deleting...' : 'Delete'}
		</Button>
	</div>
</Modal>
