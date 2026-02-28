<script lang="ts">
	import type { TimerEntryResponse, ManualEntryResponse, ObservationResponse } from '$lib/api/client';

	let {
		timerEntries,
		manualEntries,
		observations = [],
		onDeleteManual,
		onDeleteTimer
	}: {
		timerEntries: TimerEntryResponse[];
		manualEntries: ManualEntryResponse[];
		observations?: ObservationResponse[];
		onDeleteManual: (id: number) => void;
		onDeleteTimer: (id: number) => void;
	} = $props();

	interface LogItem {
		type: 'timer' | 'manual' | 'import';
		id: number;
		category: string | null;
		minutes: number;
		description: string | null;
		time: string;
	}

	const items: LogItem[] = $derived.by(() => {
		const all: LogItem[] = [];
		for (const t of timerEntries) {
			all.push({
				type: 'timer',
				id: t.id,
				category: t.category_name,
				minutes: t.duration_minutes || 0,
				description: t.description,
				time: t.end_time ? new Date(t.end_time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '',
			});
		}
		for (const m of manualEntries) {
			all.push({
				type: 'manual',
				id: m.id,
				category: m.category_name,
				minutes: m.duration_minutes,
				description: m.description,
				time: m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '',
			});
		}
		for (const o of observations) {
			all.push({
				type: 'import',
				id: o.id,
				category: o.category_name,
				minutes: o.minutes,
				description: null,
				time: '',
			});
		}
		return all;
	});

	function formatDuration(min: number): string {
		const h = Math.floor(min / 60);
		const m = min % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	function truncate(s: string | null, max: number): string {
		if (!s) return '';
		return s.length > max ? s.slice(0, max) + '...' : s;
	}
</script>

{#if items.length === 0}
	<div class="py-6 text-center text-sm text-muted-foreground">
		No entries logged today yet
	</div>
{:else}
	<div class="rounded-lg border border-border">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-border bg-muted/50">
					<th class="px-3 py-2 text-left font-medium text-muted-foreground">Time</th>
					<th class="px-3 py-2 text-left font-medium text-muted-foreground">Src</th>
					<th class="px-3 py-2 text-left font-medium text-muted-foreground">Category</th>
					<th class="px-3 py-2 text-right font-medium text-muted-foreground">Duration</th>
					<th class="px-3 py-2 text-left font-medium text-muted-foreground">Description</th>
					<th class="px-3 py-2 text-right font-medium text-muted-foreground"></th>
				</tr>
			</thead>
			<tbody>
				{#each items as item}
					<tr class="border-b border-border last:border-0 hover:bg-muted/30">
						<td class="px-3 py-2 text-xs text-muted-foreground">{item.time}</td>
						<td class="px-3 py-2">
							<span class="inline-flex h-5 w-5 items-center justify-center rounded text-xs font-bold {
								item.type === 'timer'
									? 'bg-blue-500/10 text-blue-600'
									: item.type === 'manual'
										? 'bg-purple-500/10 text-purple-600'
										: 'bg-green-500/10 text-green-600'
							}">
								{item.type === 'timer' ? 'T' : item.type === 'manual' ? 'M' : 'I'}
							</span>
						</td>
						<td class="px-3 py-2 font-medium">{item.category || '—'}</td>
						<td class="px-3 py-2 text-right tabular-nums">{formatDuration(item.minutes)}</td>
						<td class="px-3 py-2 text-muted-foreground">{truncate(item.description, 40)}</td>
						<td class="px-3 py-2 text-right">
							{#if item.type === 'manual'}
								<button
									onclick={() => onDeleteManual(item.id)}
									class="rounded p-1 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600"
									title="Delete entry"
								>
									<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
										<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
									</svg>
								</button>
							{:else if item.type === 'timer'}
								<button
									onclick={() => onDeleteTimer(item.id)}
									class="rounded p-1 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600"
									title="Delete entry"
								>
									<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
										<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
									</svg>
								</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
