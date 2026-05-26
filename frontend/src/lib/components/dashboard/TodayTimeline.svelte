<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import * as d3 from 'd3';
	import type { TimerEntryResponse, ManualEntryResponse } from '$lib/api/client';
	import { timezone, normalizeAsUtc } from '$lib/stores/timezone';

	/**
	 * Today's timeline as a Gantt-style box chart. Each completed entry renders
	 * as a horizontal rectangle from its start time to its end time, color-coded
	 * by family. Overlapping intervals stack into lanes.
	 *
	 * - Timer entries: solid boxes spanning real start_time → end_time
	 * - Manual entries: dashed-outline boxes — the start time is INFERRED as
	 *   (created_at − duration_minutes), since manuals only record when they
	 *   were logged, not when the work happened. Hover label makes this clear.
	 *
	 * Uses BOTH:
	 *   - TIME data: x-extent (start → end) and lane layout
	 *   - TEXT data: description, location, category — revealed on hover
	 */

	let {
		timerEntries = [],
		manualEntries = [],
		hasActiveTimer = false,
	}: {
		timerEntries: TimerEntryResponse[];
		manualEntries: ManualEntryResponse[];
		hasActiveTimer?: boolean;
	} = $props();

	let container = $state<HTMLDivElement | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let stableWidth = $state(720);
	const MARGIN = { top: 16, right: 18, bottom: 28, left: 18 };
	const BOX_HEIGHT = 28;
	const LANE_GAP = 4;
	const MAX_LANES = 4;

	type DayEvent = {
		startHour: number;       // hours since midnight (e.g., 14.55)
		endHour: number;
		startIso: string;        // for tooltip — original start (or inferred)
		endIso: string;          // for tooltip
		duration: number;        // minutes
		category: string;
		family: string | null;
		description: string | null;
		location: string | null;
		kind: 'timer' | 'manual';
		inferredStart: boolean;  // true for manual entries
		color: string;
		lane: number;            // assigned by stacking pass
	};

	// Stable family-color palette. Same family display name → same color across
	// sessions and days, without an extra API call to fetch family.color.
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
			// Some locales render midnight as 24 — normalise to 0.
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

	// Build raw events with real or inferred start/end times.
	const rawEvents = $derived.by<DayEvent[]>(() => {
		const tz = $timezone;
		const out: DayEvent[] = [];

		for (const t of timerEntries) {
			if (!t.end_time || !t.duration_minutes) continue;
			// Timer has both start_time and end_time. Use them directly.
			const startIso = t.start_time;
			const endIso = t.end_time;
			out.push({
				startHour: hourOfDay(startIso, tz),
				endHour: hourOfDay(endIso, tz),
				startIso,
				endIso,
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
			if (!m.created_at || !m.duration_minutes) continue;
			// Manual entries don't record when the work happened — only when the
			// user submitted the form. Approximate: end at created_at, infer
			// start as created_at - duration. Flagged in the UI as inferred.
			const endHour = hourOfDay(m.created_at, tz);
			const startHour = Math.max(0, endHour - m.duration_minutes / 60);
			out.push({
				startHour,
				endHour,
				startIso: m.created_at,
				endIso: m.created_at,
				duration: m.duration_minutes,
				category: m.category_name || 'Untitled',
				family: m.category_name,
				description: m.description,
				location: m.location,
				kind: 'manual',
				inferredStart: true,
				color: colorFor(m.category_name),
				lane: 0,
			});
		}
		return out.sort((a, b) => a.startHour - b.startHour);
	});

	// Lane assignment so overlapping intervals don't render on top of each other.
	// Greedy: each event reuses the first lane whose last-end time precedes it,
	// else opens a new lane. Capped at MAX_LANES; overflow fits into the last.
	const events = $derived.by<DayEvent[]>(() => {
		const laneEnds: number[] = []; // lane index → end of last event in that lane
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
					// Overflow: drop into the last lane (best-effort visualization).
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

	// Now (hour-of-day in the chosen tz). Updates on each render — that's fine
	// because the dashboard polls timers anyway.
	const nowHour = $derived(hourOfDay(new Date().toISOString(), $timezone));

	// Domain: earliest startHour minus a bit, to max(now, last endHour) plus a bit
	const xDomain = $derived.by<[number, number]>(() => {
		if (events.length === 0) {
			return [6, Math.max(12, nowHour + 0.5)];
		}
		const first = Math.min(...events.map((e) => e.startHour));
		const last = Math.max(nowHour, ...events.map((e) => e.endHour));
		const pad = Math.max(0.25, (last - first) * 0.05);
		return [Math.max(0, first - pad), Math.min(24, last + pad)];
	});

	let hoverIdx = $state<number | null>(null);
	let hoverX = $state(0);
	let hoverY = $state(0);

	function handleMouseMove(e: MouseEvent) {
		if (!svgEl) return;
		const rect = svgEl.getBoundingClientRect();
		hoverX = e.clientX - rect.left;
		hoverY = e.clientY - rect.top;
	}

	function handleMouseLeave() {
		hoverIdx = null;
	}

	function setHover(i: number, e: MouseEvent) {
		hoverIdx = i;
		handleMouseMove(e);
	}

	// ── Rendering with D3 (scales + path) ─────────────────────────────────
	const W = $derived(stableWidth);
	const xScale = $derived(
		d3.scaleLinear().domain(xDomain).range([MARGIN.left, W - MARGIN.right]),
	);
	// Lane → y position
	function laneY(lane: number): number {
		return MARGIN.top + lane * (BOX_HEIGHT + LANE_GAP);
	}

	// Axis ticks
	const xTicks = $derived.by(() => {
		const [lo, hi] = xDomain;
		const span = hi - lo;
		// Step size: 1h if span < 8, else 2h
		const step = span < 8 ? 1 : 2;
		const ticks: number[] = [];
		const start = Math.ceil(lo);
		for (let h = start; h <= Math.floor(hi); h += step) {
			ticks.push(h);
		}
		return ticks;
	});

	function fmtHour(h: number): string {
		if (h === 0 || h === 24) return '12a';
		if (h === 12) return '12p';
		if (h < 12) return `${h}a`;
		return `${h - 12}p`;
	}

	// No y-axis ticks with Gantt-style boxes — position carries no quantitative
	// meaning (it's just lane stacking). Time + duration are conveyed by x-extent.

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
	});

	onDestroy(() => {
		if (resizeObserver) resizeObserver.disconnect();
		if (resizeTimer) clearTimeout(resizeTimer);
	});

	// Tooltip position (clamped to container)
	const tooltipStyle = $derived.by(() => {
		const tx = Math.min(Math.max(hoverX + 14, 0), W - 240);
		const ty = Math.max(hoverY - 60, 8);
		return `left: ${tx}px; top: ${ty}px;`;
	});
</script>

<section bind:this={container} class="relative">
	<div class="mb-3 flex items-baseline justify-between">
		<h2 class="text-lg font-semibold">Today's Timeline</h2>
		<span class="text-xs text-muted-foreground">
			{events.length === 0
				? 'Hit play on a category to start filling this in'
				: `${fmtDuration(totalMinutes)} across ${events.length} entr${events.length === 1 ? 'y' : 'ies'}`}
		</span>
	</div>

	<div class="rounded-xl border border-border bg-card p-3">
		<svg
			bind:this={svgEl}
			width={W}
			height={HEIGHT}
			viewBox="0 0 {W} {HEIGHT}"
			class="block w-full"
			onmousemove={handleMouseMove}
			onmouseleave={handleMouseLeave}
			role="img"
			aria-label="Timeline of today's entries — each spike is one logged session"
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

			<!-- "Now" vertical guide if a timer is running. Drawn behind spikes
			     so the impulses stay the dominant marks. -->
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

			<!-- One box per event: x = start, width = end - start, lane = y row.
			     Minimum width 6px so very short entries are still clickable. -->
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
					onmouseenter={(ev) => setHover(i, ev)}
					onmouseleave={handleMouseLeave}
				/>
				<!-- In-box label when the box is wide enough to fit it -->
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

			<!-- Empty state hint -->
			{#if events.length === 0}
				<text
					x={W / 2}
					y={HEIGHT / 2 - 4}
					text-anchor="middle"
					class="fill-muted-foreground text-xs"
				>No entries yet today</text>
				<text
					x={W / 2}
					y={HEIGHT / 2 + 14}
					text-anchor="middle"
					class="fill-muted-foreground/60 text-[10px]"
				>Each entry becomes a colored box spanning its start → end time.</text>
			{/if}
		</svg>

		<!-- Tooltip -->
		{#if hoverIdx !== null && events[hoverIdx]}
			{@const e = events[hoverIdx]}
			<div
				class="pointer-events-none absolute z-10 max-w-xs rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-lg"
				style={tooltipStyle}
			>
				<div class="flex items-center gap-1.5">
					<span class="h-2 w-2 rounded-full" style="background: {e.color}"></span>
					<span class="font-medium">{e.category}</span>
					<span class="text-muted-foreground">·</span>
					<span class="font-mono">{fmtDuration(e.duration)}</span>
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
