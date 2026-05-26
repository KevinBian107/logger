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
	import WebsiteBanner from '$lib/components/dashboard/WebsiteBanner.svelte';
	import StopDialog from '$lib/components/timer/StopDialog.svelte';
	import TodayLog from '$lib/components/timer/TodayLog.svelte';
	import EditEntryModal from '$lib/components/timer/EditEntryModal.svelte';
	import DatePicker from '$lib/components/dashboard/DatePicker.svelte';
	import { formatLocalYMD, shortDateLabel } from '$lib/utils/lateNight';
	import type { ManualEntryResponse } from '$lib/api/client';

	const todayLabel = new Date().toLocaleDateString(undefined, {
		weekday: 'long',
		month: 'long',
		day: 'numeric',
	});

	// SVG icon strings used by stat cards
	const ICON_CLOCK = `<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.75"><circle cx="12" cy="12" r="9"/><path stroke-linecap="round" d="M12 7v5l3 2"/></svg>`;
	const ICON_LIST = `<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h10"/></svg>`;
	const ICON_FLAME = `<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M12 2c1 4 5 6 5 11a5 5 0 11-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-4-1-6 1-10z"/></svg>`;

	// `today` is captured once on mount; `selectedDate` is what the user is viewing
	// (today by default, or any past day picked via the calendar). The two are
	// compared to render different copy and disable today-only affordances.
	const today = formatLocalYMD(new Date());
	let selectedDate = $state<string>(today);
	const viewingToday = $derived(selectedDate === today);

	let dailyActivity = $state<DailyActivityResponse | null>(null);
	let streak = $state<StreakResponse>({ current: 0, longest: 0 });
	let categories = $state<CategoryResponse[]>([]);
	let quickCategoryId = $state<number | null>(null);
	let startingQuick = $state(false);
	let stoppingTimer = $state<TimerEntryResponse | null>(null);
	let editingTimer = $state<TimerEntryResponse | null>(null);
	let editingManual = $state<ManualEntryResponse | null>(null);

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
				api.getDailyActivity(selectedDate),
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

	// Reload whenever the user picks a different date in the calendar.
	$effect(() => {
		selectedDate;
		if (dailyActivity !== null) {
			loadDashboard();
		}
	});

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

	async function handleStopSave(id: number, description: string, location: string, overrideDate: string | null) {
		try {
			await stopTimer(id, description, location, overrideDate);
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

	function handleEditTimer(id: number) {
		const t = (dailyActivity?.timer_entries || []).find(x => x.id === id);
		if (t) editingTimer = t;
	}

	function handleEditManual(id: number) {
		const m = (dailyActivity?.manual_entries || []).find(x => x.id === id);
		if (m) editingManual = m;
	}

	async function handleEditSaved() {
		editingTimer = null;
		editingManual = null;
		await loadDashboard();
	}

	function handleEditDeleted() {
		editingTimer = null;
		editingManual = null;
		loadDashboard();
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
	<WebsiteBanner />

	<!-- Hero: greeting + date + date picker + active-session pill -->
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-3xl font-bold tracking-tight">{getGreeting()}</h1>
			<p class="mt-1 text-sm text-muted-foreground">{todayLabel}</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<DatePicker bind:value={selectedDate} maxDate={today} />
			{#if !viewingToday}
				<button
					onclick={() => (selectedDate = today)}
					class="inline-flex items-center gap-1.5 rounded-full border border-dashed border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
					title="Jump back to today"
				>
					<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l-7 7 7 7M2 12h20"/></svg>
					Back to today
				</button>
			{/if}
			{#if $activeSession}
				<a
					href="/data"
					class="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-sm transition-colors hover:border-primary/40 hover:bg-card/80"
				>
					<span class="relative flex h-2 w-2">
						<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-50"></span>
						<span class="relative inline-flex h-2 w-2 rounded-full bg-green-500"></span>
					</span>
					<span class="font-medium">{$activeSession.label}</span>
					<span class="text-muted-foreground">· active</span>
				</a>
			{:else}
				<a
					href="/data"
					class="inline-flex items-center gap-2 rounded-full border border-dashed border-border px-3.5 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
				>
					No active session — set one up
				</a>
			{/if}
		</div>
	</div>

	{#if $activeSession}
		<!-- Stat cards. Labels switch from "Today's…" to the picked day's date when off-today. -->
		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
			<StatCard
				label={viewingToday ? "Today's Total" : `${shortDateLabel(selectedDate)} Total`}
				value={formatHoursMinutes(dailyActivity?.total_minutes ?? 0)}
				sublabel={entryCount === 0 ? (viewingToday ? 'Nothing logged yet' : 'Nothing on this day') : undefined}
				accent={(dailyActivity?.total_minutes ?? 0) > 0}
				icon={ICON_CLOCK}
			/>
			<StatCard
				label={viewingToday ? 'Entries Today' : 'Entries'}
				value={String(entryCount)}
				sublabel={entryCount === 1 ? 'entry' : 'entries'}
				icon={ICON_LIST}
			/>
			<StatCard
				label="Current Streak"
				value="{streak.current}d"
				sublabel="Longest {streak.longest}d"
				accent={streak.current > 0}
				icon={ICON_FLAME}
			/>
			<!-- Quick start -->
			<div class="group relative overflow-hidden rounded-xl border border-border bg-card p-4 transition-all hover:shadow-sm">
				<div class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Quick Start</div>
				<div class="mt-2.5 flex items-center gap-2">
					<select
						bind:value={quickCategoryId}
						class="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					>
						<option value={null}>Choose category…</option>
						{#each categories as cat}
							<option value={cat.id}>{cat.display_name || cat.name}</option>
						{/each}
					</select>
					<button
						onclick={handleQuickStart}
						disabled={!quickCategoryId || startingQuick}
						class="shrink-0 rounded-md bg-primary p-2 text-primary-foreground transition-all hover:bg-primary/90 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
						title="Start timer"
						aria-label="Start timer"
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
			<div class="space-y-5">
				{#if dailyActivity.observations.length > 0}
					<section>
						<div class="mb-3 flex items-baseline justify-between">
							<h2 class="text-lg font-semibold">{viewingToday ? "Today's Breakdown" : `${shortDateLabel(selectedDate)} · Breakdown`}</h2>
							<span class="text-xs text-muted-foreground">{formatHoursMinutes(dailyActivity.total_minutes)} across {dailyActivity.observations.length} categor{dailyActivity.observations.length === 1 ? 'y' : 'ies'}</span>
						</div>
						<div class="flex h-7 overflow-hidden rounded-full bg-muted shadow-inner">
							{#each dailyActivity.observations as obs}
								{@const pct = dailyActivity.total_minutes > 0
									? (obs.minutes / dailyActivity.total_minutes) * 100
									: 0}
								{#if pct > 0}
									<div
										class="flex items-center justify-center bg-primary text-xs font-medium text-primary-foreground transition-opacity hover:opacity-100"
										style="width: {pct}%; opacity: {0.55 + (pct / 250)}"
										title="{obs.category_name}: {obs.minutes}m ({pct.toFixed(0)}%)"
									>
										{#if pct > 10}
											<span class="truncate px-2">{obs.category_name}</span>
										{/if}
									</div>
								{/if}
							{/each}
						</div>
					</section>
				{/if}

				<section>
					<div class="mb-3 flex items-baseline justify-between">
						<h2 class="text-lg font-semibold">{viewingToday ? "Today's Entries" : `${shortDateLabel(selectedDate)} · Entries`}</h2>
						{#if entryCount > 0}
							<span class="text-xs text-muted-foreground">{entryCount} entr{entryCount === 1 ? 'y' : 'ies'}</span>
						{/if}
					</div>
					{#if entryCount === 0}
						<div class="rounded-xl border border-dashed border-border bg-muted/30 p-8 text-center">
							<p class="text-sm font-medium">Nothing logged today yet</p>
							<p class="mt-1 text-xs text-muted-foreground">Pick a category above and hit play, or use the <a href="/timer" class="text-primary hover:underline">Timer page</a> for manual entry.</p>
						</div>
					{:else}
						<TodayLog
							timerEntries={dailyActivity.timer_entries}
							manualEntries={dailyActivity.manual_entries}
							observations={dailyActivity.observations}
							onDeleteManual={handleDeleteManual}
							onDeleteTimer={handleDeleteTimer}
							onEditTimer={handleEditTimer}
							onEditManual={handleEditManual}
						/>
					{/if}
				</section>
			</div>
		{/if}
	{:else}
		<!-- No active session — empty state with CTA -->
		<div class="rounded-2xl border border-dashed border-border bg-muted/20 p-10 text-center">
			<div class="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
				<svg class="h-6 w-6 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25"/>
				</svg>
			</div>
			<h2 class="text-lg font-semibold">No active session</h2>
			<p class="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
				Sessions are how log(ger) organizes time — typically one per academic quarter or work cycle. Create one or import a CSV to get started.
			</p>
			<a
				href="/data"
				class="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
			>
				Open Data page
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/>
				</svg>
			</a>
		</div>
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

{#if (editingTimer || editingManual) && $activeSession}
	<EditEntryModal
		timerEntry={editingTimer}
		manualEntry={editingManual}
		sessionId={$activeSession.id}
		onSaved={handleEditSaved}
		onDeleted={handleEditDeleted}
		onCancel={() => { editingTimer = null; editingManual = null; }}
	/>
{/if}
