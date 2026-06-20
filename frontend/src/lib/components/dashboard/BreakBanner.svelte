<script lang="ts">
	import { shortDateLabel } from '$lib/utils/lateNight';

	let {
		label = null,
		date,
		viewingToday = false,
	}: {
		label?: string | null;
		date: string;
		viewingToday?: boolean;
	} = $props();
</script>

<div class="flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
	<span class="text-2xl leading-none">🌴</span>
	<div class="min-w-0">
		<p class="text-sm font-semibold text-amber-700 dark:text-amber-400">
			{label || 'Break'}{viewingToday ? ' — today' : ` — ${shortDateLabel(date)}`}
		</p>
		<p class="text-xs text-muted-foreground">
			Marked as a rest day. It doesn't count toward your time and won't break your streak.
		</p>
	</div>
</div>
