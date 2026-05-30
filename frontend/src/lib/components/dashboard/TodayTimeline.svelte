<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import * as d3 from 'd3';
	import type { TimerEntryResponse, ManualEntryResponse } from '$lib/api/client';
	import { timezone, normalizeAsUtc } from '$lib/stores/timezone';
	import { shortDateLabel } from '$lib/utils/lateNight';

	/**
	 * Today's timeline as a Gantt-style box chart. Each completed entry renders
	 * as a horizontal rectangle from its start time to its end time, color-coded
	 * by family. Overlapping intervals stack into lanes.
	 *
	 * - Timer entries: solid boxes spanning real start_time → end_time.
	 * - Manual entries with a real start_time: solid boxes (same as timers).
	 * - Manual entries with NO start_time: dashed-outline boxes positioned at
	 *   the INFERRED slot (created_at − duration), since we only know when they
	 *   were logged. Edit the entry to set a real start time.
	 *
	 * Interaction is view-only: hover shows the dim/highlight, click on a box
	 * toggles a tooltip with the entry's details.
	 */

	let {
		timerEntries = [],
		manualEntries = [],
		hasActiveTimer = false,
		viewingToday = true,
		selectedDate = '',
	}: {
		timerEntries: TimerEntryResponse[];
		manualEntries: ManualEntryResponse[];
		hasActiveTimer?: boolean;
		viewingToday?: boolean;       // gates the "now" guide and live-end behavior
		selectedDate?: string;        // for the header title when off-today
	} = $props();

	let container = $state<HTMLDivElement | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let stableWidth = $state(720);
	let containerHovered = $state(false);
	const MARGIN = { top: 16, right: 18, bottom: 28, left: 18 };
	const BOX_HEIGHT = 28;
	const LANE_GAP = 4;
	const MAX_LANES = 4;

	type DayEvent = {
		entryId: number;
		startHour: number;
		endHour: number;
		startIso: string;
		endIso: string;
		duration: number;
		category: string;
		family: string | null;
		description: string | null;
		location: string | null;
		kind: 'timer' | 'manual';
		inferredStart: boolean; // true for manual entries without a real start_time
		color: string;
		lane: number;
	};

	const PALETTE = [
		'#6366F1', '#10B981', '#F59E0B', '#EF4444',
		'#A855F7', '#06B6D4', '#EC4899', '#84CC16',
		'#3B82F6', '#F97316', '#14B8A6', '#D946EF',
	];

	function colorFor(key: string | null | undefined): string {
		const k = (key || '·').trim();
		let h = 0;
		for (let i = 0; i < k.length; i++) {
			h = ((h << 5) - h + k.charCodeAt(i)) | 0;
		}
		return PALETTE[Math.abs(h) % PALETTE.length];
	}

	function hourOfDay(iso: string, tz: string): number {
		try {
			const d = new Date(normalizeAsUtc(iso));
			const parts = new Intl.DateTimeFormat('en-US', {
				timeZone: tz,
				hour: 'numeric',
				minute: 'numeric',
				second: 'numeric',
				hour12: false,
			}).formatToParts(d);
			const h = Number(parts.find((p) => p.type === 'hour')?.value ?? 0);
			const m = Number(parts.find((p) => p.type === 'minute')?.value ?? 0);
			const s = Number(parts.find((p) => p.type === 'second')?.value ?? 0);
			const hh = h === 24 ? 0 : h;
			return hh + m / 60 + s / 3600;
		} catch {
			return 0;
		}
	}

	function fmtClock(iso: string, tz: string): string {
		try {
			return new Date(normalizeAsUtc(iso)).toLocaleTimeString(undefined, {
				timeZone: tz,
				hour: 'numeric',
				minute: '2-digit',
			});
		} catch {
			return '';
		}
	}

	function fmtDuration(min: number): string {
		const h = Math.floor(min / 60);
		const m = min % 60;
		if (h === 0) return `${m}m`;
		if (m === 0) return `${h}h`;
		return `${h}h ${m}m`;
	}

	// Raw, unlaned events. Manual entries use start_time when set, otherwise
	// fall back to created_at − duration with `inferredStart=true`.
	const rawEvents = $derived.by<DayEvent[]>(() => {
		const tz = $timezone;
		const out: DayEvent[] = [];

		for (const t of timerEntries) {
			if (!t.end_time || !t.duration_minutes) continue;
			out.push({
				entryId: t.id,
				startHour: hourOfDay(t.start_time, tz),
				endHour: hourOfDay(t.end_time, tz),
				startIso: t.start_time,
				endIso: t.end_time,
				duration: t.duration_minutes,
				category: t.category_name || 'Untitled',
				family: t.category_name,
				description: t.description,
				location: t.location,
				kind: 'timer',
				inferredStart: false,
				color: colorFor(t.category_name),
				lane: 0,
			});
		}
		for (const m of manualEntries) {
			if (!m.duration_minutes) continue;
			const hasStart = !!m.start_time;
			let startHour: number;
			let endHour: number;
			let startIso: string;
			let endIso: string;
			if (hasStart) {
				startHour = hourOfDay(m.start_time!, tz);
				endHour = startHour + m.duration_minutes / 60;
				startIso = m.start_time!;
				endIso = m.start_time!;
			} else {
				if (!m.created_at) continue;
				endHour = hourOfDay(m.created_at, tz);
				startHour = Math.max(0, endHour - m.duration_minutes / 60);
				startIso = m.created_at;
				endIso = m.created_at;
			}
			out.push({
				entryId: m.id,
				startHour,
				endHour,
				startIso,
				endIso,
				duration: m.duration_minutes,
				category: m.category_name || 'Untitled',
				family: m.category_name,
				description: m.description,
				location: m.location,
				kind: 'manual',
				inferredStart: !hasStart,
				color: colorFor(m.category_name),
				lane: 0,
			});
		}
		return out.sort((a, b) => a.startHour - b.startHour);
	});

	// Lane assignment so overlapping intervals don't render on top of each other.
	const events = $derived.by<DayEvent[]>(() => {
		const laneEnds: number[] = [];
		const result: DayEvent[] = [];
		for (const e of rawEvents) {
			let assigned = -1;
			for (let i = 0; i < laneEnds.length; i++) {
				if (laneEnds[i] <= e.startHour + 0.001) {
					assigned = i;
					laneEnds[i] = e.endHour;
					break;
				}
			}
			if (assigned < 0) {
				if (laneEnds.length < MAX_LANES) {
					laneEnds.push(e.endHour);
					assigned = laneEnds.length - 1;
				} else {
					assigned = MAX_LANES - 1;
					laneEnds[assigned] = Math.max(laneEnds[assigned], e.endHour);
				}
			}
			result.push({ ...e, lane: assigned });
		}
		return result;
	});

	const laneCount = $derived(
		events.length === 0 ? 1 : Math.max(1, ...events.map((e) => e.lane + 1)),
	);
	const totalMinutes = $derived(events.reduce((s, e) => s + e.duration, 0));
	const HEIGHT = $derived(
		MARGIN.top + laneCount * (BOX_HEIGHT + LANE_GAP) - LANE_GAP + MARGIN.bottom,
	);

	// "Now" only matters when looking at today — on past days it would push the
	// x-domain to a nonsensical wall-clock hour.
	const nowHour = $derived(viewingToday ? hourOfDay(new Date().toISOString(), $timezone) : 0);

	const xDomain = $derived.by<[number, number]>(() => {
		if (events.length === 0) {
			return viewingToday
				? [6, Math.max(12, nowHour + 0.5)]
				: [6, 22]; // sensible fallback for an empty past day
		}
		const first = Math.min(...events.map((e) => e.startHour));
		// Only stretch toward "now" when viewing today; otherwise just hug the data.
		const last = viewingToday
			? Math.max(nowHour, ...events.map((e) => e.endHour))
			: Math.max(...events.map((e) => e.endHour));
		const pad = Math.max(0.25, (last - first) * 0.05);
		return [Math.max(0, first - pad), Math.min(24, last + pad)];
	});

	// ── Interaction: view-only. Hover = highlight, click = tooltip. ───────
	let hoverIdx = $state<number | null>(null);
	let selectedIdx = $state<number | null>(null);
	let selectedX = $state(0);
	let selectedY = $state(0);

	function setHover(i: number) {
		hoverIdx = i;
	}

	function clearHover() {
		hoverIdx = null;
	}

	function onBoxClick(i: number, ev: MouseEvent) {
		if (svgEl) {
			const r = svgEl.getBoundingClientRect();
			selectedX = ev.clientX - r.left;
			selectedY = ev.clientY - r.top;
		}
		selectedIdx = selectedIdx === i ? null : i;
	}

	function onKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape' && selectedIdx !== null) {
			selectedIdx = null;
		}
	}

	// ── Rendering with D3 (scales) ────────────────────────────────────────
	const W = $derived(stableWidth);
	const xScale = $derived(
		d3.scaleLinear().domain(xDomain).range([MARGIN.left, W - MARGIN.right]),
	);

	function laneY(lane: number): number {
		return MARGIN.top + lane * (BOX_HEIGHT + LANE_GAP);
	}

	const xTicks = $derived.by(() => {
		const [lo, hi] = xDomain;
		const span = hi - lo;
		const step = span < 8 ? 1 : 2;
		const ticks: number[] = [];
		const start = Math.ceil(lo);
		for (let h = start; h <= Math.floor(hi); h += step) ticks.push(h);
		return ticks;
	});

	function fmtHour(h: number): string {
		if (h === 0 || h === 24) return '12a';
		if (h === 12) return '12p';
		if (h < 12) return `${h}a`;
		return `${h - 12}p`;
	}

	// ── ResizeObserver ────────────────────────────────────────────────────
	let resizeObserver: ResizeObserver | null = null;
	let resizeTimer: ReturnType<typeof setTimeout> | null = null;

	onMount(() => {
		if (!container) return;
		const measure = () => {
			if (!container) return;
			const w = Math.floor(container.getBoundingClientRect().width);
			if (w >= 200 && Math.abs(w - stableWidth) > 4) stableWidth = w;
		};
		measure();
		resizeObserver = new ResizeObserver(() => {
			if (resizeTimer) clearTimeout(resizeTimer);
			resizeTimer = setTimeout(measure, 80);
		});
		resizeObserver.observe(container);
		window.addEventListener('keydown', onKeyDown);
	});

	onDestroy(() => {
		if (resizeObserver) resizeObserver.disconnect();
		if (resizeTimer) clearTimeout(resizeTimer);
		window.removeEventListener('keydown', onKeyDown);
	});

	const tooltipStyle = $derived.by(() => {
		const tx = Math.min(Math.max(selectedX + 14, 0), W - 240);
		const ty = Math.max(selectedY - 60, 8);
		return `left: ${tx}px; top: ${ty}px;`;
	});
