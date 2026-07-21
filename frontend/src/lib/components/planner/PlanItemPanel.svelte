<script lang="ts">
	/**
	 * Right slide-over for a single plan item: edit its fields, see everything
	 * logged against it so far, and start/log/discard work from here. Timer
	 * start/pause/resume/stop reuse the same store + TimerCard + StopDialog the
	 * Dashboard uses — an active timer started from here shows up there too
	 * (same global `activeTimers` store), and vice versa.
	 */
	import type { PlanItemDetailResponse, CategoryResponse, TimerEntryResponse } from '$lib/api/client';
	import { api } from '$lib/api/client';
	import { activeTimers, pauseTimer, resumeTimer, stopTimer, discardTimer, startTimer } from '$lib/stores/timer';
	import TimerCard from '$lib/components/timer/TimerCard.svelte';
	import StopDialog from '$lib/components/timer/StopDialog.svelte';
	import ManualEntryForm from '$lib/components/timer/ManualEntryForm.svelte';
	import NotesEditor from '$lib/components/planner/NotesEditor.svelte';
	import { colorForCategory } from '$lib/utils/chart';
	import { shortDateLabel } from '$lib/utils/lateNight';

	type PlanItemPatch = {
		title?: string;
		category_id?: number;
		start_date?: string;
		end_date?: string;
		start_time?: string | null;
		end_time?: string | null;
		notes?: string | null;
		status?: 'planned' | 'done';
		importance?: 'low' | 'medium' | 'high' | '';
	};

	let {
		itemId,
		categories,
		onClose,
		onChanged,
	}: {
		itemId: number;
		categories: CategoryResponse[];
		onClose: () => void;
		onChanged: () => void;
	} = $props();

	let detail = $state<PlanItemDetailResponse | null>(null);
	let loading = $state(true);
	let error = $state('');
	let showLogTime = $state(false);
	let stoppingTimer = $state<TimerEntryResponse | null>(null);
	let starting = $state(false);
	let deleting = $state(false);

	async function load() {
		loading = true;
		try {
			detail = await api.getPlanItem(itemId);
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to load plan item';
		}
		loading = false;
	}

	$effect(() => {
		itemId;
		load();
	});

	const linkedActiveTimer = $derived($activeTimers.find((t) => t.plan_item_id === itemId) ?? null);
	const isSingleDay = $derived(detail ? detail.start_date === detail.end_date : true);

	async function saveField(patch: PlanItemPatch) {
		if (!detail) return;
		error = '';
		try {
			await api.updatePlanItem(itemId, patch);
			await load();
			onChanged();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to save';
		}
	}

	function handleTitleBlur(e: FocusEvent) {
		const value = (e.target as HTMLInputElement).value;
		if (detail && value.trim() && value !== detail.title) saveField({ title: value });
	}

	function toggleComplete() {
		if (!detail) return;
		saveField({ status: detail.status === 'done' ? 'planned' : 'done' });
	}

	function handleImportanceChange(e: Event) {
		const value = (e.target as HTMLSelectElement).value as 'low' | 'medium' | 'high' | '';
		saveField({ importance: value });
	}

	async function handleStartTimer() {
		if (!detail) return;
		starting = true;
		try {
			await startTimer(detail.category_id, itemId);
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to start timer';
		}
		starting = false;
	}

	async function handlePause(id: number) {
		try { await pauseTimer(id); } catch (e: unknown) { console.error(e); }
	}
	async function handleResume(id: number) {
		try { await resumeTimer(id); } catch (e: unknown) { console.error(e); }
	}
	function handleStopClick(id: number) {
		const t = $activeTimers.find((x) => x.id === id);
		if (t) stoppingTimer = t;
	}
	async function handleStopSave(id: number, description: string, location: string, overrideDate: string | null, markComplete: boolean) {
		try {
			await stopTimer(id, description, location, overrideDate);
			if (markComplete) await api.updatePlanItem(itemId, { status: 'done' });
			stoppingTimer = null;
			await load();
			onChanged();
		} catch (e: unknown) { console.error(e); }
	}
	async function handleDiscardFromDialog(id: number) {
		try {
			await discardTimer(id);
			stoppingTimer = null;
			await load();
		} catch (e: unknown) { console.error(e); }
	}

	function handleLogged() {
		showLogTime = false;
		load();
		onChanged();
	}

	async function handleDelete() {
		if (!confirm('Delete this plan? Time already logged against it stays on your Dashboard, just unlinked.')) return;
		deleting = true;
		try {
			await api.deletePlanItem(itemId);
			onChanged();
			onClose();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to delete';
			deleting = false;
		}
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && !stoppingTimer) onClose();
	}

	function fmtMinutes(min: number): string {
		const h = Math.floor(min / 60);
		const m = min % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}
