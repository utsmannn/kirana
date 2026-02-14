<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getKnowledge,
		createKnowledge,
		updateKnowledge,
		deleteKnowledge,
		ApiError,
		type KnowledgeItem,
		type PaginatedResponse
	} from '$lib/api';
	import { apiKey } from '$lib/stores.svelte';
	import { showToast } from '$lib/toast.svelte';
	import Button from '$lib/components/Button.svelte';
	import Modal from '$lib/components/Modal.svelte';

	let items = $state<KnowledgeItem[]>([]);
	let loading = $state(true);
	let search = $state('');
	let currentPage = $state(1);
	let totalPages = $state(1);
	let total = $state(0);

	// Modal state
	let modalOpen = $state(false);
	let editing = $state<KnowledgeItem | null>(null);
	let formTitle = $state('');
	let formContent = $state('');
	let formContentType = $state('text');
	let saving = $state(false);

	// Delete confirm
	let deleteTarget = $state<KnowledgeItem | null>(null);
	let deleting = $state(false);

	let searchTimeout: ReturnType<typeof setTimeout>;

	const modalTitle = $derived(editing ? 'Edit Knowledge Entry' : 'New Knowledge Entry');

	onMount(() => {
		loadItems();
	});

	async function loadItems() {
		if (!apiKey.value) {
			loading = false;
			return;
		}
		loading = true;
		try {
			const result: PaginatedResponse<KnowledgeItem> = await getKnowledge(
				apiKey.value,
				currentPage,
				20,
				search
			);
			items = result.items;
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

	function handleSearch() {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			currentPage = 1;
			loadItems();
		}, 300);
	}

	function goToPage(page: number) {
		currentPage = page;
		loadItems();
	}

	function openCreate() {
		editing = null;
		formTitle = '';
		formContent = '';
		formContentType = 'text';
		modalOpen = true;
	}

	function openEdit(item: KnowledgeItem) {
		editing = item;
		formTitle = item.title;
		formContent = item.content;
		formContentType = item.content_type;
		modalOpen = true;
	}

	async function handleSave(e: Event) {
		e.preventDefault();
		if (!apiKey.value || !formTitle.trim() || !formContent.trim()) return;

		saving = true;
		try {
			if (editing) {
				await updateKnowledge(apiKey.value, editing.id, {
					title: formTitle.trim(),
					content: formContent.trim()
				});
				showToast('Entry updated', 'success');
			} else {
				await createKnowledge(apiKey.value, {
					title: formTitle.trim(),
					content: formContent.trim(),
					content_type: formContentType
				});
				showToast('Entry created', 'success');
			}
			modalOpen = false;
			await loadItems();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			saving = false;
		}
	}

	function confirmDelete(item: KnowledgeItem) {
		deleteTarget = item;
	}

	async function handleDelete() {
		if (!apiKey.value || !deleteTarget) return;

		deleting = true;
		try {
			await deleteKnowledge(apiKey.value, deleteTarget.id);
			showToast('Entry deleted', 'success');
			deleteTarget = null;
			await loadItems();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			}
		} finally {
			deleting = false;
		}
	}
</script>