</script>

<section
	bind:this={container}
	class="relative"
	onmouseenter={() => (containerHovered = true)}
	onmouseleave={() => (containerHovered = false)}
	role="presentation"
>
	<div class="mb-3 flex items-baseline justify-between gap-3">
		<h2 class="text-lg font-semibold">
			{viewingToday
				? "Today's Timeline"
				: `${selectedDate ? shortDateLabel(selectedDate) : ''} · Timeline`}
		</h2>
		<span
			class="text-xs text-muted-foreground text-right transition-opacity duration-150"
			class:opacity-0={!containerHovered}
		>
			{events.length === 0
				? (viewingToday
					? 'Hit play on a category to start filling this in'
					: 'No entries logged on this day')
				: `${fmtDuration(totalMinutes)} across ${events.length} entr${events.length === 1 ? 'y' : 'ies'} · click a box for details · edit a manual entry to set its start time`}
		</span>
	</div>

	<div class="rounded-xl border border-border bg-card p-3">
		<svg
			bind:this={svgEl}
			width={W}
			height={HEIGHT}
			viewBox="0 0 {W} {HEIGHT}"
			class="block w-full"
			onmouseleave={clearHover}
			role="img"
			aria-label="Timeline of today's entries — each box spans an entry's start to end time"
		>
			<!-- X axis baseline -->
			<line
				x1={MARGIN.left}
				x2={W - MARGIN.right}
				y1={HEIGHT - MARGIN.bottom}
				y2={HEIGHT - MARGIN.bottom}
				stroke="currentColor"
				stroke-opacity="0.2"
			/>

			<!-- X tick labels -->
			{#each xTicks as h}
				<line
					x1={xScale(h)}
					x2={xScale(h)}
					y1={HEIGHT - MARGIN.bottom}
					y2={HEIGHT - MARGIN.bottom + 4}
					stroke="currentColor"
					stroke-opacity="0.25"
				/>
				<text
					x={xScale(h)}
					y={HEIGHT - MARGIN.bottom + 16}
					text-anchor="middle"
					class="fill-muted-foreground text-[10px] font-mono"
				>{fmtHour(h)}</text>
			{/each}

			<!-- "Now" vertical guide when a timer is running -->
			{#if hasActiveTimer && nowHour >= xDomain[0] && nowHour <= xDomain[1]}
				<line
					x1={xScale(nowHour)}
					x2={xScale(nowHour)}
					y1={MARGIN.top}
					y2={HEIGHT - MARGIN.bottom}
					stroke="#10B981"
					stroke-width="1.25"
					stroke-dasharray="3,3"
					stroke-opacity="0.6"
				/>
				<circle cx={xScale(nowHour)} cy={MARGIN.top + 4} r="4" fill="#10B981">
					<animate attributeName="opacity" values="1;0.25;1" dur="1.6s" repeatCount="indefinite" />
				</circle>
			{/if}

			<!-- Boxes -->
			{#each events as e, i}
				{@const xStart = xScale(e.startHour)}
				{@const xEnd = xScale(e.endHour)}
				{@const w = Math.max(6, xEnd - xStart)}
				{@const y = laneY(e.lane)}
				{@const dim = hoverIdx !== null && hoverIdx !== i}
				<rect
					x={xStart}
					y={y}
					width={w}
					height={BOX_HEIGHT}
					rx="4"
					fill={e.color}
					fill-opacity={dim ? 0.35 : (e.inferredStart ? 0.18 : 0.85)}
					stroke={e.color}
					stroke-width={hoverIdx === i ? 2.5 : 1.5}
					stroke-opacity={dim ? 0.55 : 1}
					stroke-dasharray={e.inferredStart ? '4,3' : undefined}
					style="cursor: pointer; transition: fill-opacity 0.15s, stroke-width 0.15s;"
					onclick={(ev) => onBoxClick(i, ev)}
					onmouseenter={() => setHover(i)}
					onmouseleave={clearHover}
				/>
				{#if w >= 60}
					<text
						x={xStart + 8}
						y={y + BOX_HEIGHT / 2}
						dy="0.32em"
						class="pointer-events-none text-[11px] font-semibold"
						fill={e.inferredStart ? e.color : 'white'}
						fill-opacity={dim ? 0.6 : 1}
					>
						<tspan>{e.category}</tspan>
						{#if w >= 120}
							<tspan dx="6" class="text-[10px] font-mono" fill-opacity={dim ? 0.5 : 0.85}>
								{fmtDuration(e.duration)}
							</tspan>
						{/if}
					</text>
				{/if}
			{/each}

			<!-- Empty state -->
			{#if events.length === 0}
				<text
					x={W / 2}
					y={HEIGHT / 2 - 4}
					text-anchor="middle"
					class="fill-muted-foreground text-xs"
				>{viewingToday ? 'No entries yet today' : 'Nothing logged on this day'}</text>
				<text
					x={W / 2}
					y={HEIGHT / 2 + 14}
					text-anchor="middle"
					class="fill-muted-foreground/60 text-[10px]"
				>Each entry becomes a colored box spanning its start → end time.</text>
			{/if}
		</svg>

		<!-- Tooltip — opens on click, dismissed by Escape, clicking outside, or the × button. -->
		{#if selectedIdx !== null && events[selectedIdx]}
			{@const e = events[selectedIdx]}
			<div
				class="absolute z-10 max-w-xs rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-lg"
				style={tooltipStyle}
			>
				<div class="flex items-center justify-between gap-2">
					<div class="flex min-w-0 items-center gap-1.5">
						<span class="h-2 w-2 shrink-0 rounded-full" style="background: {e.color}"></span>
						<span class="truncate font-medium">{e.category}</span>
						<span class="text-muted-foreground">·</span>
						<span class="shrink-0 font-mono">{fmtDuration(e.duration)}</span>
					</div>
					<button
						onclick={() => (selectedIdx = null)}
						class="-mr-1 shrink-0 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
						aria-label="Close"
					>
						<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
				<div class="mt-1 font-mono text-[11px] text-muted-foreground">
					{fmtClock(e.startIso, $timezone)} – {fmtClock(e.endIso, $timezone)}
				</div>
				<div class="mt-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
					{e.kind === 'timer' ? 'Timer' : 'Manual'}{e.inferredStart ? ' · start inferred' : ''}
				</div>
				{#if e.description}
					<div class="mt-1.5 leading-snug">{e.description}</div>
				{/if}
				{#if e.location}
					<div class="mt-1 text-muted-foreground">@ {e.location}</div>
				{/if}
			</div>
		{/if}
	</div>
</section>
