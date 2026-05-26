<script lang="ts">
	import type { SessionResponse, AnalyticsFilters } from '$lib/api/client';

	type Scale = 'overall' | 'year' | 'month';

	// Bindable state lifted to the parent so it survives in-app tab navigation
	// (the +page.svelte exposes a snapshot that captures these values).
	//
	// Note: 'week' was previously a fourth scale but produced inconsistent results
	// — older CSV imports lacked a week column so daily_records had week_number=NULL,
	// and there's no single semantic ("session-relative" vs "ISO calendar week") that
	// works for all data. Removed in favour of Year/Month/Overall which align cleanly
	// with the date_range filter the backend already supports.
	let {
		sessions,
		onFilterChange,
		scale = $bindable<Scale>('overall'),
		selectedYear = $bindable<number | null>(null),
		selectedMonth = $bindable<number | null>(null),
	}: {
		sessions: SessionResponse[];
		onFilterChange: (filters: AnalyticsFilters, timeScale: string) => void;
		scale?: Scale;
		selectedYear?: number | null;
		selectedMonth?: number | null;
	} = $props();

	const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

	// Derive available years from sessions
	let availableYears = $derived.by(() => {
		const years = new Set<number>();
		for (const s of sessions) {
			years.add(s.year);
		}
		return [...years].sort((a, b) => b - a);
	});

	function lastDayOfMonth(year: number, month: number): number {
		return new Date(year, month + 1, 0).getDate();
	}

	function emitFilters() {
		let filters: AnalyticsFilters = {};

		if (scale === 'year' && selectedYear !== null) {
			filters = {
				from_date: `${selectedYear}-01-01`,
				to_date: `${selectedYear}-12-31`
			};
		} else if (scale === 'month' && selectedYear !== null && selectedMonth !== null) {
			const mm = String(selectedMonth + 1).padStart(2, '0');
			const lastDay = lastDayOfMonth(selectedYear, selectedMonth);
			filters = {
				from_date: `${selectedYear}-${mm}-01`,
				to_date: `${selectedYear}-${mm}-${String(lastDay).padStart(2, '0')}`
			};
		}
		// 'overall' sends empty filters

		onFilterChange(filters, scale);
	}

	function setScale(s: Scale) {
		scale = s;

		// Set defaults for secondary selectors
		if (s === 'year') {
			if (selectedYear === null && availableYears.length > 0) {
				selectedYear = availableYears[0];
			}
		} else if (s === 'month') {
			if (selectedYear === null && availableYears.length > 0) {
				selectedYear = availableYears[0];
			}
			if (selectedMonth === null) {
				selectedMonth = new Date().getMonth();
			}
		}

		emitFilters();
	}

	function handleYearChange(e: Event) {
		selectedYear = Number((e.target as HTMLSelectElement).value);
		emitFilters();
	}

	function handleMonthChange(e: Event) {
		selectedMonth = Number((e.target as HTMLSelectElement).value);
		emitFilters();
	}

	const scales: { key: Scale; label: string }[] = [
		{ key: 'overall', label: 'Overall' },
		{ key: 'year', label: 'Year' },
		{ key: 'month', label: 'Month' },
	];
</script>

<div class="flex flex-wrap items-center gap-3">
	<!-- Scale buttons -->
	<div class="flex rounded-lg border border-border bg-card">
		{#each scales as s}
			<button
				onclick={() => setScale(s.key)}
				class="px-3 py-1.5 text-sm font-medium transition-colors first:rounded-l-lg last:rounded-r-lg
					{scale === s.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}"
			>
				{s.label}
			</button>
		{/each}
	</div>

	<!-- Secondary selectors -->
	{#if scale === 'year'}
		<select
			value={selectedYear}
			onchange={handleYearChange}
			class="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground"
		>
			{#each availableYears as y}
				<option value={y}>{y}</option>
			{/each}
		</select>
	{/if}

	{#if scale === 'month'}
		<select
			value={selectedYear}
			onchange={handleYearChange}
			class="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground"
		>
			{#each availableYears as y}
				<option value={y}>{y}</option>
			{/each}
		</select>
		<select
			value={selectedMonth}
			onchange={handleMonthChange}
			class="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground"
		>
			{#each MONTH_NAMES as name, i}
				<option value={i}>{name}</option>
			{/each}
		</select>
	{/if}

</div>
