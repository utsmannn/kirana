<script lang="ts">
	interface Props {
		loading?: boolean;
		variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
		size?: 'sm' | 'md' | 'lg';
		type?: 'button' | 'submit';
		disabled?: boolean;
		onclick?: (e: MouseEvent) => void;
		children: import('svelte').Snippet;
		class?: string;
	}

	let {
		loading = false,
		variant = 'primary',
		size = 'md',
		type = 'button',
		disabled = false,
		onclick,
		children,
		class: className = ''
	}: Props = $props();

	const baseClasses =
		'inline-flex items-center justify-center font-medium rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed';

	const variantClasses = $derived(
		variant === 'primary'
			? 'bg-indigo-600 text-white hover:bg-indigo-500 active:bg-indigo-700'
			: variant === 'secondary'
				? 'bg-zinc-700 text-zinc-200 hover:bg-zinc-600 border border-zinc-600'
				: variant === 'danger'
					? 'bg-red-600 text-white hover:bg-red-500 active:bg-red-700'
					: 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
	);

	const sizeClasses = $derived(
		size === 'sm'
			? 'px-3 py-1.5 text-xs gap-1.5'
			: size === 'lg'
				? 'px-5 py-3 text-base gap-2.5'
				: 'px-4 py-2 text-sm gap-2'
	);
</script>

<button
	{type}
	{onclick}
	disabled={disabled || loading}
	class="{baseClasses} {variantClasses} {sizeClasses} {className}"
>
	{#if loading}
		<svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
			<path
				class="opacity-75"
				fill="currentColor"
				d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
			/>
		</svg>
	{/if}
	{@render children()}
</button>
