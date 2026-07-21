<script module lang="ts">
	export type ImportanceFilter = 'high' | 'medium' | 'low' | 'none';
	export type PlannerFilters = {
		categoryIds: Set<number>;        // empty = no filter (all categories)
		importance: Set<ImportanceFilter>; // empty = no filter (all levels)
		complete: 'all' | 'done' | 'planned';
	};

	export function defaultPlannerFilters(): PlannerFilters {
		return { categoryIds: new Set(), importance: new Set(), complete: 'all' };
	}
</script>

<script lang="ts">
	/**
	 * Notion-style filter chips: a pill button showing the current state that
	 * opens a checkbox popover. Styled after the only existing precedent for a
	 * floating panel in this app — DatePicker.svelte's calendar popover.
	 */
	import type { CategoryResponse } from '$lib/api/client';

	let {
		categories,
		filters,
		onChange,
	}: {
		categories: CategoryResponse[];
		filters: PlannerFilters;
		onChange: (filters: PlannerFilters) => void;
	} = $props();

	let openChip = $state<'category' | 'importance' | 'complete' | null>(null);

	function toggle(chip: typeof openChip) {
		openChip = openChip === chip ? null : chip;
	}

	function toggleCategory(id: number) {
		const next = new Set(filters.categoryIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		onChange({ ...filters, categoryIds: next });
	}

	function toggleImportance(v: ImportanceFilter) {
		const next = new Set(filters.importance);
		if (next.has(v)) next.delete(v);
		else next.add(v);
		onChange({ ...filters, importance: next });
	}

	function setComplete(v: PlannerFilters['complete']) {
		onChange({ ...filters, complete: v });
	}

	function clearAll() {
		onChange(defaultPlannerFilters());
	}

	const hasAnyFilter = $derived(
		filters.categoryIds.size > 0 || filters.importance.size > 0 || filters.complete !== 'all'
	);

	const IMPORTANCE_OPTIONS: { value: ImportanceFilter; label: string; dot: string }[] = [
		{ value: 'high', label: 'High', dot: 'bg-red-500' },
		{ value: 'medium', label: 'Medium', dot: 'bg-amber-500' },
		{ value: 'low', label: 'Low', dot: 'bg-sky-500' },
		{ value: 'none', label: 'None', dot: 'bg-muted-foreground/40' },
	];

	const completeLabel = $derived(
		filters.complete === 'all' ? 'All' : filters.complete === 'done' ? 'Done' : 'Not done'
	);

	function onWindowClick(e: MouseEvent) {
		if (!openChip) return;
		const target = e.target as HTMLElement;
		if (!target.closest('.planner-filter-root')) openChip = null;
	}
</script>

<svelte:window onclick={onWindowClick} />

<div class="planner-filter-root flex flex-wrap items-center gap-2">
	<!-- Category -->
	<div class="relative">
		<button
			type="button"
			onclick={(e) => { e.stopPropagation(); toggle('category'); }}
			class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors
				{filters.categoryIds.size > 0 ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border bg-card text-muted-foreground hover:text-foreground'}"
		>
			Category{filters.categoryIds.size > 0 ? ` (${filters.categoryIds.size})` : ''}
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
		</button>
		{#if openChip === 'category'}
			<div class="absolute left-0 z-30 mt-2 max-h-72 w-56 overflow-y-auto rounded-xl border border-border bg-card p-2 shadow-2xl" onclick={(e) => e.stopPropagation()} role="presentation">
				{#each categories as cat}
					<label class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted">
						<input type="checkbox" checked={filters.categoryIds.has(cat.id)} onchange={() => toggleCategory(cat.id)} class="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary" />
						{cat.display_name || cat.name}
					</label>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Importance -->
	<div class="relative">
		<button
			type="button"
			onclick={(e) => { e.stopPropagation(); toggle('importance'); }}
			class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors
				{filters.importance.size > 0 ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border bg-card text-muted-foreground hover:text-foreground'}"
		>
			Priority{filters.importance.size > 0 ? ` (${filters.importance.size})` : ''}
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
		</button>
		{#if openChip === 'importance'}
			<div class="absolute left-0 z-30 mt-2 w-44 rounded-xl border border-border bg-card p-2 shadow-2xl" onclick={(e) => e.stopPropagation()} role="presentation">
				{#each IMPORTANCE_OPTIONS as opt}
					<label class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted">
						<input type="checkbox" checked={filters.importance.has(opt.value)} onchange={() => toggleImportance(opt.value)} class="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary" />
						<span class="h-2 w-2 rounded-full {opt.dot}"></span>
						{opt.label}
					</label>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Complete -->
	<div class="relative">
		<button
			type="button"
			onclick={(e) => { e.stopPropagation(); toggle('complete'); }}
			class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors
				{filters.complete !== 'all' ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border bg-card text-muted-foreground hover:text-foreground'}"
		>
			Complete: {completeLabel}
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
		</button>
		{#if openChip === 'complete'}
			<div class="absolute left-0 z-30 mt-2 w-36 rounded-xl border border-border bg-card p-2 shadow-2xl" onclick={(e) => e.stopPropagation()} role="presentation">
				{#each [['all', 'All'], ['planned', 'Not done'], ['done', 'Done']] as [v, label]}
					<button
						type="button"
						onclick={() => setComplete(v as PlannerFilters['complete'])}
						class="flex w-full items-center rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted {filters.complete === v ? 'font-semibold text-primary' : ''}"
					>
						{label}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	{#if hasAnyFilter}
		<button type="button" onclick={clearAll} class="text-xs text-muted-foreground hover:text-foreground hover:underline">
			Clear filters
		</button>
	{/if}
</div>
