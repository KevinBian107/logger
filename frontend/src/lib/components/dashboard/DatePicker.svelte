<script lang="ts">
	import { formatLocalYMD, shortDateLabel } from '$lib/utils/lateNight';
	import { api } from '$lib/api/client';

	// Bound YYYY-MM-DD string. Parent owns it.
	let {
		value = $bindable<string>(formatLocalYMD(new Date())),
		// Optional bound for "future" — defaults to "today" so users can't pick days
		// that don't have data yet.
		maxDate = formatLocalYMD(new Date()),
	}: {
		value?: string;
		maxDate?: string;
	} = $props();

	let open = $state(false);

	// Month being viewed in the picker (may differ from selected value while browsing).
	let viewYear = $state<number>(0);
	let viewMonth = $state<number>(0); // 0-indexed

	function ymdToDate(ymd: string): Date {
		const [y, m, d] = ymd.split('-').map(Number);
		return new Date(y, m - 1, d);
	}

	// Initialise the view to the selected month whenever the picker opens.
	$effect(() => {
		if (open) {
			const d = ymdToDate(value);
			viewYear = d.getFullYear();
			viewMonth = d.getMonth();
		}
	});

	const todayYMD = formatLocalYMD(new Date());

	// Day cells for the visible month grid (always 42 cells = 6 rows × 7 cols).
	const cells = $derived.by(() => {
		const firstOfMonth = new Date(viewYear, viewMonth, 1);
		const startWeekday = firstOfMonth.getDay(); // 0 = Sun
		const start = new Date(viewYear, viewMonth, 1 - startWeekday);
		const out: { ymd: string; day: number; inMonth: boolean; future: boolean }[] = [];
		for (let i = 0; i < 42; i++) {
			const d = new Date(start);
			d.setDate(start.getDate() + i);
			const ymd = formatLocalYMD(d);
			out.push({
				ymd,
				day: d.getDate(),
				inMonth: d.getMonth() === viewMonth,
				future: ymd > maxDate,
			});
		}
		return out;
	});

	const monthLabel = $derived(
		new Date(viewYear, viewMonth, 1).toLocaleDateString(undefined, {
			month: 'long',
			year: 'numeric',
		})
	);

	// Break days visible in the current month grid, keyed by YYYY-MM-DD → label
	// (label may be null for an unlabeled break). Re-fetched whenever the popover
	// is open and the visible month changes — closed, it's not worth the request.
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
		value = ymd;
		open = false;
	}

	function jumpToday() {
		value = todayYMD;
		open = false;
	}

	function jumpYesterday() {
		const y = new Date();
		y.setDate(y.getDate() - 1);
		value = formatLocalYMD(y);
		open = false;
	}

	// Close popover on outside click. The button itself is excluded via stopPropagation.
	function onWindowClick(e: MouseEvent) {
		if (!open) return;
		const target = e.target as HTMLElement;
		if (!target.closest('.datepicker-root')) open = false;
	}
</script>

<svelte:window onclick={onWindowClick} />

<div class="datepicker-root relative inline-block">
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
		<span class="font-medium">{shortDateLabel(value)}</span>
		<svg class="h-3 w-3 text-muted-foreground transition-transform {open ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
			<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>
		</svg>
	</button>

	{#if open}
		<div
			class="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-border bg-card shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			role="dialog"
			aria-label="Pick a date"
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
			<div class="grid grid-cols-7 gap-0.5 px-2 pb-2 pt-1">
				{#each cells as c}
					{@const isBreak = breaksByDate.has(c.ymd)}
					<button
						type="button"
						onclick={() => pick(c.ymd, c.future)}
						disabled={c.future}
						title={isBreak ? (breaksByDate.get(c.ymd) || 'Break') : undefined}
						class="relative aspect-square w-full rounded-md text-xs transition-colors
							{c.ymd === value
								? 'bg-primary text-primary-foreground font-semibold'
								: isBreak
									? 'bg-amber-500/15 font-medium text-amber-700 hover:bg-amber-500/25 dark:text-amber-400'
									: c.ymd === todayYMD
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

			<!-- Quick jumps -->
			<div class="flex gap-1.5 border-t border-border px-3 py-2">
				<button
					type="button"
					onclick={jumpToday}
					class="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs font-medium transition-colors hover:border-primary hover:text-primary"
				>
					Today
				</button>
				<button
					type="button"
					onclick={jumpYesterday}
					class="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs font-medium transition-colors hover:border-primary hover:text-primary"
				>
					Yesterday
				</button>
			</div>
		</div>
	{/if}
</div>
