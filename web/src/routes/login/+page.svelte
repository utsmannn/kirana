<script lang="ts">
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { adminLogin, getAdminConfig, ApiError } from '$lib/api';
	import { adminToken, apiKey } from '$lib/stores.svelte';
	import Button from '$lib/components/Button.svelte';

	let password = $state('');
	let loading = $state(false);
	let error = $state('');

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (!password.trim()) return;

		loading = true;
		error = '';

		try {
			const result = await adminLogin(password);
			adminToken.value = result.token;

			// Fetch API key for display
			try {
				const config = await getAdminConfig(result.token);
				apiKey.value = config.api_key;
			} catch {
				// Ignore error - API key fetch is not critical
			}

			goto(`${base}/`);
		} catch (err) {
			if (err instanceof ApiError) {
				error = err.message;
			} else {
				error = 'Failed to connect to server';
			}
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
	<div class="w-full max-w-sm">
		<!-- Logo -->
		<div class="mb-8 text-center">
			<div
				class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-xl font-bold text-white shadow-lg shadow-indigo-600/20"
			>
				K
			</div>
			<h1 class="text-2xl font-bold text-zinc-100">Kirana Admin</h1>
			<p class="mt-1 text-sm text-zinc-500">Enter your admin password to continue</p>
		</div>

		<!-- Login form -->
		<form onsubmit={handleSubmit} class="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
			<div class="space-y-4">
				<div>
					<label for="password" class="block text-sm font-medium text-zinc-300">Password</label>
					<input
						id="password"
						type="password"
						bind:value={password}
						placeholder="Admin password"
						autocomplete="current-password"
						class="mt-1.5 block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 transition-colors focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
					/>
				</div>

				{#if error}
					<div class="rounded-lg border border-red-800/50 bg-red-950/50 px-3 py-2 text-sm text-red-300">
						{error}
					</div>
				{/if}

				<Button type="submit" {loading} class="w-full">
					{loading ? 'Signing in...' : 'Sign in'}
				</Button>
			</div>
		</form>

		<p class="mt-6 text-center text-xs text-zinc-600">
			Multi-tenant AI Chat API Administration
		</p>
	</div>
</div>
