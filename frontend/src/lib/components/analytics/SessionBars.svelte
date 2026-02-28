<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';
	import type { SessionComparisonItem } from '$lib/api/client';
	import { PALETTE, getThemeColors, observeResize, formatHoursMinutes } from '$lib/utils/chart';

	let { data }: { data: SessionComparisonItem[] } = $props();

	let container = $state<HTMLDivElement | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let width = 800;
	let cleanup: (() => void) | null = null;

	function render() {
		if (!data.length || !svgEl || !container) return;

		const theme = getThemeColors(container);
		const height = 340;
		const margin = { top: 20, right: 20, bottom: 100, left: 50 };
		const w = width - margin.left - margin.right;
		const h = height - margin.top - margin.bottom;

		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();
		svg.attr('width', width).attr('height', height);

		const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

		// Collect all unique group names across sessions
		const allGroups = new Set<string>();
		for (const s of data) {
			for (const gr of s.groups) allGroups.add(gr.name);
		}
		const groupList = [...allGroups];

		// Build color map: prefer the color from the group data, fallback to palette
		const colorMap: Record<string, string> = {};
		let paletteIdx = 0;
		for (const name of groupList) {
			let found: string | null = null;
			for (const s of data) {
				const gr = s.groups.find(g => g.name === name);
				if (gr?.color) { found = gr.color; break; }
			}
			colorMap[name] = found || PALETTE[paletteIdx++ % PALETTE.length];
		}

		// Build stacked data
		const stackData = data.map(s => {
			const row: Record<string, number | string> = { label: s.label };
			for (const name of groupList) row[name] = 0;
			for (const gr of s.groups) {
				row[gr.name] = gr.minutes / 60;
			}
			return row;
		});

		const x = d3.scaleBand()
			.domain(data.map(s => s.label))
			.range([0, w])
			.padding(0.3);

		const stack = d3.stack<Record<string, number | string>>()
			.keys(groupList)
			.value((d, key) => (d[key] as number) || 0)
			.order(d3.stackOrderNone)
			.offset(d3.stackOffsetNone);

		const series = stack(stackData);
		const yMax = d3.max(series, s => d3.max(s, d => d[1])) || 1;
		const y = d3.scaleLinear().domain([0, yMax]).nice().range([h, 0]);

		// Draw stacked bars
		for (let si = 0; si < series.length; si++) {
			const s = series[si];
			g.selectAll(`.bar-g${si}`)
				.data(s)
				.join('rect')
				.attr('class', `bar-g${si}`)
				.attr('x', (_d, i) => x(data[i].label)!)
				.attr('y', d => y(d[1]))
				.attr('height', d => y(d[0]) - y(d[1]))
				.attr('width', x.bandwidth())
				.attr('fill', colorMap[s.key] || '#6B7280')
				.attr('fill-opacity', 0.8)
				.attr('rx', 2);
		}

		// Total labels on top
		for (let i = 0; i < data.length; i++) {
			const s = data[i];
			g.append('text')
				.attr('x', x(s.label)! + x.bandwidth() / 2)
				.attr('y', y(s.total_minutes / 60) - 5)
				.attr('text-anchor', 'middle')
				.attr('fill', theme.muted)
				.style('font-size', '9px')
				.style('font-family', 'system-ui, sans-serif')
				.text(formatHoursMinutes(s.total_minutes));
		}

		// X axis
		g.append('g')
			.attr('transform', `translate(0,${h})`)
			.call(d3.axisBottom(x))
			.call(g => g.select('.domain').attr('stroke', theme.border))
			.call(g => g.selectAll('.tick text')
				.attr('fill', theme.muted)
				.style('font-size', '9px')
				.attr('transform', 'rotate(-30)')
				.attr('text-anchor', 'end'))
			.call(g => g.selectAll('.tick line').attr('stroke', theme.border));

		// Y axis
		g.append('g')
			.call(d3.axisLeft(y).ticks(5).tickFormat(d => `${d}h`))
			.call(g => g.select('.domain').attr('stroke', theme.border))
			.call(g => g.selectAll('.tick text').attr('fill', theme.muted).style('font-size', '10px'))
			.call(g => g.selectAll('.tick line').attr('stroke', theme.border));

		// Legend — placed below x-axis labels
		const legendY = margin.top + h + 70;
		const legendG = svg.append('g').attr('transform', `translate(${margin.left},${legendY})`);
		let lx = 0;
		for (const name of groupList.slice(0, 10)) {
			if (lx + 12 + name.length * 5.5 > w) {
				break;
			}
			const lg = legendG.append('g').attr('transform', `translate(${lx},0)`);
			lg.append('rect').attr('width', 8).attr('height', 8).attr('rx', 2).attr('fill', colorMap[name]);
			lg.append('text').attr('x', 12).attr('y', 8).attr('fill', theme.muted)
				.style('font-size', '9px').style('font-family', 'system-ui, sans-serif').text(name);
			lx += 12 + name.length * 5.5 + 12;
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
	<h3 class="mb-2 text-sm font-semibold">Session Comparison</h3>
	<div class="relative" style="height: 340px;" bind:this={container}>
		{#if data.length === 0}
			<div class="flex h-full items-center justify-center text-sm text-muted-foreground">
				No session data
			</div>
		{:else}
			<svg bind:this={svgEl} class="absolute inset-0"></svg>
		{/if}
	</div>
</div>