<div class="mx-auto max-w-5xl p-6">
	<!-- Header -->
	<div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold text-zinc-100">Knowledge Base</h1>
			<p class="mt-1 text-sm text-zinc-400">
				{total} {total === 1 ? 'entry' : 'entries'}
			</p>
		</div>
		<Button onclick={openCreate}>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M12 4v16m8-8H4"
				/>
			</svg>
			Add Entry
		</Button>
	</div>

	<!-- Search -->
	<div class="mb-6">
		<input
			type="text"
			bind:value={search}
			oninput={handleSearch}
			placeholder="Search knowledge base..."
			class="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
		/>
	</div>

	<!-- List -->
	{#if loading}
		<div class="space-y-3">
			{#each [1, 2, 3] as _}
				<div class="animate-pulse rounded-xl border border-zinc-800 bg-zinc-900 p-5">
					<div class="h-4 w-48 rounded bg-zinc-800"></div>
					<div class="mt-3 h-3 w-full rounded bg-zinc-800"></div>
					<div class="mt-2 h-3 w-2/3 rounded bg-zinc-800"></div>
				</div>
			{/each}
		</div>
	{:else if items.length === 0}
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
					d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
				/>
			</svg>
			<p class="mt-3 text-sm text-zinc-400">
				{search ? 'No entries match your search' : 'No knowledge entries yet'}
			</p>
			{#if !search}
				<Button variant="secondary" size="sm" onclick={openCreate} class="mt-4">
					Add your first entry
				</Button>
			{/if}
		</div>
	{:else}
		<div class="space-y-3">
			{#each items as item}
				<div
					class="group rounded-xl border border-zinc-800 bg-zinc-900 p-5 transition-colors hover:border-zinc-700"
				>
					<div class="flex items-start justify-between gap-4">
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2">
								<h3 class="truncate text-sm font-semibold text-zinc-200">{item.title}</h3>
								<span
									class="shrink-0 rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-medium text-zinc-400"
								>
									{item.content_type}
								</span>
							</div>
							<p class="mt-2 line-clamp-2 text-sm text-zinc-400">
								{item.content}
							</p>
							<p class="mt-2 text-xs text-zinc-600">
								Updated {new Date(item.updated_at).toLocaleDateString()}
							</p>
						</div>
						<div
							class="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100"
						>
							<button
								onclick={() => openEdit(item)}
								class="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
								aria-label="Edit"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
									/>
								</svg>
							</button>
							<button
								onclick={() => confirmDelete(item)}
								class="rounded-md p-1.5 text-zinc-400 hover:bg-red-950 hover:text-red-400"
								aria-label="Delete"
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
					</div>
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

<!-- Create/Edit Modal -->
<Modal open={modalOpen} title={modalTitle} onClose={() => (modalOpen = false)}>
	<form onsubmit={handleSave} class="space-y-4">
		<div>
			<label for="entry-title" class="block text-sm font-medium text-zinc-300">Title</label>
			<input
				id="entry-title"
				type="text"
				bind:value={formTitle}
				placeholder="Entry title"
				class="mt-1.5 block w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
			/>
		</div>

		{#if !editing}
			<div>
				<label for="content-type" class="block text-sm font-medium text-zinc-300">Content Type</label>
				<select
					id="content-type"
					bind:value={formContentType}
					class="mt-1.5 block w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3.5 py-2.5 text-sm text-zinc-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
				>
					<option value="text">Text</option>
					<option value="markdown">Markdown</option>
					<option value="faq">FAQ</option>
					<option value="document">Document</option>
				</select>
			</div>
		{/if}

		<div>
			<label for="entry-content" class="block text-sm font-medium text-zinc-300">Content</label>
			<textarea
				id="entry-content"
				bind:value={formContent}
				placeholder="Enter knowledge content..."
				rows="8"
				class="mt-1.5 block w-full resize-y rounded-lg border border-zinc-600 bg-zinc-700 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
			></textarea>
		</div>

		<div class="flex justify-end gap-3 pt-2">
			<Button variant="secondary" onclick={() => (modalOpen = false)}>Cancel</Button>
			<Button type="submit" loading={saving}>
				{saving ? 'Saving...' : editing ? 'Update' : 'Create'}
			</Button>
		</div>
	</form>
</Modal>

<!-- Delete Confirmation -->
<Modal open={!!deleteTarget} title="Delete Entry" onClose={() => (deleteTarget = null)}>
	<p class="text-sm text-zinc-300">
		Are you sure you want to delete
		<span class="font-semibold text-zinc-100">"{deleteTarget?.title}"</span>?
		This action cannot be undone.
	</p>
	<div class="mt-6 flex justify-end gap-3">
		<Button variant="secondary" onclick={() => (deleteTarget = null)}>Cancel</Button>
		<Button variant="danger" loading={deleting} onclick={handleDelete}>
			{deleting ? 'Deleting...' : 'Delete'}
		</Button>
	</div>
</Modal>
