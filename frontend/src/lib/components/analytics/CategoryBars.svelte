<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';
	import type { CategoryBreakdownItem } from '$lib/api/client';
	import { PALETTE, getThemeColors, observeResize, formatHoursMinutes } from '$lib/utils/chart';

	let { data }: { data: CategoryBreakdownItem[] } = $props();

	let container = $state<HTMLDivElement | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let width = 400;
	let cleanup: (() => void) | null = null;

	const BAR_HEIGHT = 28;
	const GAP = 4;
	const MAX_BARS = 15;

	function render() {
		if (!data.length || !svgEl || !container) return;

		const theme = getThemeColors(container);
		const items = data.slice(0, MAX_BARS);
		const margin = { top: 4, right: 60, bottom: 4, left: 200 };
		const h = items.length * (BAR_HEIGHT + GAP) + margin.top + margin.bottom;
		const w = width - margin.left - margin.right;

		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();
		svg.attr('width', width).attr('height', h);

		const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

		const maxMins = d3.max(items, d => d.total_minutes) || 1;
		const x = d3.scaleLinear().domain([0, maxMins]).range([0, w]);

		for (let i = 0; i < items.length; i++) {
			const d = items[i];
			const y = i * (BAR_HEIGHT + GAP);
			const color = d.color || PALETTE[i % PALETTE.length];
			const barW = x(d.total_minutes);

			// Label (category name + session)
			const labelText = g.append('text')
				.attr('x', -8)
				.attr('y', y + BAR_HEIGHT / 2)
				.attr('text-anchor', 'end')
				.attr('dominant-baseline', 'central')
				.style('font-size', '11px')
				.style('font-family', 'system-ui, sans-serif');

			labelText.append('tspan')
				.attr('fill', theme.fg)
				.text((d.display_name || d.name).slice(0, 18));

			if (d.session_label) {
				labelText.append('tspan')
					.attr('fill', theme.muted)
					.style('font-size', '9px')
					.text(` ${d.session_label}`);
			}

			// Bar
			g.append('rect')
				.attr('x', 0)
				.attr('y', y)
				.attr('width', barW)
				.attr('height', BAR_HEIGHT)
				.attr('rx', 4)
				.attr('fill', color)
				.attr('fill-opacity', 0.7);

			// Value
			g.append('text')
				.attr('x', barW + 6)
				.attr('y', y + BAR_HEIGHT / 2)
				.attr('dominant-baseline', 'central')
				.attr('fill', theme.muted)
				.style('font-size', '10px')
				.style('font-family', 'system-ui, sans-serif')
				.text(formatHoursMinutes(d.total_minutes));
		}

		// Set the container to actual height
		if (container) {
			container.style.height = `${h}px`;
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
	<h3 class="mb-2 text-sm font-semibold">Category Breakdown</h3>
	<div class="relative overflow-y-auto" style="min-height: 100px;" bind:this={container}>
		{#if data.length === 0}
			<div class="flex h-24 items-center justify-center text-sm text-muted-foreground">
				No category data
			</div>
		{:else}
			<svg bind:this={svgEl}></svg>
		{/if}
	</div>
</div>
