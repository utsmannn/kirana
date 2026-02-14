<script lang="ts">
	import { page } from '$app/state';
	import { base } from '$app/paths';
	import { logout } from '$lib/auth';

	interface Props {
		onNavigate?: () => void;
	}

	let { onNavigate }: Props = $props();

	const navItems = [
		{
			href: `${base}/`,
			label: 'Dashboard',
			icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6'
		},
		{
			href: `${base}/chat`,
			label: 'Chat',
			icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z'
		},
		{
			href: `${base}/channels`,
			label: 'Channels',
			icon: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z'
		},
		{
			href: `${base}/knowledge`,
			label: 'Knowledge',
			icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253'
		},
		{
			href: `${base}/sessions`,
			label: 'Sessions',
			icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10'
		},
		{
			href: `${base}/settings`,
			label: 'Settings',
			icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z'
		}
	];

	function isActive(href: string): boolean {
		const current = page.url.pathname;
		if (href === `${base}/`) {
			return current === `${base}/` || current === `${base}`;
		}
		return current.startsWith(href);
	}
</script>

<nav
	class="flex h-full w-64 flex-col border-r border-zinc-800 bg-zinc-900"
>
	<!-- Logo -->
	<div class="flex h-14 items-center gap-2.5 border-b border-zinc-800 px-5">
		<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
			K
		</div>
		<span class="text-base font-semibold text-zinc-100">Kirana</span>
		<span class="rounded bg-zinc-700 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">Admin</span>
	</div>

	<!-- Nav items -->
	<div class="flex-1 overflow-y-auto px-3 py-3">
		<ul class="space-y-1">
			{#each navItems as item}
				{@const active = isActive(item.href)}
				<li>
					<a
						href={item.href}
						onclick={onNavigate}
						class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors
							{active
							? 'bg-indigo-600/15 text-indigo-400'
							: 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}"
					>
						<svg
							class="h-5 w-5 shrink-0"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
							stroke-width="1.5"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
						</svg>
						{item.label}
					</a>
				</li>
			{/each}
		</ul>
	</div>

	<!-- Logout -->
	<div class="border-t border-zinc-800 p-3">
		<button
			onclick={logout}
			class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-red-400"
		>
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
				/>
			</svg>
			Logout
		</button>
	</div>
</nav>
