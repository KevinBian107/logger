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
	// The panel is a fixed-height viewport that the full bar list scrolls inside,
	// so every category is reachable without the list shoving the charts below it
	// off the page. It shrinks to fit when there are only a few categories.
	const MAX_VIEWPORT_H = 420;

	// Full rendered height of the bar list, for the scroll affordance in the header.
	let contentHeight = $state(0);
	const scrollable = $derived(contentHeight > MAX_VIEWPORT_H);

	function render() {
		if (!data.length || !svgEl || !container) return;

		const theme = getThemeColors(container);
		const items = data;
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

		// Hug the content until it outgrows the viewport, then cap it and let the
		// container scroll (it carries overflow-y: auto).
		contentHeight = h;
		if (container) {
			container.style.height = `${Math.min(h, MAX_VIEWPORT_H)}px`;
		}
	}

	$effect(() => {
		if (!container) return;
		if (data.length === 0) {
			// Nothing to draw — drop the cached viewport height so the empty state
			// doesn't sit inside a 420px void left over from the previous range.
			contentHeight = 0;
			container.style.height = '';
			return;
		}
		if (svgEl) requestAnimationFrame(() => render());
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
	<div class="mb-2 flex items-baseline justify-between gap-3">
		<h3 class="text-sm font-semibold">Category Breakdown</h3>
		{#if data.length > 0}
			<span class="text-xs text-muted-foreground">
				{data.length} categor{data.length === 1 ? 'y' : 'ies'}{scrollable ? ' · scroll for more' : ''}
			</span>
		{/if}
	</div>
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
