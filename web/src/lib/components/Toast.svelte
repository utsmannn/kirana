<script lang="ts">
	import { getToasts, dismissToast } from '$lib/toast.svelte';

	const toasts = $derived(getToasts());
</script>

{#if toasts.length > 0}
	<div class="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
		{#each toasts as toast (toast.id)}
			<div
				class="flex items-center gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur-sm
					{toast.type === 'success'
					? 'border-emerald-800 bg-emerald-950/90 text-emerald-200'
					: toast.type === 'error'
						? 'border-red-800 bg-red-950/90 text-red-200'
						: 'border-zinc-700 bg-zinc-800/90 text-zinc-200'}"
			>
				<span class="flex-1">{toast.message}</span>
				<button
					onclick={() => dismissToast(toast.id)}
					class="text-current opacity-60 hover:opacity-100"
					aria-label="Dismiss"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M6 18L18 6M6 6l12 12"
						/>
					</svg>
				</button>
			</div>
		{/each}
	</div>
{/if}
