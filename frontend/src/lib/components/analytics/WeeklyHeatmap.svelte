<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';
	import type { HeatmapPoint } from '$lib/api/client';
	import { getThemeColors, observeResize, formatHoursMinutes } from '$lib/utils/chart';

	let { data }: { data: HeatmapPoint[] } = $props();

	let container = $state<HTMLDivElement | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let width = 400;
	let cleanup: (() => void) | null = null;

	const CELL_SIZE = 14;
	const CELL_GAP = 2;
	const DAY_LABELS = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun'];

	function render() {
		if (!data.length || !svgEl || !container) return;

		const theme = getThemeColors(container);
		const margin = { top: 16, right: 10, bottom: 10, left: 32 };

		// Group data by ISO week
		const parseDate = d3.timeParse('%Y-%m-%d');
		const points = data.map(d => ({
			...d,
			dateObj: parseDate(d.date)!,
		})).filter(d => d.dateObj);

		if (points.length === 0) return;

		// Sort by date
		points.sort((a, b) => a.dateObj.getTime() - b.dateObj.getTime());

		// Calculate week index from start
		const startDate = points[0].dateObj;
		const startWeekStart = d3.timeMonday(startDate);

		const weekData: Map<string, number> = new Map();
		let maxWeek = 0;

		for (const p of points) {
			const weekStart = d3.timeMonday(p.dateObj);
			const weekIdx = Math.floor((weekStart.getTime() - startWeekStart.getTime()) / (7 * 86400000));
			if (weekIdx > maxWeek) maxWeek = weekIdx;
			const key = `${weekIdx}-${p.day_of_week}`;
			weekData.set(key, (weekData.get(key) || 0) + p.total_minutes);
		}

		const numWeeks = maxWeek + 1;
		const cellStep = CELL_SIZE + CELL_GAP;
		const svgW = margin.left + numWeeks * cellStep + margin.right;
		const svgH = margin.top + 7 * cellStep + margin.bottom;

		const maxMins = Math.max(...weekData.values(), 1);
		const colorScale = d3.scaleSequential()
			.domain([0, maxMins])
			.interpolator(d3.interpolateGreens);

		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();
		svg.attr('width', Math.max(svgW, width)).attr('height', svgH);

		const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

		// Day labels
		for (let d = 0; d < 7; d++) {
			if (DAY_LABELS[d]) {
				g.append('text')
					.attr('x', -6)
					.attr('y', d * cellStep + CELL_SIZE / 2)
					.attr('text-anchor', 'end')
					.attr('dominant-baseline', 'central')
					.attr('fill', theme.muted)
					.style('font-size', '9px')
					.style('font-family', 'system-ui, sans-serif')
					.text(DAY_LABELS[d]);
			}
		}

		// Tooltip
		const tooltipG = svg.append('g').style('pointer-events', 'none').style('opacity', 0);
		const tooltipRect = tooltipG.append('rect')
			.attr('rx', 4).attr('fill', theme.bg).attr('stroke', theme.border).attr('stroke-width', 1);
		const tooltipText = tooltipG.append('text')
			.attr('fill', theme.fg).style('font-size', '10px').style('font-family', 'system-ui, sans-serif');

		// Cells
		for (let w = 0; w <= maxWeek; w++) {
			for (let d = 0; d < 7; d++) {
				const key = `${w}-${d}`;
				const mins = weekData.get(key) || 0;
				const cx = w * cellStep;
				const cy = d * cellStep;

				// Compute the actual date for this cell
				const cellDate = new Date(startWeekStart.getTime() + w * 7 * 86400000 + d * 86400000);
				const dateStr = cellDate.toISOString().split('T')[0];

				g.append('rect')
					.attr('x', cx)
					.attr('y', cy)
					.attr('width', CELL_SIZE)
					.attr('height', CELL_SIZE)
					.attr('rx', 2)
					.attr('fill', mins > 0 ? colorScale(mins) : theme.border)
					.attr('fill-opacity', mins > 0 ? 1 : 0.3)
					.style('cursor', 'pointer')
					.on('mouseenter', function (event: MouseEvent) {
						d3.select(this).attr('stroke', theme.fg).attr('stroke-width', 1.5);
						const label = `${dateStr}: ${formatHoursMinutes(mins)}`;
						tooltipText.text(label);
						const bbox = tooltipText.node()!.getBBox();
						const tw = bbox.width + 12;
						const th = bbox.height + 8;
						const tx = Math.min(cx + margin.left, svgW - tw - 5);
						const ty = cy + margin.top - th - 4;
						tooltipRect.attr('x', tx).attr('y', ty).attr('width', tw).attr('height', th);
						tooltipText.attr('x', tx + 6).attr('y', ty + th - 6);
						tooltipG.style('opacity', 1);
					})
					.on('mouseleave', function () {
						d3.select(this).attr('stroke', 'none');
						tooltipG.style('opacity', 0);
					});
			}
		}

		// Set container height
		if (container) {
			container.style.height = `${svgH}px`;
		}
	}

	$effect(() => {
		if (data && svgEl && container) {
			requestAnimationFrame(() => render());
		}
	});

	onMount(() => {
		if (container) {
			cleanup = observeResize(container, (w) => {
				if (Math.abs(w - width) > 5) {
					width = w;
					render();
				}
			});
		}
		return () => cleanup?.();
	});
</script>

<div class="rounded-lg border border-border bg-card p-4">
	<h3 class="mb-2 text-sm font-semibold">Activity Heatmap</h3>
	<div class="relative overflow-x-auto" style="min-height: 100px;" bind:this={container}>
		{#if data.length === 0}
			<div class="flex h-24 items-center justify-center text-sm text-muted-foreground">
				No heatmap data
			</div>
		{:else}
			<svg bind:this={svgEl}></svg>
		{/if}
	</div>
</div>
