<script lang="ts">
	import { page } from '$app/state';

	// `hidden` tabs keep their route and code but are not shown. The Projects
	// tab (/chat/projects) is parked for now — flip `hidden` to bring it back.
	const tabs = [
		{ href: '/chat', label: 'Chat', hidden: false },
		{ href: '/chat/projects', label: 'Projects', hidden: true },
	];
	const visibleTabs = tabs.filter((t) => !t.hidden);

	function isActive(href: string): boolean {
		if (href === '/chat') return page.url.pathname === '/chat';
		return page.url.pathname.startsWith(href);
	}

	let { children } = $props();
</script>

<!-- -m-6 cancels main's ambient p-6 so the tab bar + Chat's own message stream
     can span edge-to-edge, matching how the Chat page already did this before
     the Projects tab was folded in here. Projects' own page restores its p-6.
     With a single visible tab the bar is pointless, so it is not rendered. -->
<div class="flex h-full flex-col -m-6">
	{#if visibleTabs.length > 1}
		<div class="flex shrink-0 gap-1 border-b border-border px-6 pt-3">
			{#each visibleTabs as t}
				<a
					href={t.href}
					class="rounded-t-md border-b-2 px-3 py-2 text-sm font-medium transition-colors
						{isActive(t.href)
							? 'border-primary text-foreground'
							: 'border-transparent text-muted-foreground hover:text-foreground'}"
				>
					{t.label}
				</a>
			{/each}
		</div>
	{/if}
	<div class="min-h-0 flex-1">
		{@render children()}
	</div>
</div>
