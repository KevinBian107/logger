<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type BreakDayResponse } from '$lib/api/client';
	import { shortDateLabel } from '$lib/utils/lateNight';

	let {
		// Pre-fills the range when the panel opens (the day the page is viewing).
		presetDate,
		// Notifies the parent so it can refresh the day view (streak / banner).
		onChanged = () => {},
	}: {
		presetDate: string;
		onChanged?: () => void;
	} = $props();

	let startDate = $state(presetDate);
	let endDate = $state(presetDate);
	let label = $state('');
	let breaks = $state<BreakDayResponse[]>([]);
	let saving = $state(false);
	let error = $state('');

	const LABEL_SUGGESTIONS = ['Vacation', 'Sick', 'Rest', 'Holiday', 'Travel'];

	const isValid = $derived(!!startDate && !!endDate && endDate >= startDate);

	async function loadBreaks() {
		try {
			breaks = await api.getBreaks();
		} catch {
			/* */
		}
	}

	async function handleMark() {
		if (!isValid) return;
		saving = true;
		error = '';
		try {
			await api.createBreaks(startDate, endDate, label.trim() || undefined);
			label = '';
			await loadBreaks();
			onChanged();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to mark break';
		}
		saving = false;
	}

	async function handleDelete(date: string) {
		try {
			await api.deleteBreak(date);
			await loadBreaks();
			onChanged();
		} catch (e: unknown) {
			console.error(e);
		}
	}

	onMount(loadBreaks);
</script>

<div class="space-y-5">
	<div class="rounded-lg border border-border bg-card p-5">
		<div class="flex items-start gap-3">
			<span class="text-2xl leading-none">🌴</span>
			<div>
				<h3 class="text-sm font-semibold">Mark a break</h3>
				<p class="mt-0.5 text-xs text-muted-foreground">
					Take a day (or a stretch of days) off. Breaks add no time and bridge your
					streak — resting never breaks it.
				</p>
			</div>
		</div>

		{#if error}
			<div class="mt-4 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-600">{error}</div>
		{/if}

		<div class="mt-4 grid grid-cols-2 gap-4">
			<div>
				<label for="break-start" class="block text-sm font-medium text-muted-foreground">From</label>
				<input
					id="break-start"
					type="date"
					bind:value={startDate}
					class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				/>
			</div>
			<div>
				<label for="break-end" class="block text-sm font-medium text-muted-foreground">To</label>
				<input
					id="break-end"
					type="date"
					bind:value={endDate}
					min={startDate}
					class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				/>
			</div>
		</div>

		<div class="mt-4">
			<label for="break-label" class="block text-sm font-medium text-muted-foreground">
				Label <span class="ml-1 text-xs font-normal italic text-muted-foreground/70">optional</span>
			</label>
			<input
				id="break-label"
				type="text"
				bind:value={label}
				placeholder="e.g., Vacation"
				class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
			/>
			<div class="mt-2 flex flex-wrap gap-1.5">
				{#each LABEL_SUGGESTIONS as s}
					<button
						type="button"
						onclick={() => (label = s)}
						class="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
					>
						{s}
					</button>
				{/each}
			</div>
		</div>

		{#if !isValid && startDate && endDate}
			<p class="mt-3 text-xs text-red-600">End date must be on or after the start date.</p>
		{/if}

		<button
			onclick={handleMark}
			disabled={!isValid || saving}
			class="mt-4 w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
		>
			{saving ? 'Marking…' : startDate === endDate ? 'Mark this day as a break' : 'Mark these days as a break'}
		</button>
	</div>

	<!-- Existing breaks -->
	<div>
		<h3 class="mb-2 text-sm font-semibold">Marked breaks</h3>
		{#if breaks.length === 0}
			<div class="rounded-lg border border-dashed border-border bg-muted/20 p-6 text-center text-sm text-muted-foreground">
				No breaks marked yet.
			</div>
		{:else}
			<ul class="divide-y divide-border overflow-hidden rounded-lg border border-border">
				{#each breaks as b (b.date)}
					<li class="flex items-center justify-between bg-card px-4 py-2.5">
						<div class="flex items-center gap-2">
							<span class="text-base leading-none">🌴</span>
							<span class="text-sm font-medium">{shortDateLabel(b.date)}</span>
							{#if b.label}
								<span class="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400">{b.label}</span>
							{/if}
						</div>
						<button
							onclick={() => handleDelete(b.date)}
							class="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-red-600"
							title="Remove break"
							aria-label="Remove break"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
							</svg>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
