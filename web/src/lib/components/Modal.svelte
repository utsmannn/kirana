<script lang="ts">
	interface Props {
		open: boolean;
		title?: string;
		onClose: () => void;
		closable?: boolean;
		children: import('svelte').Snippet;
	}

	let { open, title = '', onClose, closable = true, children }: Props = $props();

	function handleKeydown(e: KeyboardEvent) {
		if (!closable) return;
		if (e.key === 'Escape') onClose();
	}

	function handleBackdropClick() {
		if (!closable) return;
		onClose();
	}
</script>

{#if open}
	<div class="fixed inset-0 z-[90] flex items-center justify-center p-4">
		<!-- Backdrop -->
		<button
			class="absolute inset-0 bg-black/70 backdrop-blur-sm {closable ? 'cursor-pointer' : 'cursor-not-allowed'}"
			onclick={handleBackdropClick}
			aria-label={closable ? 'Close modal' : ''}
			disabled={!closable}
		></button>

		<!-- Modal -->
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<!-- svelte-ignore a11y_interactive_supports_focus -->
		<div
			role="dialog"
			aria-modal="true"
			aria-label={title || 'Dialog'}
			class="relative w-full max-w-lg rounded-xl border border-zinc-700 bg-zinc-800 shadow-2xl"
			onkeydown={handleKeydown}
		>
			{#if title}
				<div class="flex items-center justify-between border-b border-zinc-700 px-6 py-4">
					<h2 class="text-lg font-semibold text-zinc-100">{title}</h2>
					{#if closable}
						<button
							onclick={onClose}
							class="rounded-md p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
							aria-label="Close"
						>
							<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M6 18L18 6M6 6l12 12"
								/>
							</svg>
						</button>
					{/if}
				</div>
			{/if}
			<div class="p-6">
				{@render children()}
			</div>
		</div>
	</div>
{/if}
