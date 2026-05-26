<script lang="ts">
	import { isLateNight, lateNightDateOptions, shortDateLabel } from '$lib/utils/lateNight';

	// Bindable selected date (YYYY-MM-DD). Parent controls the value.
	let {
		value = $bindable<string>(''),
		// Auto-default to "yesterday" when in the late-night window (the user
		// explicitly asked to be prompted because they tend to work past midnight).
		preferYesterday = true,
		// Override the "now" used for late-night detection — useful in tests
		// and when prompting for an existing entry's date, not "right now".
		nowOverride = null as Date | null,
	}: {
		value?: string;
		preferYesterday?: boolean;
		nowOverride?: Date | null;
	} = $props();

	const now = nowOverride ?? new Date();
	const showPrompt = isLateNight(now);
	const { today, yesterday } = lateNightDateOptions(now);

	// On first mount, set the default if value is empty.
	$effect(() => {
		if (!value) {
			value = preferYesterday && showPrompt ? yesterday : today;
		}
	});
</script>

{#if showPrompt}
	<div class="rounded-lg border border-amber-300/50 bg-amber-50/60 dark:bg-amber-950/20 dark:border-amber-700/30 p-3">
		<div class="flex items-start gap-2.5">
			<svg class="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
			</svg>
			<div class="flex-1 min-w-0">
				<div class="text-xs font-medium">Working past midnight — which date does this belong to?</div>
				<div class="mt-2 flex flex-wrap gap-2">
					<label class="flex-1 cursor-pointer">
						<input
							type="radio"
							bind:group={value}
							value={yesterday}
							class="peer sr-only"
						/>
						<div class="rounded-md border border-border bg-background px-3 py-1.5 text-center text-sm transition-colors peer-checked:border-amber-500 peer-checked:bg-amber-100 peer-checked:text-amber-900 dark:peer-checked:bg-amber-900/40 dark:peer-checked:text-amber-100">
							<div class="text-[10px] uppercase tracking-wider text-muted-foreground peer-checked:text-current">Yesterday</div>
							<div class="font-medium">{shortDateLabel(yesterday)}</div>
						</div>
					</label>
					<label class="flex-1 cursor-pointer">
						<input
							type="radio"
							bind:group={value}
							value={today}
							class="peer sr-only"
						/>
						<div class="rounded-md border border-border bg-background px-3 py-1.5 text-center text-sm transition-colors peer-checked:border-amber-500 peer-checked:bg-amber-100 peer-checked:text-amber-900 dark:peer-checked:bg-amber-900/40 dark:peer-checked:text-amber-100">
							<div class="text-[10px] uppercase tracking-wider text-muted-foreground peer-checked:text-current">Today</div>
							<div class="font-medium">{shortDateLabel(today)}</div>
						</div>
					</label>
				</div>
			</div>
		</div>
	</div>
{/if}
