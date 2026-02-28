<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';
	import type { DailySeriesPoint } from '$lib/api/client';
	import { PALETTE, getThemeColors, observeResize, formatHoursMinutes } from '$lib/utils/chart';

	let { data, timeScale = 'overall' }: { data: DailySeriesPoint[]; timeScale?: string } = $props();

	let container = $state<HTMLDivElement | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let width = 800;
	let height = 300;
	let rendered = false;
	let cleanup: (() => void) | null = null;

	function getAllCategories(): string[] {
		const totals: Record<string, number> = {};
		for (const d of data) {
			for (const c of d.categories) {
				totals[c.name] = (totals[c.name] || 0) + c.minutes;
			}
		}
		return Object.entries(totals)
			.sort((a, b) => b[1] - a[1])
			.map(([name]) => name);
	}

	function getCategoryColor(cat: string, catList: string[]): string {
		// Try to use the color from data first
		for (const d of data) {
			for (const c of d.categories) {
				if (c.name === cat && c.color) return c.color;
			}
		}
		const idx = catList.indexOf(cat);
		return PALETTE[idx % PALETTE.length];
	}

	function render() {
		if (!data.length || !svgEl || !container) return;

		const theme = getThemeColors(container);
		const margin = { top: 20, right: 20, bottom: 30, left: 50 };
		const w = width - margin.left - margin.right;
		const h = height - margin.top - margin.bottom;

		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();
		svg.attr('width', width).attr('height', height);

		const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

		const categories = getAllCategories();
		const colorMap: Record<string, string> = {};
		for (const cat of categories) {
			colorMap[cat] = getCategoryColor(cat, categories);
		}

		// Build stacked data
		const stackData = data.map(d => {
			const row: Record<string, number | string> = { date: d.date };
			for (const cat of categories) {
				row[cat] = 0;
			}
			for (const c of d.categories) {
				row[c.name] = c.minutes / 60; // convert to hours
			}
			return row;
		});

		const parseDate = d3.timeParse('%Y-%m-%d');
		const dates = data.map(d => parseDate(d.date)!).filter(Boolean);

		const x = d3.scaleTime()
			.domain(d3.extent(dates) as [Date, Date])
			.range([0, w]);

		const stack = d3.stack<Record<string, number | string>>()
			.keys(categories)
			.value((d, key) => (d[key] as number) || 0)
			.order(d3.stackOrderNone)
			.offset(d3.stackOffsetNone);

		const series = stack(stackData);

		const yMax = d3.max(series, s => d3.max(s, d => d[1])) || 1;
		const y = d3.scaleLinear().domain([0, yMax]).nice().range([h, 0]);

		const area = d3.area<d3.SeriesPoint<Record<string, number | string>>>()
			.x((_d, i) => x(dates[i]))
			.y0(d => y(d[0]))
			.y1(d => y(d[1]))
			.curve(d3.curveMonotoneX);

		// Draw areas
		for (const s of series) {
			g.append('path')
				.datum(s)
				.attr('d', area)
				.attr('fill', colorMap[s.key] || '#6B7280')
				.attr('fill-opacity', 0.7)
				.attr('stroke', colorMap[s.key] || '#6B7280')
				.attr('stroke-width', 0.5);
		}

		// X axis — adapt format/ticks to time scale
		let xTickFormat: (d: Date) => string;
		let xTickCount: number;
		switch (timeScale) {
			case 'year':
				xTickFormat = d3.timeFormat('%b');
				xTickCount = 12;
				break;
			case 'month':
				xTickFormat = d3.timeFormat('%d');
				xTickCount = Math.min(data.length, 8);
				break;
			case 'week':
				xTickFormat = d3.timeFormat('%a %d');
				xTickCount = 7;
				break;
			default: // 'overall'
				xTickFormat = d3.timeFormat('%b %Y');
				xTickCount = Math.min(data.length, 8);
				break;
		}

		g.append('g')
			.attr('transform', `translate(0,${h})`)
			.call(d3.axisBottom(x).ticks(xTickCount).tickFormat(xTickFormat as any))
			.call(g => g.select('.domain').attr('stroke', theme.border))
			.call(g => g.selectAll('.tick text').attr('fill', theme.muted).style('font-size', '10px'))
			.call(g => g.selectAll('.tick line').attr('stroke', theme.border));

		// Y axis
		g.append('g')
			.call(d3.axisLeft(y).ticks(5).tickFormat(d => `${d}h`))
			.call(g => g.select('.domain').attr('stroke', theme.border))
			.call(g => g.selectAll('.tick text').attr('fill', theme.muted).style('font-size', '10px'))
			.call(g => g.selectAll('.tick line').attr('stroke', theme.border));

		// Tooltip overlay
		const tooltipLine = g.append('line')
			.attr('stroke', theme.muted)
			.attr('stroke-width', 1)
			.attr('stroke-dasharray', '4,4')
			.attr('y1', 0).attr('y2', h)
			.style('opacity', 0);

		const tooltipG = svg.append('g').style('pointer-events', 'none').style('opacity', 0);
		const tooltipRect = tooltipG.append('rect')
			.attr('rx', 6).attr('fill', theme.bg).attr('stroke', theme.border).attr('stroke-width', 1);
		const tooltipText = tooltipG.append('text')
			.attr('fill', theme.fg).style('font-size', '11px').style('font-family', 'system-ui, sans-serif');

		const bisect = d3.bisector((d: DailySeriesPoint) => parseDate(d.date)!).left;

		g.append('rect')
			.attr('width', w).attr('height', h)
			.attr('fill', 'transparent')
			.on('mousemove', function (event: MouseEvent) {
				const [mx] = d3.pointer(event, this);
				const date = x.invert(mx);
				const idx = Math.min(bisect(data, date), data.length - 1);
				const d = data[idx];
				if (!d) return;

				const px = x(parseDate(d.date)!);
				tooltipLine.attr('x1', px).attr('x2', px).style('opacity', 1);

				const lines = [`${d.date}  ·  ${formatHoursMinutes(d.total_minutes)}`];
				for (const c of d.categories.slice().sort((a, b) => b.minutes - a.minutes).slice(0, 5)) {
					lines.push(`  ${c.name}: ${formatHoursMinutes(c.minutes)}`);
				}

				tooltipText.selectAll('tspan').remove();
				for (let i = 0; i < lines.length; i++) {
					tooltipText.append('tspan')
						.attr('x', 8).attr('dy', i === 0 ? 14 : 14)
						.style('font-weight', i === 0 ? '600' : '400')
						.text(lines[i]);
				}

				const bbox = tooltipText.node()!.getBBox();
				const tw = bbox.width + 16;
				const th = bbox.height + 10;
				const tx = Math.min(px + margin.left + 10, width - tw - 5);
				const ty = margin.top + 10;
				tooltipRect.attr('x', tx).attr('y', ty).attr('width', tw).attr('height', th);
				tooltipText.attr('transform', `translate(${tx},${ty})`);
				tooltipG.style('opacity', 1);
			})
			.on('mouseleave', () => {
				tooltipLine.style('opacity', 0);
				tooltipG.style('opacity', 0);
			});

		// Legend
		const legendG = svg.append('g').attr('transform', `translate(${margin.left},${height - 8})`);
		let lx = 0;
		for (const cat of categories.slice(0, 8)) {
			const lg = legendG.append('g').attr('transform', `translate(${lx},0)`);
			lg.append('rect').attr('width', 8).attr('height', 8).attr('rx', 2).attr('fill', colorMap[cat]);
			lg.append('text').attr('x', 12).attr('y', 8).attr('fill', theme.muted)
				.style('font-size', '9px').style('font-family', 'system-ui, sans-serif').text(cat);
			lx += 12 + cat.length * 5.5 + 10;
			if (lx > w - 50) break;
		}

		rendered = true;
	}

	$effect(() => {
		// Re-render when data or timeScale changes
		const _deps = [data, timeScale];
		if (data && svgEl && container) {
			rendered = false;
			requestAnimationFrame(() => render());
		}
	});

	onMount(() => {
		if (container) {
			cleanup = observeResize(container, (w, h) => {
				if (Math.abs(w - width) > 5 || Math.abs(h - height) > 5) {
					width = w;
					height = h;
					rendered = false;
					render();
				}
			});
		}
		return () => cleanup?.();
	});
</script>

<div class="rounded-lg border border-border bg-card p-4">
	<h3 class="mb-2 text-sm font-semibold">Daily Activity</h3>
	<div class="relative" style="height: 300px;" bind:this={container}>
		{#if data.length === 0}
			<div class="flex h-full items-center justify-center text-sm text-muted-foreground">
				No data for selected range
			</div>
		{:else}
			<svg bind:this={svgEl} class="absolute inset-0"></svg>
		{/if}
	</div>
</div>
