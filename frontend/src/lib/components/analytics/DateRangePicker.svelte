<script lang="ts">
	/**
	 * Date RANGE picker for the analytics Range scale.
	 *
	 * Visually the Recorder's DatePicker (same pill trigger, same popover, same
	 * cell treatment), but selection is a span: click a start date, then an end
	 * date. The pending span follows the cursor so you can see what you're about
	 * to select, both ends light up in the primary color, and the days between
	 * carry a lighter tint. Clicking the same day twice is a single-day range.
	 */
	import { shortDateLabel, addDaysYMD } from '$lib/utils/lateNight';
	import { todayYMD } from '$lib/stores/clock';
	import { api } from '$lib/api/client';

	let {
		from = $bindable<string>(''),
		to = $bindable<string>(''),
		// Upper bound; empty tracks the live "today" so future days stay disabled.
		maxDate = '',
		onChange = undefined,
	}: {
		from?: string;
		to?: string;
		maxDate?: string;
		onChange?: (from: string, to: string) => void;
	} = $props();

	const max = $derived(maxDate || $todayYMD);

	let open = $state(false);
	let viewYear = $state<number>(0);
	let viewMonth = $state<number>(0); // 0-indexed

	// The first click of an in-progress selection; null when nothing is pending.
	let pendingStart = $state<string | null>(null);
	let hovered = $state<string | null>(null);

	function ymdToDate(ymd: string): Date {
		const [y, m, d] = ymd.split('-').map(Number);
		return new Date(y, m - 1, d);
	}

	// Open on the month of the current start, and always start a fresh selection.
	$effect(() => {
		if (open) {
			const d = ymdToDate(from || $todayYMD);
			viewYear = d.getFullYear();
			viewMonth = d.getMonth();
			pendingStart = null;
			hovered = null;
		}
	});

	// What the grid should paint: the pending span while picking, else the
	// committed range. YYYY-MM-DD compares lexicographically = chronologically.
	const shown = $derived.by<[string, string]>(() => {
		if (pendingStart) {
			const other = hovered ?? pendingStart;
			return pendingStart <= other ? [pendingStart, other] : [other, pendingStart];
		}
		return [from, to];
	});

	const cells = $derived.by(() => {
		const firstOfMonth = new Date(viewYear, viewMonth, 1);
		const startWeekday = firstOfMonth.getDay(); // 0 = Sun
		const start = new Date(viewYear, viewMonth, 1 - startWeekday);
		const pad = (n: number) => String(n).padStart(2, '0');
		const out: { ymd: string; day: number; inMonth: boolean; future: boolean }[] = [];
		for (let i = 0; i < 42; i++) {
			const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
			const ymd = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
			out.push({
				ymd,
				day: d.getDate(),
				inMonth: d.getMonth() === viewMonth,
				future: ymd > max,
			});
		}
		return out;
	});

	const monthLabel = $derived(
		new Date(viewYear, viewMonth, 1).toLocaleDateString(undefined, {
			month: 'long',
			year: 'numeric',
		}),
	);

	// Break days in the visible month, same as the Recorder's picker.
	let breaksByDate = $state<Map<string, string | null>>(new Map());

	$effect(() => {
		if (!open) return;
		const c = cells;
		const start = c[0]?.ymd;
		const end = c[c.length - 1]?.ymd;
		if (!start || !end) return;
		api.getBreaks(start, end)
			.then((rows) => {
				const m = new Map<string, string | null>();
				for (const b of rows) m.set(b.date, b.label);
				breaksByDate = m;
			})
			.catch(() => {});
	});

	function dayCount(a: string, b: string): number {
		if (!a || !b) return 0;
		return Math.round((ymdToDate(b).getTime() - ymdToDate(a).getTime()) / 86400000) + 1;
	}

	const triggerLabel = $derived.by(() => {
		if (!from || !to) return 'Pick a range';
		if (from === to) return shortDateLabel(from);
		const sameYear = from.slice(0, 4) === to.slice(0, 4);
		const fmt = (ymd: string) =>
			ymdToDate(ymd).toLocaleDateString(undefined, {
				month: 'short',
				day: 'numeric',
				...(sameYear ? {} : { year: '2-digit' }),
			});
		return `${fmt(from)} – ${fmt(to)}`;
	});

	function prevMonth() {
		if (viewMonth === 0) {
			viewMonth = 11;
			viewYear--;
		} else {
			viewMonth--;
		}
	}
	function nextMonth() {
		if (viewMonth === 11) {
			viewMonth = 0;
			viewYear++;
		} else {
			viewMonth++;
		}
	}

	function pick(ymd: string, future: boolean) {
		if (future) return;
		if (!pendingStart) {
			// First click: anchor the span and wait for the other end.
			pendingStart = ymd;
			hovered = ymd;
			return;
		}
		const a = pendingStart;
		apply(a <= ymd ? a : ymd, a <= ymd ? ymd : a);
	}

	function apply(start: string, end: string) {
		pendingStart = null;
		hovered = null;
		from = start;
		to = end;
		open = false;
		onChange?.(start, end);
	}

	function preset(days: number | 'month') {
		const today = $todayYMD;
		if (days === 'month') {
			apply(`${today.slice(0, 7)}-01`, today);
		} else {
			apply(addDaysYMD(today, -(days - 1)), today);
		}
	}

	function onWindowClick(e: MouseEvent) {
		if (!open) return;
		const target = e.target as HTMLElement;
		if (!target.closest('.rangepicker-root')) open = false;
	}
