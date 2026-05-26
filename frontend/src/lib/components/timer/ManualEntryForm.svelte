<script lang="ts">
	import type { CategoryResponse } from '$lib/api/client';
	import { api } from '$lib/api/client';
	import LateNightDatePrompt from './LateNightDatePrompt.svelte';
	import { formatLocalYMD, isLateNight, lateNightDateOptions } from '$lib/utils/lateNight';
	import { manualEntryDraft, resetManualEntryDraft } from '$lib/stores/drafts';
	import { onMount } from 'svelte';

	let {
		categories,
		onCreated
	}: {
		categories: CategoryResponse[];
		onCreated: () => void;
	} = $props();

	// Local copies of the draft fields. We read once on mount and write back
	// to the store via $effect so the draft survives page navigation.
	let categoryId = $state<number | null>(null);
	let date = $state(
		isLateNight() ? lateNightDateOptions().yesterday : formatLocalYMD(new Date())
	);
	let hours = $state(0);
	let minutes = $state(0);
	let description = $state('');
	let location = $state('');
	let error = $state('');
	let saving = $state(false);

	onMount(() => {
		const unsub = manualEntryDraft.subscribe((d) => {
			// Only initialise from store on first mount — after that we own the values.
			if (d.date) {
				date = d.date;
				categoryId = d.categoryId;
				hours = d.hours;
				minutes = d.minutes;
				description = d.description;
				location = d.location;
			}
		});
		unsub();
	});

	// Persist any local change back to the store so a tab-switch preserves it.
	$effect(() => {
		manualEntryDraft.set({ categoryId, date, hours, minutes, description, location });
	});

	const totalMinutes = $derived(hours * 60 + minutes);
	const isValid = $derived(categoryId !== null && totalMinutes > 0);

	async function handleSubmit() {
		if (!isValid || !categoryId) return;
		error = '';
		saving = true;
		try {
			await api.createManualEntry({
				category_id: categoryId,
				date,
				duration_minutes: totalMinutes,
				description: description || undefined,
				location: location || undefined
			});
			// Reset form + clear the persisted draft (it was for this entry).
			categoryId = null;
			hours = 0;
			minutes = 0;
			description = '';
			location = '';
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

	<LateNightDatePrompt bind:value={date} />

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

	<button
		onclick={handleSubmit}
		disabled={!isValid || saving}
		class="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
	>
		{saving ? 'Logging...' : 'Log Entry'}
	</button>
</div>
