<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import * as d3 from 'd3';
	import type { TimerEntryResponse, ManualEntryResponse } from '$lib/api/client';
	import { timezone, normalizeAsUtc } from '$lib/stores/timezone';

	/**
	 * Today's timeline as a "spike plot": each logged entry is a single vertical
	 * impulse positioned at its time-of-day, with height = duration_minutes and
	 * color = family. A cumulative line over one day buries the per-event story;
	 * spikes show "I spent 45m on X at 2pm, then 20m on Y at 4pm" directly.
	 *
	 * Uses BOTH:
	 *   - TIME data: x-position (hour-of-day) + spike height (duration)
	 *   - TEXT data: description + location revealed on hover
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
	const HEIGHT = 220;
	const MARGIN = { top: 16, right: 18, bottom: 28, left: 44 };

	type DayEvent = {
		hour: number;            // hours since midnight (e.g., 14.55)
		iso: string;             // original timestamp for tooltip display
		duration: number;        // minutes
		category: string;
		family: string | null;
		description: string | null;
		location: string | null;
		kind: 'timer' | 'manual';
		color: string;
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

	// Build the chronologically-sorted event list, cumulative minutes derived.
	const events = $derived.by<DayEvent[]>(() => {
		const tz = $timezone;
		const out: DayEvent[] = [];
		for (const t of timerEntries) {
			if (!t.end_time || !t.duration_minutes) continue;
			out.push({
				hour: hourOfDay(t.end_time, tz),
				iso: t.end_time,
				duration: t.duration_minutes,
				category: t.category_name || 'Untitled',
				family: t.category_name,
				description: t.description,
				location: t.location,
				kind: 'timer',
				color: colorFor(t.category_name),
			});
		}
		for (const m of manualEntries) {
			if (!m.created_at) continue;
			out.push({
				hour: hourOfDay(m.created_at, tz),
				iso: m.created_at,
				duration: m.duration_minutes,
				category: m.category_name || 'Untitled',
				family: m.category_name,
				description: m.description,
				location: m.location,
				kind: 'manual',
				color: colorFor(m.category_name),
			});
		}
		return out.sort((a, b) => a.hour - b.hour);
	});

	// Per-event maxima for the y-axis. The dashboard's stat-cards already show
	// the aggregate total; here we want each spike's height to be readable as
	// the duration of that one entry, not buried inside a cumulative sum.
	const totalMinutes = $derived(events.reduce((s, e) => s + e.duration, 0));
	const maxDuration = $derived(events.length > 0 ? Math.max(...events.map((e) => e.duration)) : 60);

	// Now (hour-of-day in the chosen tz). Updates on each render — that's fine
	// because the dashboard polls timers anyway.
	const nowHour = $derived(hourOfDay(new Date().toISOString(), $timezone));

	// Domain: earliest hour minus a bit, to max(now, last event) plus a bit
	const xDomain = $derived.by<[number, number]>(() => {
		if (events.length === 0) {
			// No events: show 6am → max(noon, now) so the empty axis isn't silly.
			return [6, Math.max(12, nowHour + 0.5)];
		}
		const first = events[0].hour;
		const last = Math.max(events[events.length - 1].hour, nowHour);
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
	const yScale = $derived(
		d3
			.scaleLinear()
			// Snap to 30-min increments above the tallest spike, min 60.
			.domain([0, Math.max(60, Math.ceil(maxDuration / 30) * 30)])
			.range([HEIGHT - MARGIN.bottom, MARGIN.top]),
	);

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

	const yTicks = $derived.by(() => {
		const max = yScale.domain()[0]; // domain is [0, max]
		// Use d3 to compute up to ~4 ticks
		return yScale.ticks(4).filter((t) => t > 0);
	});

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
			<!-- Y gridlines -->
			{#each yTicks as t}
				<line
					x1={MARGIN.left}
					x2={W - MARGIN.right}
					y1={yScale(t)}
					y2={yScale(t)}
					stroke="currentColor"
					stroke-opacity="0.07"
				/>
				<text
					x={MARGIN.left - 8}
					y={yScale(t)}
					dy="0.32em"
					text-anchor="end"
					class="fill-muted-foreground text-[10px] font-mono"
				>{t}m</text>
			{/each}

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

			<!-- One spike per event: vertical line from baseline up to the event's
			     duration, capped by a small circle at the top for hover affordance. -->
			{#each events as e, i}
				<line
					x1={xScale(e.hour)}
					x2={xScale(e.hour)}
					y1={yScale(0)}
					y2={yScale(e.duration)}
					stroke={e.color}
					stroke-width={hoverIdx === i ? 4 : 3}
					stroke-linecap="round"
					stroke-opacity={hoverIdx === null || hoverIdx === i ? 1 : 0.45}
					style="cursor: pointer; transition: stroke-width 0.15s, stroke-opacity 0.15s;"
					onmouseenter={(ev) => setHover(i, ev)}
					onmouseleave={handleMouseLeave}
				/>
				<circle
					cx={xScale(e.hour)}
					cy={yScale(e.duration)}
					r={hoverIdx === i ? 6 : 4}
					fill={e.color}
					fill-opacity={hoverIdx === null || hoverIdx === i ? 1 : 0.45}
					stroke="var(--color-card, #fff)"
					stroke-width="2"
					style="cursor: pointer; transition: r 0.15s, fill-opacity 0.15s;"
					onmouseenter={(ev) => setHover(i, ev)}
					onmouseleave={handleMouseLeave}
				/>
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
				>Each entry shows up as a vertical spike at its time-of-day.</text>
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
				<div class="mt-1 text-[10px] uppercase tracking-wider text-muted-foreground">
					{e.kind === 'timer' ? 'Timer' : 'Manual'} · stopped {fmtClock(e.iso, $timezone)}
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
