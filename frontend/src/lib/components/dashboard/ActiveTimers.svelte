<script lang="ts">
	import type { TimerEntryResponse } from '$lib/api/client';
	import TimerCard from '$lib/components/timer/TimerCard.svelte';

	let {
		timers,
		onPause,
		onResume,
		onStop
	}: {
		timers: TimerEntryResponse[];
		onPause: (id: number) => void;
		onResume: (id: number) => void;
		onStop: (id: number) => void;
	} = $props();
</script>

<div>
	<h2 class="mb-3 text-lg font-semibold">Active Timers</h2>
	{#if timers.length === 0}
		<div class="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
			No active timers
		</div>
	{:else}
		<div class="space-y-2">
			{#each timers as timer (timer.id)}
				<TimerCard {timer} {onPause} {onResume} {onStop} compact />
			{/each}
		</div>
	{/if}
</div>
