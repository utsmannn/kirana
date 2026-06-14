<script lang="ts">
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { onMount } from 'svelte';

	onMount(() => {
		goto(`${base}/channels`, { replaceState: true });
	});
</script>

<div class="mx-auto max-w-3xl p-6">
	<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-8 text-center">
		<h1 class="text-xl font-semibold text-zinc-100">Knowledge moved to Channels</h1>
		<p class="mt-2 text-sm text-zinc-400">
			Knowledge is now scoped per channel. Manage it from the Channels page.
		</p>
		<a
			href={`${base}/channels`}
			class="mt-5 inline-flex rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
		>
			Open Channels
		</a>
	</div>
</div>
