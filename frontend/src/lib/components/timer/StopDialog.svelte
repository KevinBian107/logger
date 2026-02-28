<script lang="ts">
	import type { TimerEntryResponse } from '$lib/api/client';
	import { computeElapsedSeconds } from '$lib/stores/timer';

	let {
		timer,
		onSave,
		onDiscard,
		onCancel
	}: {
		timer: TimerEntryResponse;
		onSave: (id: number, description: string, location: string) => void;
		onDiscard: (id: number) => void;
		onCancel: () => void;
	} = $props();

	let description = $state('');
	let location = $state('');

	const elapsed = $derived(computeElapsedSeconds(timer));
	const roundedMinutes = $derived(Math.max(1, Math.round(elapsed / 60)));

	function formatDuration(minutes: number): string {
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onCancel();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Backdrop -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onclick={onCancel} onkeydown={handleKeydown}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="mx-4 w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-lg" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<h2 class="text-lg font-semibold">Stop Timer</h2>

		<div class="mt-4 rounded-lg bg-muted p-3">
			<div class="flex items-center justify-between">
				<span class="font-medium">{timer.category_name}</span>
				<span class="font-mono text-lg font-bold tabular-nums">{formatDuration(roundedMinutes)}</span>
			</div>
		</div>

		<div class="mt-4 space-y-3">
			<div>
				<label for="stop-desc" class="block text-sm font-medium text-muted-foreground">Description</label>
				<textarea
					id="stop-desc"
					bind:value={description}
					placeholder="What did you work on?"
					rows="3"
					class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				></textarea>
			</div>
			<div>
				<label for="stop-loc" class="block text-sm font-medium text-muted-foreground">Location</label>
				<input
					id="stop-loc"
					type="text"
					bind:value={location}
					placeholder="e.g., Home, Library, Lab"
					class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
				/>
			</div>
		</div>

		<div class="mt-6 flex justify-between">
			<button
				onclick={() => onDiscard(timer.id)}
				class="rounded-md px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-500/10"
			>
				Discard
			</button>
			<div class="flex gap-3">
				<button
					onclick={onCancel}
					class="rounded-md px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted"
				>
					Cancel
				</button>
				<button
					onclick={() => onSave(timer.id, description, location)}
					class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/90"
				>
					Save & Log
				</button>
			</div>
		</div>
	</div>
</div>
