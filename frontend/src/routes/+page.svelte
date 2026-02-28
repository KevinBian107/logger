<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		api, type CategoryResponse, type DailyActivityResponse,
		type StreakResponse, type TimerEntryResponse
	} from '$lib/api/client';
	import { activeSession, loadActiveSession } from '$lib/stores/session';
	import {
		activeTimers, loadActiveTimers, startPolling, stopPolling,
		startTimer, pauseTimer, resumeTimer, stopTimer
	} from '$lib/stores/timer';
	import StatCard from '$lib/components/dashboard/StatCard.svelte';
	import ActiveTimers from '$lib/components/dashboard/ActiveTimers.svelte';
	import StopDialog from '$lib/components/timer/StopDialog.svelte';
	import TodayLog from '$lib/components/timer/TodayLog.svelte';

	// Use local date, not UTC
	const now = new Date();
	const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

	let dailyActivity = $state<DailyActivityResponse | null>(null);
	let streak = $state<StreakResponse>({ current: 0, longest: 0 });
	let categories = $state<CategoryResponse[]>([]);
	let quickCategoryId = $state<number | null>(null);
	let startingQuick = $state(false);
	let stoppingTimer = $state<TimerEntryResponse | null>(null);

	function getGreeting(): string {
		const h = new Date().getHours();
		if (h < 12) return 'Good morning';
		if (h < 17) return 'Good afternoon';
		return 'Good evening';
	}

	function formatHoursMinutes(min: number): string {
		const h = Math.floor(min / 60);
		const m = min % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	async function loadDashboard() {
		await loadActiveSession();
		try {
			const [activity, streakData] = await Promise.all([
				api.getDailyActivity(today),
				api.getStreak()
			]);
			dailyActivity = activity;
			streak = streakData;
		} catch { /* */ }

		const session = $activeSession;
		if (session) {
			try {
				categories = await api.getCategories(session.id);
			} catch { /* */ }
		}
	}

	async function handleQuickStart() {
		if (!quickCategoryId) return;
		startingQuick = true;
		try {
			await startTimer(quickCategoryId);
			quickCategoryId = null;
		} catch (e: unknown) { console.error(e); }
		startingQuick = false;
	}

	async function handlePause(id: number) {
		try { await pauseTimer(id); } catch (e: unknown) { console.error(e); }
	}

	async function handleResume(id: number) {
		try { await resumeTimer(id); } catch (e: unknown) { console.error(e); }
	}

	function handleStopClick(id: number) {
		const timer = $activeTimers.find(t => t.id === id);
		if (timer) stoppingTimer = timer;
	}

	async function handleStopSave(id: number, description: string, location: string) {
		try {
			await stopTimer(id, description, location);
			stoppingTimer = null;
			await loadDashboard();
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDeleteManual(id: number) {
		try {
			await api.deleteManualEntry(id);
			await loadDashboard();
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDeleteTimer(id: number) {
		try {
			await api.discardTimer(id);
			await loadDashboard();
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDiscard(id: number) {
		try {
			await api.discardTimer(id);
			stoppingTimer = null;
			await loadActiveTimers();
			await loadDashboard();
		} catch (e: unknown) { console.error(e); }
	}

	onMount(() => {
		loadDashboard();
		startPolling();
	});

	onDestroy(() => {
		stopPolling();
	});

	const entryCount = $derived(
		(dailyActivity?.timer_entries.length ?? 0) +
		(dailyActivity?.manual_entries.length ?? 0) +
		(dailyActivity?.observations.length ?? 0)
	);
</script>

<div class="space-y-6">
	<!-- Greeting + session badge -->
	<div>
		<h1 class="text-2xl font-bold">{getGreeting()}</h1>
		{#if $activeSession}
			<p class="mt-1 text-sm text-muted-foreground">
				<span class="inline-flex items-center gap-1.5">
					<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
					{$activeSession.label}
				</span>
			</p>
		{:else}
			<p class="mt-1 text-sm text-muted-foreground">
				No active session — <a href="/data" class="text-primary underline">go to Data</a>
			</p>
		{/if}
	</div>

	{#if $activeSession}
		<!-- Stat cards -->
		<div class="grid grid-cols-4 gap-4">
			<StatCard
				label="Today's Total"
				value={formatHoursMinutes(dailyActivity?.total_minutes ?? 0)}
			/>
			<StatCard
				label="Entries Today"
				value={String(entryCount)}
			/>
			<StatCard
				label="Current Streak"
				value="{streak.current}d"
				sublabel="Longest: {streak.longest}d"
			/>
			<!-- Quick start -->
			<div class="rounded-lg border border-border bg-card p-4">
				<div class="text-xs font-medium text-muted-foreground">Quick Start</div>
				<div class="mt-2 flex items-center gap-2">
					<select
						bind:value={quickCategoryId}
						class="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:border-primary focus:outline-none"
					>
						<option value={null}>Category...</option>
						{#each categories as cat}
							<option value={cat.id}>{cat.display_name || cat.name}</option>
						{/each}
					</select>
					<button
						onclick={handleQuickStart}
						disabled={!quickCategoryId || startingQuick}
						class="rounded-md bg-primary p-1.5 text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
						title="Start timer"
					>
						<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
					</button>
				</div>
			</div>
		</div>

		<!-- Active timers -->
		<ActiveTimers
			timers={$activeTimers}
			onPause={handlePause}
			onResume={handleResume}
			onStop={handleStopClick}
		/>

		<!-- Today's log -->
		{#if dailyActivity}
			<div>
				<!-- Observation bar -->
				{#if dailyActivity.observations.length > 0}
					<h2 class="mb-3 text-lg font-semibold">Today's Breakdown</h2>
					<div class="mb-4 flex h-6 overflow-hidden rounded-full bg-muted">
						{#each dailyActivity.observations as obs}
							{@const pct = dailyActivity.total_minutes > 0
								? (obs.minutes / dailyActivity.total_minutes) * 100
								: 0}
							{#if pct > 0}
								<div
									class="flex items-center justify-center text-xs font-medium text-white bg-primary"
									style="width: {pct}%; opacity: {0.5 + (pct / 200)}"
									title="{obs.category_name}: {obs.minutes}m"
								>
									{#if pct > 8}
										{obs.category_name}
									{/if}
								</div>
							{/if}
						{/each}
					</div>
				{/if}

				<h2 class="mb-3 text-lg font-semibold">Entries</h2>
				<TodayLog
					timerEntries={dailyActivity.timer_entries}
					manualEntries={dailyActivity.manual_entries}
					observations={dailyActivity.observations}
					onDeleteManual={handleDeleteManual}
					onDeleteTimer={handleDeleteTimer}
				/>
			</div>
		{/if}
	{/if}
</div>

{#if stoppingTimer}
	<StopDialog
		timer={stoppingTimer}
		onSave={handleStopSave}
		onDiscard={handleDiscard}
		onCancel={() => stoppingTimer = null}
	/>
{/if}
