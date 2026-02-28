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

	let tab = $state<'timer' | 'manual'>('timer');
	let categories = $state<CategoryResponse[]>([]);
	let selectedCategoryId = $state<number | null>(null);
	let startingTimer = $state(false);
	let stoppingTimer = $state<TimerEntryResponse | null>(null);
	let todayTimerEntries = $state<TimerEntryResponse[]>([]);
	let todayManualEntries = $state<ManualEntryResponse[]>([]);
	let todayObservations = $state<ObservationResponse[]>([]);

	// Use local date, not UTC
	const now = new Date();
	const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

	async function loadCategories() {
		const session = $activeSession;
		if (!session) return;
		try {
			categories = await api.getCategories(session.id);
		} catch { /* */ }
	}

	async function loadTodayLog() {
		try {
			const data = await api.getDailyActivity(today);
			todayTimerEntries = data.timer_entries;
			todayManualEntries = data.manual_entries;
			todayObservations = data.observations;
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

	async function handleStopSave(id: number, description: string, location: string) {
		try {
			await stopTimer(id, description, location);
			stoppingTimer = null;
			await loadTodayLog();
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDiscard(id: number) {
		try {
			await discardTimer(id);
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDeleteManual(id: number) {
		try {
			await api.deleteManualEntry(id);
			await loadTodayLog();
		} catch (e: unknown) { console.error(e); }
	}

	function handleManualCreated() {
		loadTodayLog();
	}

	onMount(() => {
		loadCategories();
		loadTodayLog();
		startPolling();
	});

	onDestroy(() => {
		stopPolling();
	});
</script>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-bold">Timer</h1>
		<p class="mt-1 text-sm text-muted-foreground">Start timers, add manual entries, view today's log.</p>
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
		</div>

		{#if tab === 'timer'}
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
		{:else}
			<!-- Manual entry form -->
			<div class="rounded-lg border border-border bg-card p-5">
				<ManualEntryForm {categories} onCreated={handleManualCreated} />
			</div>
		{/if}

		<!-- Today's log -->
		<div>
			<h2 class="mb-3 text-lg font-semibold">Today's Log</h2>
			<TodayLog
				timerEntries={todayTimerEntries}
				manualEntries={todayManualEntries}
				observations={todayObservations}
				onDeleteManual={handleDeleteManual}
			/>
		</div>
	{/if}
</div>

<!-- Stop dialog -->
{#if stoppingTimer}
	<StopDialog
		timer={stoppingTimer}
		onSave={handleStopSave}
		onCancel={() => stoppingTimer = null}
	/>
{/if}
