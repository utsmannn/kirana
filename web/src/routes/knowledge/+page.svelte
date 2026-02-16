<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getKnowledge,
		createKnowledge,
		updateKnowledge,
		deleteKnowledge,
		uploadKnowledgeFile,
		scrapeWebUrl,
		crawlWebsite,
		ApiError,
		type KnowledgeItem,
		type PaginatedResponse
	} from '$lib/api';
	import { adminToken } from '$lib/stores.svelte';
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

	// File upload state
	let uploadMode = $state<'text' | 'file' | 'web'>('text');
	let selectedFile = $state<File | null>(null);
	let uploading = $state(false);
	let uploadProgress = $state(0);
	let uploadStage = $state<'idle' | 'uploading' | 'analyzing'>('idle');
	let uploadTimer: ReturnType<typeof setTimeout> | null = null;

	// Web scraping state
	let webUrl = $state('');
	let crawlMode = $state<'single' | 'crawl'>('single');
	let crawlMaxPages = $state(50);
	let crawlMaxDepth = $state(3);
	let crawlPathPrefix = $state('');
	let scraping = $state(false);

	// Image types that require AI analysis
	const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'];
	// Types that require Vision AI analysis (longer processing time)
	const VISION_TYPES = [...IMAGE_TYPES, 'application/pdf'];

	// Delete confirm
	let deleteTarget = $state<KnowledgeItem | null>(null);
	let deleting = $state(false);

	let searchTimeout: ReturnType<typeof setTimeout>;

	// Helper to build file URL with auth
	function getFileUrl(itemId: string): string {
		return `/v1/knowledge/${itemId}/download?api_key=${encodeURIComponent(adminToken.value ?? '')}`;
	}

	const modalTitle = $derived(editing ? 'Edit Knowledge Entry' : 'New Knowledge Entry');

	onMount(() => {
		loadItems();
	});

	async function loadItems() {
		if (!adminToken.value) {
			loading = false;
			return;
		}
		loading = true;
		try {
			const result: PaginatedResponse<KnowledgeItem> = await getKnowledge(
				undefined,
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
		uploadMode = 'text';
		selectedFile = null;
		uploadProgress = 0;
		uploadStage = 'idle';
		webUrl = '';
		crawlMode = 'single';
		crawlMaxPages = 50;
		crawlMaxDepth = 3;
		crawlPathPrefix = '';
		if (uploadTimer) {
			clearTimeout(uploadTimer);
			uploadTimer = null;
		}
		modalOpen = true;
	}

	function handleFileSelect(e: Event) {
		const input = e.target as HTMLInputElement;
		if (input.files && input.files.length > 0) {
			selectedFile = input.files[0];
			// Auto-fill title from filename if empty
			if (!formTitle) {
				formTitle = selectedFile.name.replace(/\.[^/.]+$/, '');
			}
		}
	}

	async function handleUpload(e: Event) {
		e.preventDefault();
		if (!selectedFile) return;

		uploading = true;
		uploadProgress = 0;
		uploadStage = 'uploading';

		// Check if file requires Vision AI analysis (images + PDFs)
		const needsVision = VISION_TYPES.includes(selectedFile.type);

		// Start timer to switch to "analyzing" state after 1.5 seconds
		if (needsVision) {
			uploadTimer = setTimeout(() => {
				if (uploading) {
					uploadStage = 'analyzing';
				}
			}, 1500);
		}

		try {
			await uploadKnowledgeFile(selectedFile, formTitle.trim() || undefined);
			showToast('File uploaded successfully', 'success');
			modalOpen = false;
			selectedFile = null;
			formTitle = '';
			await loadItems();
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			} else {
				showToast('Failed to upload file', 'error');
			}
		} finally {
			if (uploadTimer) {
				clearTimeout(uploadTimer);
				uploadTimer = null;
			}
			uploading = false;
			uploadProgress = 0;
			uploadStage = 'idle';
		}
	}

	async function handleWebScrape(e: Event) {
		e.preventDefault();
		if (!webUrl.trim()) return;

		// Normalize URL - add https:// if missing
		let url = webUrl.trim();
		if (!url.startsWith('http://') && !url.startsWith('https://')) {
			url = 'https://' + url;
		}

		// Basic URL validation
		try {
			new URL(url);
		} catch {
			showToast('Please enter a valid URL', 'error');
			return;
		}

		scraping = true;

		try {
			if (crawlMode === 'single') {
				const result = await scrapeWebUrl(url, undefined);
				if (result.success) {
					showToast(`Scraped: ${result.title}`, 'success');
					modalOpen = false;
					webUrl = '';
					await loadItems();
				} else {
					showToast(result.error || 'Failed to scrape URL', 'error');
				}
			} else {
				const result = await crawlWebsite(url, undefined, {
					max_pages: crawlMaxPages,
					max_depth: crawlMaxDepth,
					path_prefix: crawlPathPrefix.trim() || undefined
				});
				if (result.success) {
					showToast(`Crawled ${result.successful_pages} pages from website`, 'success');
					modalOpen = false;
					webUrl = '';
					await loadItems();
				} else {
					showToast(result.errors[0] || 'Failed to crawl website', 'error');
				}
			}
		} catch (err) {
			if (err instanceof ApiError) {
				showToast(err.message, 'error');
			} else {
				showToast('Failed to scrape website', 'error');
			}
		} finally {
			scraping = false;
		}
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

		// If in file upload mode, use handleUpload instead
		if (uploadMode === 'file' && !editing) {
			await handleUpload(e);
			return;
		}

		// If in web scraping mode, use handleWebScrape instead
		if (uploadMode === 'web' && !editing) {
			await handleWebScrape(e);
			return;
		}

		if (!formTitle.trim() || !formContent.trim()) return;

		saving = true;
		try {
			if (editing) {
				await updateKnowledge(editing.id, {
					title: formTitle.trim(),
					content: formContent.trim()
				});
				showToast('Entry updated', 'success');
			} else {
				await createKnowledge({
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
		if (!deleteTarget) return;

		deleting = true;
		try {
			await deleteKnowledge(deleteTarget.id);
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
				{@const isImage = item.mime_type?.startsWith('image/')}
				{@const isPdf = item.mime_type === 'application/pdf'}
				<div
					class="group rounded-xl border border-zinc-800 bg-zinc-900 p-5 transition-colors hover:border-zinc-700"
				>
					<div class="flex items-start gap-4">
						<!-- File Preview (images only) -->
						{#if item.has_file && isImage}
							<div class="shrink-0">
								<a
									href={getFileUrl(item.id)}
									target="_blank"
									class="block"
								>
									<img
										src={getFileUrl(item.id)}
										alt={item.title}
										class="h-20 w-20 rounded-lg object-cover border border-zinc-700 hover:border-indigo-500 transition-colors"
									/>
								</a>
							</div>
						{/if}

						<!-- Content -->
						<div class="min-w-0 flex-1">
							<div class="flex items-start justify-between gap-4">
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										<h3 class="truncate text-sm font-semibold text-zinc-200">{item.title}</h3>
										<span
											class="shrink-0 rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-medium text-zinc-400"
										>
											{item.content_type}
										</span>
										{#if item.has_file}
											<span
												class="shrink-0 rounded bg-indigo-900/50 px-2 py-0.5 text-[10px] font-medium text-indigo-300"
												title={item.mime_type}
											>
												{isImage ? 'Image' : isPdf ? 'PDF' : 'File'}
											</span>
										{:else if item.source_type === 'web'}
											<span
												class="shrink-0 rounded bg-emerald-900/50 px-2 py-0.5 text-[10px] font-medium text-emerald-300"
												title={item.source_url}
											>
												Web
											</span>
										{/if}
									</div>
									<p class="mt-2 line-clamp-2 text-sm text-zinc-400">
										{item.content}
									</p>
									<div class="mt-2 flex items-center gap-3 text-xs text-zinc-600">
										<span>Updated {new Date(item.updated_at).toLocaleDateString()}</span>
										{#if item.file_size}
											<span>• {(item.file_size / 1024).toFixed(1)} KB</span>
										{/if}
										<!-- View/Download links -->
										{#if item.has_file}
											{#if isPdf}
												<a
													href={getFileUrl(item.id)}
													target="_blank"
													class="text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
												>
													<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
													</svg>
													View PDF
												</a>
											{:else if !isImage}
												<a
													href={getFileUrl(item.id)}
													download
													class="text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
												>
													<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
													</svg>
													Download
												</a>
											{/if}
										{/if}
									</div>
								</div>

								<!-- Action buttons -->
								<div
									class="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100"
								>
									{#if item.has_file}
										<a
											href={getFileUrl(item.id)}
											download
											class="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
											aria-label="Download"
										>
											<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
												/>
											</svg>
										</a>
									{/if}
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
<Modal open={modalOpen} title={modalTitle} onClose={() => (modalOpen = false)} closable={!uploading && !saving && !scraping}>
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
			<!-- Mode toggle for new entries -->
			<div class="flex rounded-lg border border-zinc-600 bg-zinc-800 p-1">
				<button
					type="button"
					onclick={() => (uploadMode = 'text')}
					class="flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors {uploadMode === 'text' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}"
				>
					Text
				</button>
				<button
					type="button"
					onclick={() => (uploadMode = 'file')}
					class="flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors {uploadMode === 'file' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}"
				>
					Upload File
				</button>
				<button
					type="button"
					onclick={() => (uploadMode = 'web')}
					class="flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors {uploadMode === 'web' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}"
				>
					Web URL
				</button>
			</div>
		{/if}

		{#if uploadMode === 'text' || editing}
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
		{:else if uploadMode === 'file'}
			<!-- File upload UI -->
			<div>
				<label class="block text-sm font-medium text-zinc-300">File</label>
				<div class="mt-1.5">
					{#if selectedFile}
						<div class="rounded-lg border border-zinc-600 bg-zinc-800 p-4">
							<div class="flex items-center gap-3">
								<svg class="h-8 w-8 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
								</svg>
								<div class="flex-1 min-w-0">
									<p class="text-sm font-medium text-zinc-200 truncate">{selectedFile.name}</p>
									<p class="text-xs text-zinc-500">{(selectedFile.size / 1024).toFixed(1)} KB</p>
								</div>
								<button
									type="button"
									onclick={() => { selectedFile = null; formTitle = ''; }}
									class="text-zinc-400 hover:text-zinc-200"
								>
									<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
									</svg>
								</button>
							</div>
						</div>
					{:else}
						<label class="flex cursor-pointer flex-col items-center rounded-lg border-2 border-dashed border-zinc-600 bg-zinc-800 p-8 hover:border-zinc-500 hover:bg-zinc-700">
							<svg class="h-10 w-10 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
							</svg>
							<span class="mt-2 text-sm text-zinc-400">Click to upload or drag and drop</span>
							<span class="mt-1 text-xs text-zinc-500">PDF, Word, Excel, PowerPoint, Images, Text</span>
							<input
								type="file"
								class="hidden"
								onchange={handleFileSelect}
								accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.jpg,.jpeg,.png,.gif,.webp"
							/>
						</label>
					{/if}
				</div>
				{#if uploading}
					<div class="mt-2">
						<div class="h-2 rounded bg-zinc-700">
							<div class="h-2 rounded bg-indigo-500 transition-all" style="width: {uploadProgress}%"></div>
						</div>
						<p class="mt-1 text-xs text-zinc-500">
							{#if uploadStage === 'analyzing'}
								<span class="flex items-center gap-1.5">
									<svg class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
										<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
										<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
									</svg>
									{selectedFile?.type === 'application/pdf' ? 'Analyzing document with AI...' : 'Analyzing image with AI...'}
								</span>
							{:else}
								Uploading...
							{/if}
						</p>
					</div>
				{/if}
			</div>
		{:else if uploadMode === 'web'}
			<!-- Web scraping UI -->
			<div>
				<label for="web-url" class="block text-sm font-medium text-zinc-300">Website URL</label>
				<input
					id="web-url"
					type="url"
					bind:value={webUrl}
					placeholder="kiatkoding.com or https://example.com"
					class="mt-1.5 block w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
				/>
			</div>

			<!-- Crawl mode toggle -->
			<div class="flex rounded-lg border border-zinc-600 bg-zinc-800 p-1">
				<button
					type="button"
					onclick={() => (crawlMode = 'single')}
					class="flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors {crawlMode === 'single' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}"
				>
					Single Page
				</button>
				<button
					type="button"
					onclick={() => (crawlMode = 'crawl')}
					class="flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors {crawlMode === 'crawl' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}"
				>
					Crawl Site
				</button>
			</div>

			{#if crawlMode === 'crawl'}
				<div class="space-y-3 rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="max-pages" class="block text-xs font-medium text-zinc-400">Max Pages</label>
							<input
								id="max-pages"
								type="number"
								bind:value={crawlMaxPages}
								min="1"
								max="100"
								class="mt-1 block w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
							/>
						</div>
						<div>
							<label for="max-depth" class="block text-xs font-medium text-zinc-400">Max Depth</label>
							<input
								id="max-depth"
								type="number"
								bind:value={crawlMaxDepth}
								min="1"
								max="5"
								class="mt-1 block w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
							/>
						</div>
					</div>
					<div>
						<label for="path-prefix" class="block text-xs font-medium text-zinc-400">Path Prefix (optional)</label>
						<input
							id="path-prefix"
							type="text"
							bind:value={crawlPathPrefix}
							placeholder="/blog/"
							class="mt-1 block w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
						/>
						<p class="mt-1 text-xs text-zinc-500">Only crawl URLs starting with this path</p>
					</div>
				</div>
			{/if}

			{#if scraping}
				<div class="flex items-center gap-2 text-sm text-zinc-400">
					<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
					</svg>
					{crawlMode === 'single' ? 'Scraping page...' : 'Crawling website...'}
				</div>
			{/if}
		{/if}

		<div class="flex justify-end gap-3 pt-2">
			<Button variant="secondary" onclick={() => (modalOpen = false)}>Cancel</Button>
			<Button type="submit" loading={saving || uploading || scraping} disabled={(uploadMode === 'file' && !selectedFile) || (uploadMode === 'web' && !webUrl.trim())}>
				{#if saving}
					Saving...
				{:else if uploading}
					{uploadStage === 'analyzing' ? 'Analyzing...' : 'Uploading...'}
				{:else if scraping}
					{crawlMode === 'single' ? 'Scraping...' : 'Crawling...'}
				{:else}
					{editing ? 'Update' : uploadMode === 'file' ? 'Upload' : uploadMode === 'web' ? (crawlMode === 'single' ? 'Scrape' : 'Crawl') : 'Create'}
				{/if}
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
