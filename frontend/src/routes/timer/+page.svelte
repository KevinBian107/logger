<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api, type CategoryResponse, type TimerEntryResponse, type ManualEntryResponse, type ObservationResponse } from '$lib/api/client';
	import { activeSession } from '$lib/stores/session';
	import {
		activeTimers, loadActiveTimers, startPolling, stopPolling,
		startTimer, pauseTimer, resumeTimer, stopTimer, discardTimer
	} from '$lib/stores/timer';
	import TimerCard from '$lib/components/timer/TimerCard.svelte';
	import StopDialog from '$lib/components/timer/StopDialog.svelte';
	import ManualEntryForm from '$lib/components/timer/ManualEntryForm.svelte';
	import TodayLog from '$lib/components/timer/TodayLog.svelte';
	import EditEntryModal from '$lib/components/timer/EditEntryModal.svelte';
	import BreakPanel from '$lib/components/timer/BreakPanel.svelte';
	import DatePicker from '$lib/components/dashboard/DatePicker.svelte';
	import BreakBanner from '$lib/components/dashboard/BreakBanner.svelte';
	import { viewDate } from '$lib/stores/viewDate';
	import { formatLocalYMD, shortDateLabel } from '$lib/utils/lateNight';
	import { get } from 'svelte/store';

	let tab = $state<'timer' | 'manual' | 'break'>('timer');
	let categories = $state<CategoryResponse[]>([]);
	let selectedCategoryId = $state<number | null>(null);
	let startingTimer = $state(false);
	let stoppingTimer = $state<TimerEntryResponse | null>(null);
	let editingTimer = $state<TimerEntryResponse | null>(null);
	let editingManual = $state<ManualEntryResponse | null>(null);
	let todayTimerEntries = $state<TimerEntryResponse[]>([]);
	let todayManualEntries = $state<ManualEntryResponse[]>([]);
	let todayObservations = $state<ObservationResponse[]>([]);
	let dayIsBreak = $state(false);
	let breakLabel = $state<string | null>(null);

	// Shared selected day (survives navigation; see viewDate store). `today` is
	// captured once for comparison.
	const today = formatLocalYMD(new Date());
	let selectedDate = $state<string>(get(viewDate));
	const viewingToday = $derived(selectedDate === today);
	$effect(() => { viewDate.set(selectedDate); });

	// Reload the log whenever the viewed day changes.
	$effect(() => {
		selectedDate;
		loadLog();
	});

	async function loadCategories() {
		const session = $activeSession;
		if (!session) return;
		try {
			categories = await api.getCategories(session.id);
		} catch { /* */ }
	}

	async function loadLog() {
		try {
			const data = await api.getDailyActivity(selectedDate);
			todayTimerEntries = data.timer_entries;
			todayManualEntries = data.manual_entries;
			todayObservations = data.observations;
			dayIsBreak = data.is_break;
			breakLabel = data.break_label;
		} catch { /* */ }
	}

	async function handleStart() {
		if (!selectedCategoryId) return;
		startingTimer = true;
		try {
			await startTimer(selectedCategoryId);
			selectedCategoryId = null;
		} catch (e: unknown) {
			console.error('Failed to start timer:', e);
		}
		startingTimer = false;
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
			await loadLog();
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDiscard(id: number) {
		try {
			await discardTimer(id);
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDiscardFromDialog(id: number) {
		try {
			await api.discardTimer(id);
			stoppingTimer = null;
			await loadActiveTimers();
			await loadLog();
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDeleteManual(id: number) {
		try {
			await api.deleteManualEntry(id);
			await loadLog();
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDeleteTimer(id: number) {
		try {
			await api.discardTimer(id);
			await loadLog();
		} catch (e: unknown) { console.error(e); }
	}

	function handleEditTimer(id: number) {
		const t = todayTimerEntries.find(x => x.id === id);
		if (t) editingTimer = t;
	}

	function handleEditManual(id: number) {
		const m = todayManualEntries.find(x => x.id === id);
		if (m) editingManual = m;
	}

	async function handleEditSaved() {
		editingTimer = null;
		editingManual = null;
		await loadLog();
	}

	function handleEditDeleted() {
		editingTimer = null;
		editingManual = null;
		loadLog();
	}

	function handleManualCreated() {
		loadLog();
	}

	onMount(() => {
		loadCategories();
		loadLog();
		startPolling();
	});

	onDestroy(() => {
		stopPolling();
	});
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-2xl font-bold">Timer</h1>
			<p class="mt-1 text-sm text-muted-foreground">Start timers, add manual entries, mark breaks.</p>
		</div>
		{#if $activeSession}
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
			</div>
		{/if}
	</div>

	{#if !$activeSession}
		<div class="rounded-lg border border-border bg-card p-8 text-center">
			<p class="text-muted-foreground">No active session. Go to <a href="/data" class="text-primary underline">Data</a> to activate or create a session.</p>
		</div>
	{:else}
		<!-- Tab bar -->
		<div class="flex gap-1 rounded-lg bg-muted p-1">
			<button
				onclick={() => tab = 'timer'}
				class="flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors {
					tab === 'timer' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
				}"
			>
				Timer
			</button>
			<button
				onclick={() => tab = 'manual'}
				class="flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors {
					tab === 'manual' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
				}"
			>
				Manual Entry
			</button>
			<button
				onclick={() => tab = 'break'}
				class="flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors {
					tab === 'break' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
				}"
			>
				Break
			</button>
		</div>

		{#if tab === 'timer'}
			{#if !viewingToday}
				<p class="rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
					Live timers always run for <span class="font-medium">now</span>. To log time for {shortDateLabel(selectedDate)}, use <button class="text-primary hover:underline" onclick={() => (tab = 'manual')}>Manual Entry</button>.
				</p>
			{/if}
			<!-- Start new timer -->
			<div class="rounded-lg border border-border bg-card p-4">
				<div class="flex items-end gap-3">
					<div class="flex-1">
						<label for="timer-cat" class="block text-sm font-medium text-muted-foreground">Category</label>
						<select
							id="timer-cat"
							bind:value={selectedCategoryId}
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
						>
							<option value={null}>Select category...</option>
							{#each categories as cat}
								<option value={cat.id}>{cat.display_name || cat.name}</option>
							{/each}
						</select>
					</div>
					<button
						onclick={handleStart}
						disabled={!selectedCategoryId || startingTimer}
						class="flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
					>
						<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
						Start
					</button>
				</div>
			</div>

			<!-- Active timers -->
			{#if $activeTimers.length > 0}
				<div>
					<h2 class="mb-3 text-lg font-semibold">Active Timers</h2>
					<div class="space-y-3">
						{#each $activeTimers as timer (timer.id)}
							<TimerCard
								{timer}
								onPause={handlePause}
								onResume={handleResume}
								onStop={handleStopClick}
								onDiscard={handleDiscard}
							/>
						{/each}
					</div>
				</div>
			{/if}
		{:else if tab === 'manual'}
			<!-- Manual entry form. When viewing a past day, default the entry to it;
			     on today keep the late-night Today/Yesterday prompt behavior. -->
			<div class="rounded-lg border border-border bg-card p-5">
				<ManualEntryForm
					{categories}
					presetDate={viewingToday ? undefined : selectedDate}
					onCreated={handleManualCreated}
				/>
			</div>
		{:else}
			<!-- Break panel -->
			<BreakPanel presetDate={selectedDate} onChanged={loadLog} />
		{/if}

		<!-- Break banner for the viewed day -->
		{#if dayIsBreak}
			<BreakBanner label={breakLabel} date={selectedDate} {viewingToday} />
		{/if}

		<!-- Day log -->
		<div>
			<h2 class="mb-3 text-lg font-semibold">{viewingToday ? "Today's Log" : `${shortDateLabel(selectedDate)} · Log`}</h2>
			<TodayLog
				timerEntries={todayTimerEntries}
				manualEntries={todayManualEntries}
				observations={todayObservations}
				onDeleteManual={handleDeleteManual}
				onDeleteTimer={handleDeleteTimer}
				onEditTimer={handleEditTimer}
				onEditManual={handleEditManual}
			/>
		</div>
	{/if}
</div>

<!-- Stop dialog -->
{#if stoppingTimer}
	<StopDialog
		timer={stoppingTimer}
		onSave={handleStopSave}
		onDiscard={handleDiscardFromDialog}
		onCancel={() => stoppingTimer = null}
	/>
{/if}

<!-- Edit modal — keyed so it re-mounts when switching between entries -->
{#if (editingTimer || editingManual) && $activeSession}
	{#key (editingTimer?.id ?? 't-none') + '/' + (editingManual?.id ?? 'm-none')}
		<EditEntryModal
			timerEntry={editingTimer}
			manualEntry={editingManual}
			sessionId={$activeSession.id}
			onSaved={handleEditSaved}
			onDeleted={handleEditDeleted}
			onCancel={() => { editingTimer = null; editingManual = null; }}
		/>
	{/key}
{/if}