</script>

<svelte:window onkeydown={handleKey} />

<div
	class="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-[1px]"
	onclick={(e) => { if (e.target === e.currentTarget) onClose(); }}
	role="presentation"
>
	<div class="flex h-full w-full max-w-lg flex-col border-l border-border bg-card shadow-2xl">
		<div class="flex shrink-0 items-center justify-end px-3 py-3">
			<button onclick={onClose} class="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close">
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
			</button>
		</div>

		<div class="flex-1 overflow-y-auto px-8 pb-10">
			{#if error}
				<div class="mb-3 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-600">{error}</div>
			{/if}

			{#if loading && !detail}
				<div class="py-8 text-center text-sm text-muted-foreground">Loading…</div>
			{:else if detail}
				{@const done = detail.status === 'done'}
				<!-- Title -->
				<div class="flex items-start gap-3">
					<button
						type="button"
						onclick={toggleComplete}
						aria-label={done ? 'Mark not complete' : 'Mark complete'}
						class="mt-2.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors {done ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40 hover:border-primary'}"
					>
						{#if done}
							<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>
						{/if}
					</button>
					<input
						value={detail.title}
						onblur={handleTitleBlur}
						class="flex-1 border-none bg-transparent py-1 text-2xl font-bold leading-snug focus:outline-none focus:ring-0 {done ? 'text-muted-foreground line-through' : ''}"
					/>
				</div>

				<!-- Properties -->
				<div class="mt-6 space-y-0.5">
					<!-- Category -->
					<div class="flex items-center gap-3 rounded-md px-1.5 py-1.5 hover:bg-muted/60">
						<div class="flex w-24 shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
							<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5"><circle cx="12" cy="12" r="8"/></svg>
							Category
						</div>
						<span class="h-2 w-2 shrink-0 rounded-full" style="background-color:{colorForCategory(detail.category_name)}"></span>
						<select
							value={detail.category_id}
							onchange={(e) => saveField({ category_id: Number((e.target as HTMLSelectElement).value) })}
							class="min-w-0 flex-1 truncate rounded border-none bg-transparent py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
						>
							{#each categories as cat}
								<option value={cat.id}>{cat.display_name || cat.name}</option>
							{/each}
						</select>
					</div>

					<!-- Priority -->
					<div class="flex items-center gap-3 rounded-md px-1.5 py-1.5 hover:bg-muted/60">
						<div class="flex w-24 shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
							<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 3v18M4.5 4.5h13l-2.2 3.5 2.2 3.5h-13"/></svg>
							Priority
						</div>
						<select
							value={detail.importance ?? ''}
							onchange={handleImportanceChange}
							class="min-w-0 flex-1 rounded border-none bg-transparent py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
						>
							<option value="">None</option>
							<option value="low">Low</option>
							<option value="medium">Medium</option>
							<option value="high">High</option>
						</select>
					</div>

					<!-- When -->
					<div class="flex items-start gap-3 rounded-md px-1.5 py-1.5 hover:bg-muted/60">
						<div class="mt-1 flex w-24 shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
							<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5a2.25 2.25 0 012.25 2.25v7.5"/></svg>
							When
						</div>
						<div class="min-w-0 flex-1 space-y-1 py-0.5">
							<div class="flex items-center gap-1.5 text-sm">
								<input
									type="date"
									value={detail.start_date}
									onchange={(e) => saveField({ start_date: (e.target as HTMLInputElement).value })}
									class="min-w-0 rounded border-none bg-transparent py-0.5 focus:outline-none focus:ring-1 focus:ring-primary"
								/>
								<span class="text-muted-foreground">–</span>
								<input
									type="date"
									value={detail.end_date}
									min={detail.start_date}
									onchange={(e) => saveField({ end_date: (e.target as HTMLInputElement).value })}
									class="min-w-0 rounded border-none bg-transparent py-0.5 focus:outline-none focus:ring-1 focus:ring-primary"
								/>
							</div>
							{#if isSingleDay}
								<div class="flex items-center gap-1.5 text-sm">
									<input
										type="time"
										value={detail.start_time ?? ''}
										onchange={(e) => saveField({ start_time: (e.target as HTMLInputElement).value || '' })}
										class="min-w-0 rounded border-none bg-transparent py-0.5 focus:outline-none focus:ring-1 focus:ring-primary"
									/>
									<span class="text-muted-foreground">–</span>
									<input
										type="time"
										value={detail.end_time ?? ''}
										onchange={(e) => saveField({ end_time: (e.target as HTMLInputElement).value || '' })}
										class="min-w-0 rounded border-none bg-transparent py-0.5 focus:outline-none focus:ring-1 focus:ring-primary"
									/>
								</div>
							{:else}
								<p class="text-[11px] italic text-muted-foreground/70">Spans multiple days — no specific time.</p>
							{/if}
						</div>
					</div>

					<!-- Progress -->
					{#if detail.logged_minutes > 0}
						<div class="flex items-center gap-3 rounded-md px-1.5 py-1.5">
							<div class="flex w-24 shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
								<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><path stroke-linecap="round" d="M12 7v5l3 2"/></svg>
								Logged
							</div>
							<span class="text-sm">
								{fmtMinutes(detail.logged_minutes)}
								<span class="text-muted-foreground">
									· {detail.timer_count + detail.manual_count} session{detail.timer_count + detail.manual_count === 1 ? '' : 's'}
								</span>
							</span>
						</div>
					{/if}
				</div>

				<!-- Notes -->
				<div class="mt-6 border-t border-border pt-4">
					{#key itemId}
						<NotesEditor value={detail.notes ?? ''} onChange={(v) => saveField({ notes: v })} />
					{/key}
				</div>

				<!-- Start / active timer -->
				<div class="mt-6">
					{#if linkedActiveTimer}
						<TimerCard
							timer={linkedActiveTimer}
							onPause={handlePause}
							onResume={handleResume}
							onStop={handleStopClick}
							onDiscard={handleDiscardFromDialog}
						/>
					{:else}
						<div class="flex gap-2">
							<button
								onclick={handleStartTimer}
								disabled={starting}
								class="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
							>
								<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
								Start timer
							</button>
							<button
								onclick={() => (showLogTime = !showLogTime)}
								class="flex-1 rounded-md border border-border px-3 py-2 text-sm font-medium transition-colors hover:border-primary hover:text-primary"
							>
								Log time
							</button>
						</div>
					{/if}

					{#if showLogTime}
						<div class="mt-3 rounded-lg border border-border bg-background/50 p-3">
							<ManualEntryForm
								{categories}
								presetDate={detail.start_date}
								planItemId={itemId}
								presetCategoryId={detail.category_id}
								onCreated={handleLogged}
							/>
						</div>
					{/if}
				</div>

				<!-- Linked sessions -->
				{#if detail.timer_entries.length > 0 || detail.manual_entries.length > 0}
					<div class="mt-6">
						<h4 class="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Logged sessions</h4>
						<ul class="divide-y divide-border">
							{#each detail.timer_entries as t (t.id)}
								<li class="flex items-center justify-between py-2 text-xs">
									<span class="text-muted-foreground">{shortDateLabel(t.date)} · timer</span>
									<span class="font-mono font-medium">{t.duration_minutes ? fmtMinutes(t.duration_minutes) : '—'}</span>
								</li>
							{/each}
							{#each detail.manual_entries as m (m.id)}
								<li class="flex items-center justify-between py-2 text-xs">
									<span class="text-muted-foreground">{shortDateLabel(m.date)} · manual</span>
									<span class="font-mono font-medium">{fmtMinutes(m.duration_minutes)}</span>
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			{/if}
		</div>

		{#if detail}
			<div class="shrink-0 border-t border-border px-8 py-3">
				<button
					onclick={handleDelete}
					disabled={deleting}
					class="text-sm text-muted-foreground transition-colors hover:text-red-600 disabled:opacity-50"
				>
					{deleting ? 'Deleting…' : 'Delete plan'}
				</button>
			</div>
		{/if}
	</div>
</div>

{#if stoppingTimer}
	<StopDialog
		timer={stoppingTimer}
		onSave={handleStopSave}
		onDiscard={handleDiscardFromDialog}
		onCancel={() => (stoppingTimer = null)}
	/>
{/if}
