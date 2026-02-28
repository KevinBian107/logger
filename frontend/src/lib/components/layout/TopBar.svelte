<script lang="ts">
	import { activeSession } from '$lib/stores/session';
	import { theme, toggleTheme } from '$lib/stores/theme';

	const themeIcons: Record<string, string> = {
		light: 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z',
		dark: 'M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z',
		system: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'
	};
</script>

<header class="flex h-14 items-center justify-between border-b border-border bg-background px-6">
	<div class="flex items-center gap-3">
		{#if $activeSession}
			<a
				href="/data"
				class="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
			>
				<span class="h-2 w-2 rounded-full bg-green-500"></span>
				{$activeSession.label}
			</a>
		{:else}
			<span class="text-sm text-muted-foreground">No active session</span>
		{/if}
	</div>

	<button
		onclick={toggleTheme}
		class="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
		title="Toggle theme ({$theme})"
	>
		<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
			<path stroke-linecap="round" stroke-linejoin="round" d={themeIcons[$theme]} />
		</svg>
	</button>
</header>
