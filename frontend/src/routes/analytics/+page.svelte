<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type AnalyticsFilters,
		type AnalyticsOverviewResponse,
		type DailySeriesPoint,
		type CategoryBreakdownItem,
		type HeatmapPoint,
		type SessionResponse
	} from '$lib/api/client';
	import { sessions, loadSessions } from '$lib/stores/session';
	import { todayYMDNow } from '$lib/stores/clock';
	import { addDaysYMD } from '$lib/utils/lateNight';
	import { formatHoursMinutes } from '$lib/utils/chart';
	import StatCard from '$lib/components/dashboard/StatCard.svelte';
	import FilterBar from '$lib/components/analytics/FilterBar.svelte';
	import DailyAreaChart from '$lib/components/analytics/DailyAreaChart.svelte';
	import CategoryBars from '$lib/components/analytics/CategoryBars.svelte';
	import WeeklyHeatmap from '$lib/components/analytics/WeeklyHeatmap.svelte';

	let overview = $state<AnalyticsOverviewResponse | null>(null);
	let dailyData = $state<DailySeriesPoint[]>([]);

	// Monday-anchored YYYY-MM-DD for any input date string (parsed as local).
	function mondayOf(ymd: string): string {
		const [y, m, d] = ymd.split('-').map(Number);
		const dt = new Date(y, m - 1, d);
		const day = dt.getDay(); // 0=Sun … 6=Sat
		const shift = day === 0 ? -6 : 1 - day;
		dt.setDate(dt.getDate() + shift);
		const pad = (n: number) => String(n).padStart(2, '0');
		return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
	}

	// Group daily-series points into ISO weeks, summing total_minutes and merging
	// the per-category breakdowns. The Monday of each week becomes the point's
	// `date`, so DailyAreaChart's existing time-axis logic just works.
	function bucketByWeek(series: DailySeriesPoint[]): DailySeriesPoint[] {
		const buckets = new Map<
			string,
			{ total: number; cats: Map<string, { name: string; minutes: number; color: string | null }> }
		>();
		for (const d of series) {
			const monday = mondayOf(d.date);
			let b = buckets.get(monday);
			if (!b) {
				b = { total: 0, cats: new Map() };
				buckets.set(monday, b);
			}
			b.total += d.total_minutes;
			for (const c of d.categories) {
				const existing = b.cats.get(c.name);
				if (existing) existing.minutes += c.minutes;
				else b.cats.set(c.name, { name: c.name, minutes: c.minutes, color: c.color });
			}
		}
		return [...buckets.entries()]
			.sort((a, b) => a[0].localeCompare(b[0]))
			.map(([date, b]) => ({
				date,
				total_minutes: b.total,
				categories: [...b.cats.values()],
			}));
	}
	let categoryData = $state<CategoryBreakdownItem[]>([]);
	let heatmapData = $state<HeatmapPoint[]>([]);
	let allSessions = $state<SessionResponse[]>([]);

	let loadingMain = $state(true);
	let error = $state<string | null>(null);
	let currentFilters = $state<AnalyticsFilters>({});
	// FilterBar internals are bound from here so the snapshot can preserve them.
	let scale = $state<'overall' | 'year' | 'month' | 'range'>('overall');
	let filterYear = $state<number | null>(null);
	let filterMonth = $state<number | null>(null);
	let filterFrom = $state<string>(addDaysYMD(todayYMDNow(), -29));
	let filterTo = $state<string>(todayYMDNow());
	// A one-day range has nothing to trend and one heatmap cell, so those two
	// range views sit it out and the breakdown carries the day.
	const singleDay = $derived(scale === 'range' && filterFrom === filterTo);

	// For overall view, bucket the daily series into ISO weeks. Year and Month
	// stay day-resolution since they have ≤366 / 31 points respectively.
	const chartData = $derived(
		scale === 'overall' ? bucketByWeek(dailyData) : dailyData,
	);

	async function fetchFilteredData(filters: AnalyticsFilters) {
		try {
			const [ov, daily, cats, heatmap] = await Promise.all([
				api.getAnalyticsOverview(filters),
				api.getAnalyticsDaily(filters),
				api.getAnalyticsCategories(filters),
				api.getAnalyticsHeatmap(filters),
			]);
			overview = ov;
			dailyData = daily;
			categoryData = cats;
			heatmapData = heatmap;
			error = null;
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to load analytics';
		}
	}

	async function loadAll() {
		loadingMain = true;

		try {
			await loadSessions();
		} catch { /* */ }

		const unsub = sessions.subscribe(s => { allSessions = s; });
		unsub();

		await fetchFilteredData(currentFilters);

		loadingMain = false;
	}

	function handleFilterChange(filters: AnalyticsFilters, _scale: string) {
		currentFilters = filters;
		// `scale` is bound directly via the FilterBar prop so we don't need to copy it here.
		fetchFilteredData(filters);
	}

	onMount(() => {
		// Subscribe to session store
		const unsub = sessions.subscribe(s => { allSessions = s; });
		loadAll();
		return unsub;
	});

	// Preserve filter selection across in-app navigation. SvelteKit's
	// snapshot.capture runs before this page unmounts on tab switch, and
	// snapshot.restore runs when it remounts — so Month/Week + the picked
	// year/month/session/week aren't lost when the user pops over to Timer.
	export const snapshot = {
		capture: () => ({
			filters: currentFilters,
			scale,
			filterYear,
			filterMonth,
			filterFrom,
			filterTo,
		}),
		restore: (s: {
			filters: AnalyticsFilters;
			scale: 'overall' | 'year' | 'month' | 'range';
			filterYear: number | null;
			filterMonth: number | null;
			filterFrom: string;
			filterTo: string;
		}) => {
			currentFilters = s.filters;
			scale = s.scale;
			filterYear = s.filterYear;
			filterMonth = s.filterMonth;
			filterFrom = s.filterFrom ?? addDaysYMD(todayYMDNow(), -29);
			filterTo = s.filterTo ?? todayYMDNow();
			// SvelteKit calls restore() AFTER onMount, so loadAll() has already
			// fetched with the default empty filters. Re-issue with the restored
			// filters so the charts match what the snapshot remembered.
			fetchFilteredData(s.filters);
		},
	};
