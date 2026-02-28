<script lang="ts">
	import type { SessionResponse } from '$lib/api/client';

	let {
		sessions,
		selectedId,
		onSelect
	}: {
		sessions: SessionResponse[];
		selectedId: number | null;
		onSelect: (id: number) => void;
	} = $props();

	function formatHours(minutes: number): string {
		const hours = Math.floor(minutes / 60);
		const mins = minutes % 60;
		if (hours === 0) return `${mins}m`;
		if (mins === 0) return `${hours}h`;
		return `${hours}h ${mins}m`;
	}
</script>

<div class="space-y-1">
	{#each sessions as session}
		{@const isSelected = session.id === selectedId}
		<button
			onclick={() => onSelect(session.id)}
			class="flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left transition-colors
				{isSelected
					? 'bg-primary/10 text-foreground'
					: 'text-foreground hover:bg-muted'}"
		>
			<div class="min-w-0">
				<div class="flex items-center gap-2">
					{#if session.is_active}
						<span class="h-2 w-2 shrink-0 rounded-full bg-green-500"></span>
					{/if}
					<span class="truncate text-sm font-medium">{session.label}</span>
				</div>
				<div class="mt-0.5 text-xs text-muted-foreground">
					{session.days_logged} days &middot; {session.categories.length} categories
				</div>
			</div>
			<span class="shrink-0 text-xs font-medium text-muted-foreground">
				{formatHours(session.total_minutes)}
			</span>
		</button>
	{/each}

	{#if sessions.length === 0}
		<div class="py-4 text-center text-sm text-muted-foreground">
			No sessions yet. Import CSV data to get started.
		</div>
	{/if}
</div>
