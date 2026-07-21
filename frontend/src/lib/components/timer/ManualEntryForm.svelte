<script lang="ts">
	import type { CategoryResponse } from '$lib/api/client';
	import { api } from '$lib/api/client';
	import LateNightDatePrompt from './LateNightDatePrompt.svelte';
	import { formatLocalYMD, isLateNight, lateNightDateOptions } from '$lib/utils/lateNight';
	import { manualEntryDraft, resetManualEntryDraft } from '$lib/stores/drafts';
	import { timezone, localDateTimeToUtcIso } from '$lib/stores/timezone';
	import { onMount } from 'svelte';

	let {
		categories,
		onCreated,
		// When set (e.g. the dashboard "Add entry" modal for a viewed day), the
		// form defaults to this date instead of today/yesterday, and the late-night
		// Today/Yesterday prompt is suppressed (the user already chose the day).
		presetDate = undefined,
		// When set (logging time from the Planner against a plan item), the entry
		// gets linked via plan_item_id and a "Mark plan complete" checkbox appears.
		planItemId = null,
		// When set (logging time against a plan item), the category is fixed to
		// the plan's own category — same reasoning as presetDate: never overwritten
		// by the draft-restore below.
		presetCategoryId = null
	}: {
		categories: CategoryResponse[];
		onCreated: () => void;
		presetDate?: string;
		planItemId?: number | null;
		presetCategoryId?: number | null;
	} = $props();

	function defaultDate(): string {
		if (presetDate) return presetDate;
		return isLateNight() ? lateNightDateOptions().yesterday : formatLocalYMD(new Date());
	}

	// Local copies of the draft fields. We read once on mount and write back
	// to the store via $effect so the draft survives page navigation.
	let categoryId = $state<number | null>(presetCategoryId);
	let date = $state(defaultDate());
	let hours = $state(0);
	let minutes = $state(0);
	let description = $state('');
	let location = $state('');
	// Optional start time as HH:MM in the user's tz. '' = leave the entry's
	// timeline position inferred from when it was logged.
	let startTime = $state('');
	let error = $state('');
	let saving = $state(false);
	// Default unchecked — see StopDialog for the same reasoning (a multi-day
	// plan is expected to accumulate several logged sessions before it's done).
	let markComplete = $state(false);

	onMount(() => {
		const unsub = manualEntryDraft.subscribe((d) => {
			// Restore in-progress form input across tab navigation, but NEVER
			// touch the date. A stored "yesterday" value from a previous-day
			// session matches today's "yesterday" string and silently files new
			// entries under the wrong day. The date always uses the fresh
			// initializer (today, or yesterday-in-late-night) at mount time;
			// the user can override via the date input or the LateNightDatePrompt.
			// Same treatment for category when a plan fixed it via presetCategoryId.
			if (presetCategoryId == null) categoryId = d.categoryId;
			hours = d.hours;
			minutes = d.minutes;
			description = d.description;
			location = d.location;
			startTime = d.startTime;
		});
		unsub();
	});

	// Persist any local change back to the store so a tab-switch preserves it.
	$effect(() => {
		manualEntryDraft.set({ categoryId, date, hours, minutes, description, location, startTime });
	});

	const totalMinutes = $derived(hours * 60 + minutes);
	const isValid = $derived(categoryId !== null && totalMinutes > 0);

	async function handleSubmit() {
		if (!isValid || !categoryId) return;
		error = '';
		saving = true;
		try {
			// Translate the optional HH:MM input into a UTC ISO start_time on the
			// entry's date. Empty input → leave it unset (start inferred).
			let startIso: string | undefined;
			if (startTime) {
				const [h, m] = startTime.split(':').map(Number);
				startIso = localDateTimeToUtcIso(date, h || 0, m || 0, $timezone);
			}
			await api.createManualEntry({
				category_id: categoryId,
				date,
				duration_minutes: totalMinutes,
				description: description || undefined,
				location: location || undefined,
				start_time: startIso,
				plan_item_id: planItemId || undefined
			});
			if (planItemId && markComplete) {
				await api.updatePlanItem(planItemId, { status: 'done' });
			}
			// Reset form + clear the persisted draft (it was for this entry).
			categoryId = null;
			hours = 0;
			minutes = 0;
			description = '';
			location = '';
			startTime = '';
			markComplete = false;
			// Re-default the date too — otherwise the local `date` would carry
			// whatever the user picked into the next entry, including stale values.
			date = defaultDate();
			resetManualEntryDraft();
			onCreated();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to create entry';
		}
		saving = false;
	}
