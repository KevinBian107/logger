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

	const SEASON_ORDER: Record<string, number> = { winter: 0, spring: 1, summer: 2, fall: 3 };

	// Newest first, bucketed by the session's year so 17+ quarters scan quickly.
	const byYear = $derived.by(() => {
		const groups = new Map<number, SessionResponse[]>();
		const sorted = [...sessions].sort(
			(a, b) => b.year - a.year || (SEASON_ORDER[b.season] ?? 0) - (SEASON_ORDER[a.season] ?? 0)
		);
		for (const s of sorted) {
			const list = groups.get(s.year) ?? [];
			list.push(s);
			groups.set(s.year, list);
		}
		return [...groups.entries()].map(([year, list]) => ({
			year,
			sessions: list,
			total: list.reduce((sum, s) => sum + s.total_minutes, 0),
		}));
	});

	function formatHours(minutes: number): string {
		const hours = Math.floor(minutes / 60);
		const mins = minutes % 60;
		if (hours === 0) return `${mins}m`;
		if (mins === 0) return `${hours}h`;
		return `${hours}h ${mins}m`;
	}
</script>

<div class="space-y-5">
	{#each byYear as group (group.year)}
		<div>
			<div class="mb-1 flex items-baseline justify-between px-3">
				<span class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{group.year}</span>
				<span class="text-[11px] tabular-nums text-muted-foreground/80">{Math.round(group.total / 60)}h</span>
			</div>
			<div class="space-y-0.5">
				{#each group.sessions as session (session.id)}
					{@const isSelected = session.id === selectedId}
					<button
						onclick={() => onSelect(session.id)}
						aria-current={isSelected ? 'true' : undefined}
						class="flex w-full items-center justify-between gap-3 rounded-lg border-l-2 px-3 py-2 text-left transition-colors
							{isSelected
								? 'border-primary bg-primary/10 text-foreground'
								: 'border-transparent text-foreground hover:bg-muted'}"
					>
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								<span class="truncate text-sm font-medium">{session.label}</span>
								{#if session.is_active}
									<span class="inline-flex shrink-0 items-center gap-1 rounded-full bg-green-500/10 px-1.5 py-px text-[10px] font-medium text-green-700 dark:text-green-400">
										<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
										Active
									</span>
								{/if}
							</div>
							<div class="mt-0.5 text-xs text-muted-foreground">
								{session.days_logged} days &middot; {session.categories.length} categories
							</div>
						</div>
						<span class="shrink-0 text-xs font-medium tabular-nums text-muted-foreground">
							{formatHours(session.total_minutes)}
						</span>
					</button>
				{/each}
			</div>
		</div>
	{/each}

	{#if sessions.length === 0}
		<div class="py-4 text-center text-sm text-muted-foreground">
			No sessions yet. Import CSV data to get started.
		</div>
	{/if}
</div>
