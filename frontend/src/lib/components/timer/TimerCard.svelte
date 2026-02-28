<script lang="ts">
	import type { TimerEntryResponse } from '$lib/api/client';
	import { computeElapsedSeconds, formatElapsed } from '$lib/stores/timer';

	let {
		timer,
		onPause,
		onResume,
		onStop,
		onDiscard,
		compact = false
	}: {
		timer: TimerEntryResponse;
		onPause: (id: number) => void;
		onResume: (id: number) => void;
		onStop: (id: number) => void;
		onDiscard?: (id: number) => void;
		compact?: boolean;
	} = $props();

	let elapsed = $state(0);

	$effect(() => {
		// Reset when timer prop changes
		elapsed = computeElapsedSeconds(timer);
		if (timer.is_paused) return;

		const interval = setInterval(() => {
			elapsed = computeElapsedSeconds(timer);
		}, 1000);
		return () => clearInterval(interval);
	});

	function formatStartTime(iso: string): string {
		return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}
</script>

<div class="rounded-lg border border-border bg-card p-4 {compact ? '' : 'space-y-3'}">
	<div class="flex items-center justify-between gap-3">
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<span class="font-medium truncate">{timer.category_name || 'Unknown'}</span>
				{#if timer.is_paused}
					<span class="inline-flex items-center rounded-full bg-yellow-500/10 px-2 py-0.5 text-xs font-medium text-yellow-600">
						PAUSED
					</span>
				{:else}
					<span class="inline-flex items-center rounded-full bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-600">
						RUNNING
					</span>
				{/if}
			</div>
			{#if !compact}
				<p class="mt-0.5 text-xs text-muted-foreground">
					Started at {formatStartTime(timer.start_time)}
				</p>
			{/if}
		</div>

		<div class="text-right">
			<div class="font-mono text-2xl font-bold tabular-nums {timer.is_paused ? 'text-yellow-600' : 'text-foreground'}">
				{formatElapsed(elapsed)}
			</div>
		</div>
	</div>

	{#if !compact}
		<div class="flex items-center gap-2 pt-1">
			{#if timer.is_paused}
				<button
					onclick={() => onResume(timer.id)}
					class="flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-green-700"
				>
					<svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
					Resume
				</button>
			{:else}
				<button
					onclick={() => onPause(timer.id)}
					class="flex items-center gap-1.5 rounded-md bg-yellow-500 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-yellow-600"
				>
					<svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
					Pause
				</button>
			{/if}

			<button
				onclick={() => onStop(timer.id)}
				class="flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-red-700"
			>
				<svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
				Stop
			</button>

			{#if onDiscard}
				<button
					onclick={() => onDiscard?.(timer.id)}
					class="ml-auto rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
				>
					Discard
				</button>
			{/if}
		</div>
	{:else}
		<!-- Compact: inline buttons -->
		<div class="flex items-center gap-1.5 shrink-0">
			{#if timer.is_paused}
				<button onclick={() => onResume(timer.id)} class="rounded p-1 text-green-600 hover:bg-green-500/10" title="Resume">
					<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
				</button>
			{:else}
				<button onclick={() => onPause(timer.id)} class="rounded p-1 text-yellow-500 hover:bg-yellow-500/10" title="Pause">
					<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
				</button>
			{/if}
			<button onclick={() => onStop(timer.id)} class="rounded p-1 text-red-600 hover:bg-red-500/10" title="Stop">
				<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
			</button>
		</div>
	{/if}
</div>
