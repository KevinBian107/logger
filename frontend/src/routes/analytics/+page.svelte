<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type AnalyticsFilters,
		type AnalyticsOverviewResponse,
		type DailySeriesPoint,
		type CategoryBreakdownItem,
		type HeatmapPoint,
		type SessionComparisonItem,
		type SessionResponse
	} from '$lib/api/client';
	import { sessions, loadSessions } from '$lib/stores/session';
	import { formatHoursMinutes } from '$lib/utils/chart';
	import StatCard from '$lib/components/dashboard/StatCard.svelte';
	import FilterBar from '$lib/components/analytics/FilterBar.svelte';
	import DailyAreaChart from '$lib/components/analytics/DailyAreaChart.svelte';
	import CategoryBars from '$lib/components/analytics/CategoryBars.svelte';
	import WeeklyHeatmap from '$lib/components/analytics/WeeklyHeatmap.svelte';
	import SessionBars from '$lib/components/analytics/SessionBars.svelte';

	let overview = $state<AnalyticsOverviewResponse | null>(null);
	let dailyData = $state<DailySeriesPoint[]>([]);
	let categoryData = $state<CategoryBreakdownItem[]>([]);
	let heatmapData = $state<HeatmapPoint[]>([]);
	let sessionData = $state<SessionComparisonItem[]>([]);
	let allSessions = $state<SessionResponse[]>([]);

	let loadingMain = $state(true);
	let loadingSessions = $state(true);
	let error = $state<string | null>(null);
	let currentFilters = $state<AnalyticsFilters>({});
	let currentScale = $state<string>('overall');

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
		loadingSessions = true;

		try {
			await loadSessions();
		} catch { /* */ }

		const unsub = sessions.subscribe(s => { allSessions = s; });
		unsub();

		await Promise.all([
			fetchFilteredData(currentFilters),
			api.getAnalyticsSessions().then(d => { sessionData = d; }).catch(() => {}),
		]);

		loadingMain = false;
		loadingSessions = false;
	}

	function handleFilterChange(filters: AnalyticsFilters, scale: string) {
		currentFilters = filters;
		currentScale = scale;
		fetchFilteredData(filters);
	}

	onMount(() => {
		// Subscribe to session store
		const unsub = sessions.subscribe(s => { allSessions = s; });
		loadAll();
		return unsub;
	});
</script>

<div class="space-y-6">
	<!-- Header + Filters -->
	<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold">Analytics</h1>
			<p class="text-sm text-muted-foreground">Visual insights across all sessions</p>
		</div>
		<FilterBar sessions={allSessions} onFilterChange={handleFilterChange} />
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

		<!-- Daily area chart -->
		<DailyAreaChart data={dailyData} timeScale={currentScale} />

		<!-- Two-column: Category bars + Heatmap -->
		<div class="grid gap-4 lg:grid-cols-2">
			<CategoryBars data={categoryData} />
			<WeeklyHeatmap data={heatmapData} />
		</div>

		<!-- Session comparison -->
		<SessionBars data={sessionData} />
	{/if}
</div>