</script>

<div class="space-y-4">
	{#if error}
		<div class="rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-600">{error}</div>
	{/if}

	{#if !presetDate}
		<LateNightDatePrompt bind:value={date} />
	{/if}

	<div class="grid grid-cols-2 gap-4">
		<div>
			<label for="me-date" class="block text-sm font-medium text-muted-foreground">Date</label>
			<input
				id="me-date"
				type="date"
				bind:value={date}
				class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
			/>
		</div>
		<div>
			<label for="me-cat" class="block text-sm font-medium text-muted-foreground">Category</label>
			<select
				id="me-cat"
				bind:value={categoryId}
				class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
			>
				<option value={null}>Select category...</option>
				{#each categories as cat}
					<option value={cat.id}>{cat.display_name || cat.name}</option>
				{/each}
			</select>
		</div>
	</div>

	<div>
		<!-- svelte-ignore a11y_label_has_associated_control -->
		<label class="block text-sm font-medium text-muted-foreground">Duration</label>
		<div class="mt-1 flex items-center gap-2">
			<input
				type="number"
				min="0"
				max="23"
				bind:value={hours}
				class="w-20 rounded-md border border-border bg-background px-3 py-2 text-sm text-center focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
			/>
			<span class="text-sm text-muted-foreground">h</span>
			<input
				type="number"
				min="0"
				max="59"
				bind:value={minutes}
				class="w-20 rounded-md border border-border bg-background px-3 py-2 text-sm text-center focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
			/>
			<span class="text-sm text-muted-foreground">m</span>
			{#if totalMinutes > 0}
				<span class="text-xs text-muted-foreground">= {totalMinutes} min</span>
			{/if}
		</div>
	</div>

	<div>
		<label for="me-start" class="block text-sm font-medium text-muted-foreground">
			Start time
			<span class="ml-1 text-xs font-normal italic text-muted-foreground/70">
				optional — leave blank to infer placement
			</span>
		</label>
		<div class="mt-1 flex items-center gap-2">
			<input
				id="me-start"
				type="time"
				bind:value={startTime}
				class="w-40 rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
			/>
			{#if startTime}
				<button
					type="button"
					onclick={() => (startTime = '')}
					class="text-xs text-muted-foreground hover:text-foreground"
					title="Clear start time"
				>
					Clear
				</button>
			{/if}
		</div>
	</div>

	<div>
		<label for="me-desc" class="block text-sm font-medium text-muted-foreground">Description</label>
		<textarea
			id="me-desc"
			bind:value={description}
			placeholder="What did you work on?"
			rows="2"
			class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
		></textarea>
	</div>

	<div>
		<label for="me-loc" class="block text-sm font-medium text-muted-foreground">Location</label>
		<input
			id="me-loc"
			type="text"
			bind:value={location}
			placeholder="e.g., Home, Library, Lab"
			class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
		/>
	</div>

	{#if planItemId}
		<label class="flex items-center gap-2 text-sm">
			<input type="checkbox" bind:checked={markComplete} class="h-4 w-4 rounded border-border text-primary focus:ring-primary" />
			Mark plan complete
		</label>
	{/if}

	<button
		onclick={handleSubmit}
		disabled={!isValid || saving}
		class="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
	>
		{saving ? 'Logging...' : 'Log Entry'}
	</button>
</div>
