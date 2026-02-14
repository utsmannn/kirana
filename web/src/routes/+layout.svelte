<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { adminToken } from '$lib/stores.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import Toast from '$lib/components/Toast.svelte';

	let { children } = $props();

	let sidebarOpen = $state(false);

	const isLoginPage = $derived(page.url.pathname === `${base}/login`);
	const isLoggedIn = $derived(!!adminToken.value);

	$effect(() => {
		if (!isLoginPage && !isLoggedIn) {
			goto(`${base}/login`);
		}
	});
</script>

<svelte:head>
	<title>Kirana Admin</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

{#if isLoginPage}
	{@render children()}
{:else if isLoggedIn}
	<div class="flex h-screen overflow-hidden">
		<!-- Mobile overlay -->
		{#if sidebarOpen}
			<button
				class="fixed inset-0 z-40 bg-black/60 lg:hidden"
				onclick={() => (sidebarOpen = false)}
				aria-label="Close sidebar"
			></button>
		{/if}

		<!-- Sidebar -->
		<div
			class="fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 ease-out lg:relative lg:translate-x-0 {sidebarOpen
				? 'translate-x-0'
				: '-translate-x-full'}"
		>
			<Sidebar onNavigate={() => (sidebarOpen = false)} />
		</div>

		<!-- Main content -->
		<div class="flex min-w-0 flex-1 flex-col">
			<!-- Top bar -->
			<header class="flex h-14 shrink-0 items-center gap-3 border-b border-zinc-800 px-4">
				<button
					class="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 lg:hidden"
					onclick={() => (sidebarOpen = !sidebarOpen)}
					aria-label="Toggle sidebar"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 6h16M4 12h16M4 18h16"
						/>
					</svg>
				</button>

				<div class="flex flex-1 items-center justify-between">
					<span class="text-sm text-zinc-500">Kirana Admin Panel</span>
				</div>
			</header>

			<!-- Page content -->
			<main class="flex-1 overflow-y-auto">
				{@render children()}
			</main>
		</div>
	</div>
{/if}

<Toast />