</script>

<svelte:window onclick={onWindowClick} />

<div class="rangepicker-root relative inline-block">
	<button
		type="button"
		onclick={(e) => {
			e.stopPropagation();
			open = !open;
		}}
		class="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-sm transition-colors hover:border-primary/40 hover:bg-card/80"
	>
		<svg class="h-3.5 w-3.5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5a2.25 2.25 0 012.25 2.25v7.5"/>
		</svg>
		<span class="font-medium">{triggerLabel}</span>
		{#if from && to && from !== to}
			<span class="text-xs text-muted-foreground">{dayCount(from, to)}d</span>
		{/if}
		<svg class="h-3 w-3 text-muted-foreground transition-transform {open ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
			<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>
		</svg>
	</button>

	{#if open}
		<div
			class="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-border bg-card shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => { if (e.key === 'Escape') open = false; }}
			role="dialog"
			tabindex="-1"
			aria-label="Pick a date range"
		>
			<!-- Header: month nav -->
			<div class="flex items-center justify-between border-b border-border px-3 py-2">
				<button
					type="button"
					onclick={prevMonth}
					aria-label="Previous month"
					class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5"/></svg>
				</button>
				<span class="text-sm font-semibold">{monthLabel}</span>
				<button
					type="button"
					onclick={nextMonth}
					aria-label="Next month"
					class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
				</button>
			</div>

			<!-- Weekday header -->
			<div class="grid grid-cols-7 px-2 pt-2 text-center text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
				{#each ['S','M','T','W','T','F','S'] as wd}<span>{wd}</span>{/each}
			</div>

			<!-- Day grid -->
			<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
			<div
				class="grid grid-cols-7 gap-0.5 px-2 pb-2 pt-1"
				role="grid"
				tabindex="-1"
				onmouseleave={() => { if (pendingStart) hovered = pendingStart; }}
			>
				{#each cells as c}
					{@const isBreak = breaksByDate.has(c.ymd)}
					{@const isStart = !!shown[0] && c.ymd === shown[0]}
					{@const isEnd = !!shown[1] && c.ymd === shown[1]}
					{@const inRange = !!shown[0] && !!shown[1] && c.ymd > shown[0] && c.ymd < shown[1]}
					<button
						type="button"
						onclick={() => pick(c.ymd, c.future)}
						onmouseenter={() => { if (pendingStart && !c.future) hovered = c.ymd; }}
						disabled={c.future}
						title={isBreak ? (breaksByDate.get(c.ymd) || 'Break') : undefined}
						class="relative aspect-square w-full rounded-md text-xs transition-colors
							{isStart || isEnd
								? 'bg-primary font-semibold text-primary-foreground'
								: inRange
									? 'bg-primary/20 font-medium text-foreground hover:bg-primary/30'
									: isBreak
										? 'bg-amber-500/15 font-medium text-amber-700 hover:bg-amber-500/25 dark:text-amber-400'
										: c.ymd === $todayYMD
											? 'bg-primary/10 font-semibold text-primary hover:bg-primary/20'
											: c.inMonth
												? 'text-foreground hover:bg-muted'
												: 'text-muted-foreground/40 hover:bg-muted/50'}
							{c.future ? 'cursor-not-allowed opacity-30 hover:bg-transparent' : ''}"
					>
						{c.day}
						{#if isBreak}
							<span class="pointer-events-none absolute -top-0.5 -right-0.5 text-[9px] leading-none">🌴</span>
						{/if}
					</button>
				{/each}
			</div>

			<!-- Status line: what's selected, or what to click next -->
			<div class="border-t border-border px-3 py-1.5 text-center text-[11px] text-muted-foreground">
				{#if pendingStart}
					Now pick the end date — {dayCount(shown[0], shown[1])} day{dayCount(shown[0], shown[1]) === 1 ? '' : 's'}
				{:else if from && to}
					{dayCount(from, to)} day{dayCount(from, to) === 1 ? '' : 's'} selected
				{:else}
					Click a start date, then an end date
				{/if}
			</div>

			<!-- Quick ranges -->
			<div class="grid grid-cols-4 gap-1.5 border-t border-border px-3 py-2">
				<button
					type="button"
					onclick={() => preset(1)}
					class="rounded-md border border-border bg-background px-1 py-1.5 text-[11px] font-medium transition-colors hover:border-primary hover:text-primary"
				>
					Today
				</button>
				<button
					type="button"
					onclick={() => preset(7)}
					class="rounded-md border border-border bg-background px-1 py-1.5 text-[11px] font-medium transition-colors hover:border-primary hover:text-primary"
				>
					7d
				</button>
				<button
					type="button"
					onclick={() => preset(30)}
					class="rounded-md border border-border bg-background px-1 py-1.5 text-[11px] font-medium transition-colors hover:border-primary hover:text-primary"
				>
					30d
				</button>
				<button
					type="button"
					onclick={() => preset('month')}
					class="rounded-md border border-border bg-background px-1 py-1.5 text-[11px] font-medium transition-colors hover:border-primary hover:text-primary"
				>
					Month
				</button>
			</div>
		</div>
	{/if}
</div>
