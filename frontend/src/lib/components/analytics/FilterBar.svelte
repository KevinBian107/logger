<script lang="ts">
	import type { SessionResponse, AnalyticsFilters } from '$lib/api/client';

	let {
		sessions,
		onFilterChange
	}: {
		sessions: SessionResponse[];
		onFilterChange: (filters: AnalyticsFilters, timeScale: string) => void;
	} = $props();

	type Scale = 'overall' | 'year' | 'month' | 'week';

	let scale = $state<Scale>('overall');
	let selectedYear = $state<number | null>(null);
	let selectedMonth = $state<number | null>(null);
	let selectedSessionId = $state<number | null>(null);
	let selectedWeek = $state<number | null>(null);

	const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

	// Derive available years from sessions
	let availableYears = $derived.by(() => {
		const years = new Set<number>();
		for (const s of sessions) {
			years.add(s.year);
		}
		return [...years].sort((a, b) => b - a);
	});

	// Derive max week number for the selected session
	let maxWeeks = $derived.by(() => {
		if (!selectedSessionId) return 12;
		const s = sessions.find(s => s.id === selectedSessionId);
		if (!s || !s.start_date || !s.end_date) return 12;
		const start = new Date(s.start_date + 'T00:00:00');
		const end = new Date(s.end_date + 'T00:00:00');
		const diffMs = end.getTime() - start.getTime();
		const weeks = Math.ceil(diffMs / (7 * 24 * 60 * 60 * 1000));
		return Math.max(1, Math.min(weeks, 20));
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
		} else if (scale === 'week' && selectedSessionId !== null && selectedWeek !== null) {
			filters = {
				session_ids: [selectedSessionId],
				week_number: selectedWeek
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
		} else if (s === 'week') {
			if (selectedSessionId === null && sessions.length > 0) {
				selectedSessionId = sessions[sessions.length - 1].id;
			}
			if (selectedWeek === null) {
				selectedWeek = 1;
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

	function handleSessionChange(e: Event) {
		selectedSessionId = Number((e.target as HTMLSelectElement).value);
		selectedWeek = 1;
		emitFilters();
	}

	function handleWeekChange(e: Event) {
		selectedWeek = Number((e.target as HTMLSelectElement).value);
		emitFilters();
	}

	const scales: { key: Scale; label: string }[] = [
		{ key: 'overall', label: 'Overall' },
		{ key: 'year', label: 'Year' },
		{ key: 'month', label: 'Month' },
		{ key: 'week', label: 'Week' },
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

	{#if scale === 'week'}
		<select
			value={selectedSessionId}
			onchange={handleSessionChange}
			class="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground"
		>
			{#each sessions as s}
				<option value={s.id}>{s.label || `${s.season} ${s.year}`}</option>
			{/each}
		</select>
		<select
			value={selectedWeek}
			onchange={handleWeekChange}
			class="rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground"
		>
			{#each Array.from({ length: maxWeeks }, (_, i) => i + 1) as w}
				<option value={w}>Week {w}</option>
			{/each}
		</select>
	{/if}
</div>