</script>

<div class="space-y-6">
	<!-- Header + Filters -->
	<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold">Analytics</h1>
			<p class="text-sm text-muted-foreground">Visual insights across all sessions</p>
		</div>
		<FilterBar
			sessions={allSessions}
			onFilterChange={handleFilterChange}
			bind:scale
			bind:selectedYear={filterYear}
			bind:selectedMonth={filterMonth}
			bind:rangeFrom={filterFrom}
			bind:rangeTo={filterTo}
		/>
	</div>

	{#if error}
		<div class="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
			{error}
		</div>
	{/if}

	{#if loadingMain}
		<div class="flex items-center justify-center py-12 text-sm text-muted-foreground">
			Loading analytics...
		</div>
	{:else}
		<!-- Overview stat cards -->
		{#if overview}
			<div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
				<StatCard
					label="Total Hours"
					value={formatHoursMinutes(overview.total_minutes)}
				/>
				<StatCard
					label="Days Tracked"
					value={String(overview.days_tracked)}
				/>
				<StatCard
					label="Daily Average"
					value={formatHoursMinutes(overview.daily_average)}
				/>
				<StatCard
					label="Active Categories"
					value={String(overview.active_categories)}
				/>
			</div>
		{/if}

		<!-- Trend chart — daily for Year/Month, weekly buckets for Overall.
		     The bucketing happens client-side in `chartData`. Range mode stays at
		     day resolution; a one-day range hides the trend and the heatmap. -->
		{#if !singleDay}
			<DailyAreaChart data={chartData} timeScale={scale} />
		{/if}

		<!-- Full-width, stacked: the breakdown scrolls inside its own box so a
		     long category list doesn't push the heatmap off the page. -->
		<CategoryBars data={categoryData} />

		{#if !singleDay}
			<WeeklyHeatmap data={heatmapData} />
		{/if}
	{/if}
</div>
