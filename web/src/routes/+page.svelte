<script lang="ts">
	import { base } from '$app/paths';
	import { getUsage, ApiError, type UsageData } from '$lib/api';
	import { apiKey } from '$lib/stores.svelte';
	import { onMount } from 'svelte';

	let usage = $state<UsageData | null>(null);
	let loadingUsage = $state(false);

	const quickLinks = [
		{
			href: `${base}/chat`,
			title: 'Chat Playground',
			desc: 'Test conversations with your AI',
			icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z'
		},
		{
			href: `${base}/knowledge`,
			title: 'Knowledge Base',
			desc: 'Manage knowledge entries',
			icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253'
		},
		{
			href: `${base}/sessions`,
			title: 'Sessions',
			desc: 'View chat history',
			icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10'
		},
		{
			href: `${base}/settings`,
			title: 'Settings',
			desc: 'Configure model and behavior',
			icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z'
		}
	];

	onMount(() => {
		loadUsage();
	});

	async function loadUsage() {
		loadingUsage = true;
		try {
			usage = await getUsage();
		} catch {
			// usage may not be available
		} finally {
			loadingUsage = false;
		}
	}

	async function copyApiKey() {
		if (!apiKey.value) return;
		try {
			await navigator.clipboard.writeText(apiKey.value);
		} catch {
			// ignore
		}
	}
</script>

<div class="mx-auto max-w-4xl p-6">
	<div class="mb-8">
		<h1 class="text-2xl font-bold text-zinc-100">Dashboard</h1>
		<p class="mt-1 text-sm text-zinc-400">Kirana AI Service Overview</p>
	</div>

	<!-- API Key Card -->
	<div class="mb-6 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
		<h2 class="text-sm font-medium text-zinc-400">API Key</h2>
		{#if apiKey.value}
			<div class="mt-3 flex items-center gap-3">
				<code class="flex-1 rounded-lg bg-zinc-950 px-4 py-3 font-mono text-sm text-zinc-300">
					{apiKey.value}
				</code>
				<button
					onclick={copyApiKey}
					class="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700"
				>
					Copy
				</button>
			</div>
			<p class="mt-2 text-xs text-zinc-500">
				Use this key in your Authorization header: <code>Bearer {apiKey.value}</code>
			</p>
		{:else}
			<p class="mt-3 text-sm text-zinc-500">
				API key will be displayed after login.
			</p>
		{/if}
	</div>

	<!-- Usage stats -->
	<div class="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
			<p class="text-sm text-zinc-400">Total Requests</p>
			<p class="mt-2 text-2xl font-bold text-zinc-100">
				{#if loadingUsage}
					<span class="inline-block h-7 w-16 animate-pulse rounded bg-zinc-800"></span>
				{:else}
					{usage?.total_requests ?? 0}
				{/if}
			</p>
		</div>
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
			<p class="text-sm text-zinc-400">Total Tokens</p>
			<p class="mt-2 text-2xl font-bold text-zinc-100">
				{#if loadingUsage}
					<span class="inline-block h-7 w-16 animate-pulse rounded bg-zinc-800"></span>
				{:else}
					{(usage?.total_tokens ?? 0).toLocaleString()}
				{/if}
			</p>
		</div>
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
			<p class="text-sm text-zinc-400">Input Tokens</p>
			<p class="mt-2 text-2xl font-bold text-zinc-100">
				{#if loadingUsage}
					<span class="inline-block h-7 w-16 animate-pulse rounded bg-zinc-800"></span>
				{:else}
					{(usage?.total_input_tokens ?? 0).toLocaleString()}
				{/if}
			</p>
		</div>
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
			<p class="text-sm text-zinc-400">Output Tokens</p>
			<p class="mt-2 text-2xl font-bold text-zinc-100">
				{#if loadingUsage}
					<span class="inline-block h-7 w-16 animate-pulse rounded bg-zinc-800"></span>
				{:else}
					{(usage?.total_output_tokens ?? 0).toLocaleString()}
				{/if}
			</p>
		</div>
	</div>

	<!-- Quick links -->
	<div>
		<h3 class="mb-3 text-sm font-medium text-zinc-400">Quick Links</h3>
		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
			{#each quickLinks as link}
				<a
					href={link.href}
					class="group rounded-xl border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-zinc-700 hover:bg-zinc-800/80"
				>
					<svg
						class="h-5 w-5 text-zinc-500 transition-colors group-hover:text-indigo-400"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						stroke-width="1.5"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d={link.icon} />
					</svg>
					<p class="mt-2 text-sm font-medium text-zinc-200">{link.title}</p>
					<p class="mt-0.5 text-xs text-zinc-500">{link.desc}</p>
				</a>
			{/each}
		</div>
	</div>
</div>
