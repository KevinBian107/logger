<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type TimerEntryResponse,
		type ManualEntryResponse,
		type CategoryResponse,
	} from '$lib/api/client';
	import LateNightDatePrompt from './LateNightDatePrompt.svelte';
	import { shortDateLabel } from '$lib/utils/lateNight';

	// One of these will be set depending on entry type
	let {
		timerEntry = null,
		manualEntry = null,
		sessionId,
		onSaved,
		onDeleted,
		onCancel,
	}: {
		timerEntry?: TimerEntryResponse | null;
		manualEntry?: ManualEntryResponse | null;
		sessionId: number;
		onSaved: () => void;
		onDeleted: (id: number, kind: 'timer' | 'manual') => void;
		onCancel: () => void;
	} = $props();

	const entry = timerEntry || manualEntry;
	const kind: 'timer' | 'manual' = timerEntry ? 'timer' : 'manual';

	let categories = $state<CategoryResponse[]>([]);
	let categoryId = $state<number>(entry?.category_id ?? 0);
	let date = $state<string>(entry?.date ?? '');
	let durationMinutes = $state<number>(entry?.duration_minutes ?? 0);
	let description = $state<string>(entry?.description ?? '');
	let location = $state<string>(entry?.location ?? '');

	let saving = $state(false);
	let deleting = $state(false);
	let confirmDelete = $state(false);
	let error = $state('');

	async function loadCategories() {
		try {
			categories = await api.getCategories(sessionId);
		} catch (e) {
			console.error('Failed to load categories', e);
		}
	}

	async function handleSave() {
		if (!entry) return;
		saving = true;
		error = '';
		try {
			const patch = {
				category_id: categoryId,
				date,
				duration_minutes: durationMinutes,
				description: description || null,
				location: location || null,
			};
			if (kind === 'timer') {
				await api.updateTimer(entry.id, patch);
			} else {
				await api.updateManualEntry(entry.id, patch);
			}
			onSaved();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Save failed';
		} finally {
			saving = false;
		}
	}

	async function handleDelete() {
		if (!entry) return;
		deleting = true;
		error = '';
		try {
			if (kind === 'timer') {
				await api.discardTimer(entry.id);
			} else {
				await api.deleteManualEntry(entry.id);
			}
			onDeleted(entry.id, kind);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Delete failed';
		} finally {
			deleting = false;
		}
	}

	function handleBackdrop(e: MouseEvent) {
		if (e.target === e.currentTarget) onCancel();
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape') onCancel();
	}

	onMount(loadCategories);
</script>

<svelte:window on:keydown={handleKey} />

<div
	role="presentation"
	onclick={handleBackdrop}
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
>
	<div class="w-full max-w-md rounded-xl border border-border bg-card shadow-2xl">
		<div class="flex items-center justify-between border-b border-border px-5 py-3">
			<div>
				<h3 class="text-base font-semibold">Edit {kind === 'timer' ? 'timer' : 'manual'} entry</h3>
				<p class="mt-0.5 text-xs text-muted-foreground">
					Originally logged for <span class="font-mono">{entry?.date ? shortDateLabel(entry.date) : '?'}</span>
				</p>
			</div>
			<button
				onclick={onCancel}
				class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
				aria-label="Close"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
				</svg>
			</button>
		</div>

		<div class="space-y-3.5 px-5 py-4">
			<!-- Category -->
			<div>
				<label class="block text-xs font-medium text-muted-foreground mb-1" for="edit-cat">Category</label>
				<select
					id="edit-cat"
					bind:value={categoryId}
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
				>
					{#each categories as cat}
						<option value={cat.id}>{cat.display_name || cat.name}</option>
					{/each}
				</select>
			</div>

			<!-- Date + duration row -->
			<div class="grid grid-cols-2 gap-3">
				<div>
					<label class="block text-xs font-medium text-muted-foreground mb-1" for="edit-date">Date</label>
					<input
						id="edit-date"
						type="date"
						bind:value={date}
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
					/>
				</div>
				<div>
					<label class="block text-xs font-medium text-muted-foreground mb-1" for="edit-duration">Duration (min)</label>
					<input
						id="edit-duration"
						type="number"
						min="1"
						bind:value={durationMinutes}
						class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
					/>
				</div>
			</div>

			<!-- Late-night date prompt — only renders if local time is 0-5am.
			     Setting `value` here lets the prompt override the date input above
			     when the user picks "yesterday". -->
			<LateNightDatePrompt bind:value={date} />

			<!-- Description -->
			<div>
				<label class="block text-xs font-medium text-muted-foreground mb-1" for="edit-desc">Description</label>
				<textarea
					id="edit-desc"
					bind:value={description}
					rows="2"
					placeholder="What did you work on?"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
				></textarea>
			</div>

			<!-- Location -->
			<div>
				<label class="block text-xs font-medium text-muted-foreground mb-1" for="edit-loc">Location</label>
				<input
					id="edit-loc"
					type="text"
					bind:value={location}
					placeholder="Optional"
					class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
				/>
			</div>

			{#if error}
				<p class="text-xs text-destructive">{error}</p>
			{/if}
		</div>

		<div class="flex items-center justify-between border-t border-border px-5 py-3">
			{#if confirmDelete}
				<div class="flex items-center gap-2">
					<span class="text-xs text-destructive">Delete this entry?</span>
					<button
						onclick={handleDelete}
						disabled={deleting}
						class="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
					>
						{deleting ? 'Deleting…' : 'Yes, delete'}
					</button>
					<button
						onclick={() => (confirmDelete = false)}
						class="text-xs text-muted-foreground hover:text-foreground"
					>
						No
					</button>
				</div>
			{:else}
				<button
					onclick={() => (confirmDelete = true)}
					class="text-xs text-destructive hover:underline"
				>
					Delete entry
				</button>
			{/if}
			<div class="flex items-center gap-2">
				<button
					onclick={onCancel}
					class="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
				>
					Cancel
				</button>
				<button
					onclick={handleSave}
					disabled={saving || !date || durationMinutes < 1}
					class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
				>
					{saving ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
</div>
