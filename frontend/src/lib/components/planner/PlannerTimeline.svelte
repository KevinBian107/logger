<script lang="ts">
	/**
	 * Notion-style horizontal timeline: day columns on the x-axis, plan items as
	 * draggable/resizable bars stacked into lanes when they overlap. All API
	 * calls live in the parent (routes/planner/+page.svelte) — this component
	 * only computes layout and emits intent (onCreate / onDatesChange / onSelect
	 * / onPan), mirroring how TodayTimeline stays presentational and the page
	 * component owns data loading elsewhere in this app.
	 */
	import { onMount } from 'svelte';
	import type { CategoryResponse, PlanItemResponse } from '$lib/api/client';
	import { colorForCategory } from '$lib/utils/chart';
	import { formatLocalYMD } from '$lib/utils/lateNight';

	let {
		items,
		categories,
		windowStart,
		windowEnd,
		onCreate,
		onDatesChange,
		onSelect,
		onPan,
	}: {
		items: PlanItemResponse[];
		categories: CategoryResponse[];
		windowStart: string;
		windowEnd: string;
		onCreate: (data: { title: string; category_id: number; start_date: string; end_date: string }) => void | Promise<void>;
		onDatesChange: (id: number, start_date: string, end_date: string) => void | Promise<void>;
		onSelect: (id: number) => void;
		onPan: (direction: 'prev' | 'next' | 'today') => void;
	} = $props();

	const DAY_WIDTH = 64;
	const ROW_HEIGHT = 34;
	const ROW_GAP = 10;
	const HEADER_HEIGHT = 64;

	const todayYmd = formatLocalYMD(new Date());

	function ymdToDate(ymd: string): Date {
		const [y, m, d] = ymd.split('-').map(Number);
		return new Date(y, m - 1, d);
	}
	function dateToYmd(d: Date): string {
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}
	function addDays(d: Date, n: number): Date {
		return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
	}

	type DayCol = { ymd: string; dayNum: number; weekday: string; isToday: boolean; isWeekend: boolean; showMonth: string | null };

	const days = $derived.by<DayCol[]>(() => {
		const out: DayCol[] = [];
		const end = ymdToDate(windowEnd);
		let d = ymdToDate(windowStart);
		while (d <= end) {
			const ymd = dateToYmd(d);
			out.push({
				ymd,
				dayNum: d.getDate(),
				weekday: d.toLocaleDateString(undefined, { weekday: 'narrow' }),
				isToday: ymd === todayYmd,
				isWeekend: d.getDay() === 0 || d.getDay() === 6,
				showMonth: d.getDate() === 1 || dateToYmd(d) === windowStart
					? d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
					: null,
			});
			d = addDays(d, 1);
		}
		return out;
	});

	function dayIndex(ymd: string): number {
		return Math.round((ymdToDate(ymd).getTime() - ymdToDate(windowStart).getTime()) / 86_400_000);
	}

	const contentWidth = $derived(days.length * DAY_WIDTH);

	// ── Lane packing (greedy interval scheduling, same idea as TodayTimeline's
	// event-laning but keyed on whole-day indices instead of hour floats) ────
	type LanedItem = { item: PlanItemResponse; startIdx: number; endIdx: number; lane: number };

	const laned = $derived.by<LanedItem[]>(() => {
		const raw = items
			.map((item) => ({ item, startIdx: dayIndex(item.start_date), endIdx: dayIndex(item.end_date) }))
			.filter((x) => x.endIdx >= 0 && x.startIdx < days.length)
			.sort((a, b) => a.startIdx - b.startIdx);

		const laneEnds: number[] = [];
		const out: LanedItem[] = [];
		for (const e of raw) {
			let assigned = -1;
			for (let i = 0; i < laneEnds.length; i++) {
				if (laneEnds[i] <= e.startIdx) {
					assigned = i;
					laneEnds[i] = e.endIdx + 1;
					break;
				}
			}
			if (assigned < 0) {
				laneEnds.push(e.endIdx + 1);
				assigned = laneEnds.length - 1;
			}
			out.push({ ...e, lane: assigned });
		}
		return out;
	});

	const laneCount = $derived(laned.length === 0 ? 0 : Math.max(...laned.map((l) => l.lane + 1)));
	// Floored by the scroll viewport's own visible height so the day-column
	// gridlines/weekend tint/today-guide always reach the bottom of the box,
	// even when there are few (or no) rows — otherwise they stop partway down
	// and the rest of the box reads as a dead, ungridded gap.
	let viewportHeight = $state(0);
	const contentHeight = $derived(
		Math.max(HEADER_HEIGHT + Math.max(laneCount, 4) * (ROW_HEIGHT + ROW_GAP), viewportHeight)
	);

	function laneY(lane: number): number {
		return HEADER_HEIGHT + lane * (ROW_HEIGHT + ROW_GAP);
	}

	// ── Drag state: move / resize an existing item, or drag-create a new one ─
	type DragMode = 'move' | 'resize-left' | 'resize-right' | 'create';
	type Drag = {
		mode: DragMode;
		itemId?: number;
		lane?: number;
		origStartIdx: number;
		origEndIdx: number;
		pointerStartIdx: number;
		liveStartIdx: number;
		liveEndIdx: number;
		moved: boolean;
	};
	let drag = $state<Drag | null>(null);
	let scrollEl = $state<HTMLDivElement | null>(null);

	function clampIdx(idx: number): number {
		return Math.max(0, Math.min(days.length - 1, idx));
	}

	function xToDayIndex(clientX: number): number {
		if (!scrollEl) return 0;
		const rect = scrollEl.getBoundingClientRect();
		const x = clientX - rect.left + scrollEl.scrollLeft;
		return clampIdx(Math.floor(x / DAY_WIDTH));
	}

	function onBarPointerDown(e: PointerEvent, li: LanedItem) {
		e.stopPropagation();
		if (e.button !== 0) return;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		const idx = xToDayIndex(e.clientX);
		drag = {
			mode: 'move',
			itemId: li.item.id,
			lane: li.lane,
			origStartIdx: li.startIdx,
			origEndIdx: li.endIdx,
			pointerStartIdx: idx,
			liveStartIdx: li.startIdx,
			liveEndIdx: li.endIdx,
			moved: false,
		};
	}

	function onEdgePointerDown(e: PointerEvent, li: LanedItem, side: 'left' | 'right') {
		e.stopPropagation();
		if (e.button !== 0) return;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		const idx = xToDayIndex(e.clientX);
		drag = {
			mode: side === 'left' ? 'resize-left' : 'resize-right',
			itemId: li.item.id,
			lane: li.lane,
			origStartIdx: li.startIdx,
			origEndIdx: li.endIdx,
			pointerStartIdx: idx,
			liveStartIdx: li.startIdx,
			liveEndIdx: li.endIdx,
			moved: false,
		};
	}

	function onGridPointerDown(e: PointerEvent) {
		if (e.button !== 0) return;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		const idx = xToDayIndex(e.clientX);
		drag = {
			mode: 'create',
			origStartIdx: idx,
			origEndIdx: idx,
			pointerStartIdx: idx,
			liveStartIdx: idx,
			liveEndIdx: idx,
			moved: false,
		};
	}

	function onPointerMove(e: PointerEvent) {
		if (!drag) return;
		const idx = xToDayIndex(e.clientX);
		const delta = idx - drag.pointerStartIdx;

		if (drag.mode === 'move') {
			const span = drag.origEndIdx - drag.origStartIdx;
			const newStart = Math.max(0, Math.min(days.length - 1 - span, drag.origStartIdx + delta));
			drag = { ...drag, liveStartIdx: newStart, liveEndIdx: newStart + span, moved: drag.moved || delta !== 0 };
		} else if (drag.mode === 'resize-left') {
			const newStart = Math.max(0, Math.min(drag.origEndIdx, drag.origStartIdx + delta));
			drag = { ...drag, liveStartIdx: newStart, moved: drag.moved || delta !== 0 };
		} else if (drag.mode === 'resize-right') {
			const newEnd = Math.min(days.length - 1, Math.max(drag.origStartIdx, drag.origEndIdx + delta));
			drag = { ...drag, liveEndIdx: newEnd, moved: drag.moved || delta !== 0 };
		} else if (drag.mode === 'create') {
			drag = { ...drag, liveEndIdx: idx, moved: drag.moved || idx !== drag.origStartIdx };
		}
	}

	// Quick-create popover, opened at the end of a drag-to-create gesture.
	let quickCreate = $state<{ startDate: string; endDate: string; lane: number } | null>(null);
	let qcTitle = $state('');
	let qcCategoryId = $state<number | null>(null);
	let qcInput = $state<HTMLInputElement | null>(null);

	function openQuickCreate(startIdx: number, endIdx: number) {
		quickCreate = { startDate: days[startIdx].ymd, endDate: days[endIdx].ymd, lane: laneCount };
		qcTitle = '';
		qcCategoryId = categories[0]?.id ?? null;
		queueMicrotask(() => qcInput?.focus());
	}

	function closeQuickCreate() {
		quickCreate = null;
	}

	// "+ New" button: same popover as drag-create, defaulted to a single day on
	// today's column (or the first visible day if today is outside the window).
	function handleNewClick() {
		const idx = clampIdx(dayIndex(todayYmd));
		openQuickCreate(idx, idx);
	}

	async function submitQuickCreate() {
		if (!quickCreate || !qcCategoryId) return;
		await onCreate({
			title: qcTitle.trim() || 'Untitled',
			category_id: qcCategoryId,
			start_date: quickCreate.startDate,
			end_date: quickCreate.endDate,
		});
		closeQuickCreate();
	}

	function onPointerUp() {
		if (!drag) return;
		const d = drag;
		drag = null;

		if (d.mode === 'create') {
			const startIdx = Math.min(d.liveStartIdx, d.liveEndIdx);
			const endIdx = Math.max(d.liveStartIdx, d.liveEndIdx);
			openQuickCreate(startIdx, endIdx);
			return;
		}

		if (!d.moved) {
			if (d.itemId != null) onSelect(d.itemId);
			return;
		}
		if (d.itemId != null) {
			onDatesChange(d.itemId, days[d.liveStartIdx].ymd, days[d.liveEndIdx].ymd);
		}
	}

	function barStyle(li: LanedItem): string {
		const dragging = drag && drag.itemId === li.item.id;
		const startIdx = dragging ? drag!.liveStartIdx : li.startIdx;
		const endIdx = dragging ? drag!.liveEndIdx : li.endIdx;
		const x = startIdx * DAY_WIDTH;
		const w = (endIdx - startIdx + 1) * DAY_WIDTH - 4;
		const y = laneY(li.lane);
		return `left:${x + 2}px; top:${y}px; width:${Math.max(DAY_WIDTH - 4, w)}px; height:${ROW_HEIGHT}px;`;
	}

	function fmtMinutes(min: number): string {
		const h = Math.floor(min / 60);
		const m = min % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	onMount(() => {
		if (!scrollEl) return;
		const idx = dayIndex(todayYmd);
		if (idx >= 0 && idx < days.length) {
			scrollEl.scrollLeft = Math.max(0, idx * DAY_WIDTH - scrollEl.clientWidth / 3);
		}
	});
</script>

<svelte:window onpointermove={onPointerMove} onpointerup={onPointerUp} />

<div class="flex h-full flex-col rounded-xl border border-border bg-card">
	<!-- Controls -->
	<div class="flex shrink-0 items-center justify-between border-b border-border px-4 py-2.5">
		<button
			onclick={handleNewClick}
			class="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
			New
		</button>
		<div class="flex items-center gap-1.5">
			<button
				onclick={() => onPan('prev')}
				class="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
				aria-label="Earlier"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5"/></svg>
			</button>
			<button
				onclick={() => onPan('today')}
				class="rounded-md border border-border px-2.5 py-1 text-xs font-medium hover:border-primary hover:text-primary"
			>
				Today
			</button>
			<button
				onclick={() => onPan('next')}
				class="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
				aria-label="Later"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
			</button>
		</div>
	</div>

	<!-- Scrollable grid -->
	<div bind:this={scrollEl} bind:clientHeight={viewportHeight} class="min-h-0 flex-1 overflow-auto">
		<div class="relative select-none" style="width:{contentWidth}px; height:{contentHeight}px;">
			<!-- Header (sticky while scrolling vertically) -->
			<div class="sticky top-0 z-20 bg-card" style="height:{HEADER_HEIGHT}px;">
				<div class="relative h-full">
					{#each days as day, i}
						{#if day.showMonth}
							<div
								class="absolute top-0 whitespace-nowrap text-xs font-semibold text-foreground"
								style="left:{i * DAY_WIDTH + 4}px; top:8px;"
							>{day.showMonth}</div>
						{/if}
						<div
							class="absolute flex flex-col items-center justify-end border-b border-border pb-2 text-[11px]
								{day.isToday ? 'text-primary font-semibold' : day.isWeekend ? 'text-muted-foreground/60' : 'text-muted-foreground'}"
							style="left:{i * DAY_WIDTH}px; top:28px; width:{DAY_WIDTH}px; height:{HEADER_HEIGHT - 28}px;"
						>
							<span>{day.weekday}</span>
							<span class="mt-0.5 flex h-5 w-5 items-center justify-center rounded-full {day.isToday ? 'bg-primary text-primary-foreground' : ''}">{day.dayNum}</span>
						</div>
					{/each}
				</div>
			</div>

			<!-- Day-column background (weekend tint) -->
			{#each days as day, i}
				<div
					class="absolute {day.isWeekend ? 'bg-muted/40' : ''} border-r border-border/50"
					style="left:{i * DAY_WIDTH}px; top:{HEADER_HEIGHT}px; width:{DAY_WIDTH}px; height:{contentHeight - HEADER_HEIGHT}px;"
				></div>
			{/each}

			<!-- Today guide line -->
			{#if days.some((d) => d.isToday)}
				<div
					class="pointer-events-none absolute z-10 border-l border-dashed border-primary/50"
					style="left:{dayIndex(todayYmd) * DAY_WIDTH}px; top:{HEADER_HEIGHT}px; height:{contentHeight - HEADER_HEIGHT}px;"
				></div>
			{/if}

			<!-- Interaction surface for drag-to-create -->
			<div
				class="absolute cursor-crosshair"
				style="left:0; top:{HEADER_HEIGHT}px; width:{contentWidth}px; height:{contentHeight - HEADER_HEIGHT}px;"
				onpointerdown={onGridPointerDown}
				role="presentation"
			></div>

			<!-- Create-drag ghost -->
			{#if drag?.mode === 'create'}
				{@const s = Math.min(drag.liveStartIdx, drag.liveEndIdx)}
				{@const eIdx = Math.max(drag.liveStartIdx, drag.liveEndIdx)}
				<div
					class="pointer-events-none absolute rounded-md border-2 border-dashed border-primary bg-primary/10"
					style="left:{s * DAY_WIDTH + 2}px; top:{laneY(laneCount)}px; width:{(eIdx - s + 1) * DAY_WIDTH - 4}px; height:{ROW_HEIGHT}px;"
				></div>
			{/if}

			<!-- Item bars -->
			{#each laned as li (li.item.id)}
				{@const isDone = li.item.status === 'done'}
				{@const color = colorForCategory(li.item.category_name)}
				<div
					class="group absolute flex items-center gap-1 overflow-hidden rounded-md px-2 text-xs font-medium text-white shadow-sm transition-all hover:z-20 hover:shadow-lg hover:ring-2 hover:ring-black/10 hover:brightness-110 dark:hover:ring-white/30"
					style="{barStyle(li)} background-color:{color}; opacity:{isDone ? 0.55 : 0.92};"
					onpointerdown={(e) => onBarPointerDown(e, li)}
					role="button"
					tabindex="0"
					aria-label="{li.item.title}"
				>
					<!-- Left resize handle: wider hit zone, visible grip on hover -->
					<div
						class="absolute left-0 top-0 flex h-full w-3 cursor-ew-resize items-center justify-center"
						onpointerdown={(e) => onEdgePointerDown(e, li, 'left')}
						role="presentation"
					>
						<span class="h-4/5 w-1 rounded-full bg-white/0 group-hover:bg-white/70"></span>
					</div>
					{#if isDone}<span class="shrink-0">✓</span>{/if}
					{#if li.item.importance === 'high'}
						<svg class="h-2.5 w-2.5 shrink-0 text-red-200" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3 1v14M3 2h8l-1.5 2.5L11 7H3"/></svg>
					{:else if li.item.importance === 'medium'}
						<svg class="h-2.5 w-2.5 shrink-0 text-amber-200" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3 1v14M3 2h8l-1.5 2.5L11 7H3"/></svg>
					{/if}
					{#if li.item.start_time}<span class="shrink-0">🕐</span>{/if}
					<span class="truncate {isDone ? 'line-through' : ''}">{li.item.title}</span>
					{#if li.item.logged_minutes > 0}
						<span class="ml-auto shrink-0 font-mono text-[10px] opacity-80">{fmtMinutes(li.item.logged_minutes)}</span>
					{/if}
					<!-- Right resize handle -->
					<div
						class="absolute right-0 top-0 flex h-full w-3 cursor-ew-resize items-center justify-center"
						onpointerdown={(e) => onEdgePointerDown(e, li, 'right')}
						role="presentation"
					>
						<span class="h-4/5 w-1 rounded-full bg-white/0 group-hover:bg-white/70"></span>
					</div>
				</div>
			{/each}

			<!-- Quick-create popover -->
			{#if quickCreate}
				{@const s = dayIndex(quickCreate.startDate)}
				<div
					class="absolute z-30 w-56 rounded-lg border border-border bg-card p-3 shadow-2xl"
					style="left:{Math.min(s * DAY_WIDTH, contentWidth - 232)}px; top:{laneY(quickCreate.lane) + ROW_HEIGHT + 4}px;"
					onclick={(e) => e.stopPropagation()}
					onpointerdown={(e) => e.stopPropagation()}
					role="presentation"
				>
					<input
						bind:this={qcInput}
						type="text"
						bind:value={qcTitle}
						placeholder="Plan title…"
						onkeydown={(e) => { if (e.key === 'Enter') submitQuickCreate(); if (e.key === 'Escape') closeQuickCreate(); }}
						class="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					/>
					<select
						bind:value={qcCategoryId}
						class="mt-2 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
					>
						{#each categories as cat}
							<option value={cat.id}>{cat.display_name || cat.name}</option>
						{/each}
					</select>
					<div class="mt-2 flex justify-end gap-2">
						<button onclick={closeQuickCreate} class="rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted">Cancel</button>
						<button
							onclick={submitQuickCreate}
							disabled={!qcCategoryId}
							class="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-white hover:bg-primary/90 disabled:opacity-50"
						>
							Create
						</button>
					</div>
				</div>
			{/if}
		</div>
	</div>
</div>
