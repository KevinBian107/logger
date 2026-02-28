<script lang="ts">
	import type { GroupSummary } from '$lib/api/client';

	let {
		groups,
		selectedGroupType,
		onSelect
	}: {
		groups: GroupSummary[];
		selectedGroupType: string | null;
		onSelect: (groupType: string) => void;
	} = $props();

	function formatHours(minutes: number): string {
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	const GROUP_ICONS: Record<string, string> = {
		research: 'M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5',
		course: 'M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342',
		personal: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
		other: 'M6.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM12.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM18.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0z',
	};
</script>

<div class="space-y-1.5">
	{#each groups as group}
		<button
			onclick={() => onSelect(group.group_type)}
			class="w-full rounded-lg border px-3 py-3 text-left transition-colors {selectedGroupType === group.group_type
				? 'border-primary bg-primary/5 ring-1 ring-primary/20'
				: 'border-border bg-card hover:bg-muted/50'}"
		>
			<div class="flex items-center gap-2.5">
				<svg class="h-4 w-4 shrink-0 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d={GROUP_ICONS[group.group_type] || GROUP_ICONS.other} />
				</svg>
				<span class="text-sm font-semibold">
					{group.label}
				</span>
				<span class="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
					{group.family_count}
				</span>
			</div>
			<div class="mt-1 pl-6.5 text-[11px] text-muted-foreground">
				{formatHours(group.total_minutes)}
			</div>
		</button>
	{/each}
</div>
