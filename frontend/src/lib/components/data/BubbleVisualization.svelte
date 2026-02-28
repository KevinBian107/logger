<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';
	import { api, type BubbleDataResponse } from '$lib/api/client';
	import { PALETTE } from '$lib/utils/chart';

	let container = $state<HTMLDivElement | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let data = $state<BubbleDataResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Stable dimensions — only updated on actual container resize, debounced
	let stableWidth = 800;
	let stableHeight = 600;
	let resizeTimer: ReturnType<typeof setTimeout> | null = null;
	let rendered = false;

	async function loadData() {
		loading = true;
		error = null;
		try {
			data = await api.getBubbleData();
			// If only "Other" group exists, auto-generate groups first
			if (data && data.groups.length <= 1) {
				await api.autoGenerateGroups();
				data = await api.getBubbleData();
			}
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to load bubble data';
		}
		loading = false;
	}

	function buildHierarchy(resp: BubbleDataResponse) {
		return {
			name: 'root',
			children: resp.groups.map((g, i) => ({
				name: g.name,
				color: g.color || PALETTE[i % PALETTE.length],
				groupId: g.group_id,
				children: g.categories.map((c) => ({
					name: c.name,
					value: c.total_minutes,
					mergeKey: c.merge_key,
					categoryId: c.category_id,
					sessionLabel: c.session_label,
				})),
			})),
		};
	}

	function renderBubbles() {
		if (!data || !svgEl) return;

		const w = stableWidth;
		const h = stableHeight;

		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();
		svg.attr('width', w).attr('height', h).attr('viewBox', `0 0 ${w} ${h}`);

		const hierarchy = buildHierarchy(data);
		const root = d3
			.hierarchy(hierarchy)
			.sum((d: any) => d.value || 0)
			.sort((a, b) => (b.value || 0) - (a.value || 0));

		d3.pack<any>().size([w, h]).padding(6)(root);

		// Tooltip group — rendered last so it's always on top
		const tooltipG = svg.append('g').attr('class', 'tooltip-layer').style('pointer-events', 'none');

		// Read theme colors once from computed styles
		const cs = getComputedStyle(container!);
		const bgColor = cs.getPropertyValue('--color-card').trim() || '#ffffff';
		const fgColor = cs.getPropertyValue('--color-foreground').trim() || '#0f172a';
		const borderColor = cs.getPropertyValue('--color-border').trim() || '#e2e8f0';
		const mutedColor = cs.getPropertyValue('--color-muted-foreground').trim() || '#64748b';

		function showTooltip(cx: number, cy: number, r: number, name: string, hours: string, session: string, group: string) {
			tooltipG.selectAll('*').remove();

			const line1 = `${name}  ·  ${hours}`;
			const line2 = `${session}  ·  ${group}`;
			const ty = cy - r - 10;

			// Measure text widths
			const temp1 = tooltipG.append('text').style('font-size', '12px').style('font-weight', '600').style('font-family', 'system-ui, sans-serif').text(line1);
			const temp2 = tooltipG.append('text').style('font-size', '11px').style('font-family', 'system-ui, sans-serif').text(line2);
			const w1 = (temp1.node() as SVGTextElement).getBBox();
			const w2 = (temp2.node() as SVGTextElement).getBBox();
			temp1.remove();
			temp2.remove();

			const px = 12, py = 8;
			const textW = Math.max(w1.width, w2.width);
			const rw = textW + px * 2;
			const lineH = 18;
			const rh = lineH * 2 + py * 2;

			// Clamp horizontally
			let tx = cx;
			if (tx - rw / 2 < 4) tx = rw / 2 + 4;
			if (tx + rw / 2 > w - 4) tx = w - rw / 2 - 4;

			// Flip below if too close to top
			const finalY = ty - rh < 4 ? cy + r + 10 + rh : ty;

			// Drop shadow
			tooltipG.append('rect')
				.attr('x', tx - rw / 2 + 1)
				.attr('y', finalY - rh + 1)
				.attr('width', rw)
				.attr('height', rh)
				.attr('rx', 8)
				.attr('fill', '#000')
				.attr('opacity', 0.08);

			tooltipG.append('rect')
				.attr('x', tx - rw / 2)
				.attr('y', finalY - rh)
				.attr('width', rw)
				.attr('height', rh)
				.attr('rx', 8)
				.attr('fill', bgColor)
				.attr('stroke', borderColor)
				.attr('stroke-width', 1);

			// Name + hours (bold)
			tooltipG.append('text')
				.attr('x', tx)
				.attr('y', finalY - rh + py + lineH / 2 + 2)
				.attr('text-anchor', 'middle')
				.attr('dominant-baseline', 'central')
				.attr('fill', fgColor)
				.style('font-size', '12px')
				.style('font-weight', '600')
				.style('font-family', 'system-ui, sans-serif')
				.text(line1);

			// Session + group (muted)
			tooltipG.append('text')
				.attr('x', tx)
				.attr('y', finalY - rh + py + lineH + lineH / 2 + 2)
				.attr('text-anchor', 'middle')
				.attr('dominant-baseline', 'central')
				.attr('fill', mutedColor)
				.style('font-size', '11px')
				.style('font-family', 'system-ui, sans-serif')
				.text(line2);
		}

		function hideTooltip() {
			tooltipG.selectAll('*').remove();
		}

		const groups = root.children || [];
		for (const group of groups) {
			const groupColor = (group.data as any).color || '#6B7280';

			// Group bubble
			svg.append('circle')
				.attr('cx', group.x!)
				.attr('cy', group.y!)
				.attr('r', group.r!)
				.attr('fill', groupColor)
				.attr('fill-opacity', 0.06)
				.attr('stroke', groupColor)
				.attr('stroke-opacity', 0.25)
				.attr('stroke-width', 1);

			// Group label at top of group circle
			svg.append('text')
				.attr('x', group.x!)
				.attr('y', group.y! - group.r! + 14)
				.attr('text-anchor', 'middle')
				.attr('fill', groupColor)
				.attr('opacity', 0.6)
				.style('font-size', '11px')
				.style('font-weight', '600')
				.style('pointer-events', 'none')
				.text((group.data as any).name);

			// Category circles — clean, label on hover only
			const children = group.children || [];
			for (const cat of children) {
				const catData = cat.data as any;
				const hours = (catData.value / 60).toFixed(1) + 'h';
				const groupName = (group.data as any).name;
				const session = catData.sessionLabel || '';
				const cx = cat.x!;
				const cy = cat.y!;
				const cr = cat.r!;

				svg.append('circle')
					.attr('cx', cx)
					.attr('cy', cy)
					.attr('r', cr)
					.attr('fill', groupColor)
					.attr('fill-opacity', 0.45)
					.attr('stroke', groupColor)
					.attr('stroke-opacity', 0.7)
					.attr('stroke-width', 1)
					.style('cursor', 'pointer')
					.style('transition', 'fill-opacity 0.15s, stroke-width 0.15s')
					.on('mouseenter', function () {
						d3.select(this).attr('fill-opacity', 0.8).attr('stroke-width', 2.5);
						showTooltip(cx, cy, cr, catData.name, hours, session, groupName);
					})
					.on('mouseleave', function () {
						d3.select(this).attr('fill-opacity', 0.45).attr('stroke-width', 1);
						hideTooltip();
					});
			}
		}

		// Re-append tooltip layer so it's always on top of all circles
		tooltipG.raise();

		rendered = true;
	}

	function measureAndRender() {
		if (!container || !data) return;
		const rect = container.getBoundingClientRect();
		const w = Math.floor(rect.width);
		const h = Math.floor(rect.height);
		if (w < 100 || h < 100) return;

		// Only re-render if size actually changed meaningfully (>5px)
		if (rendered && Math.abs(w - stableWidth) < 5 && Math.abs(h - stableHeight) < 5) return;

		stableWidth = w;
		stableHeight = h;
		renderBubbles();
	}

	// When data arrives, render once
	$effect(() => {
		if (data && svgEl && container) {
			rendered = false;
			// Tick so container has layout dimensions
			requestAnimationFrame(() => measureAndRender());
		}
	});

	onMount(() => {
		loadData();

		const observer = new ResizeObserver(() => {
			// Debounce resize to avoid glitchy re-renders
			if (resizeTimer) clearTimeout(resizeTimer);
			resizeTimer = setTimeout(() => measureAndRender(), 200);
		});

		// Observe after a tick so container is bound
		requestAnimationFrame(() => {
			if (container) observer.observe(container);
		});

		return () => {
			observer.disconnect();
			if (resizeTimer) clearTimeout(resizeTimer);
		};
	});
</script>

<div class="flex h-full flex-col">
	<div class="mb-3 flex items-center justify-between">
		<h3 class="text-lg font-semibold">Category Groups</h3>
		<button
			onclick={loadData}
			class="text-sm text-muted-foreground hover:text-foreground"
		>
			Refresh
		</button>
	</div>

	{#if loading}
		<div class="flex flex-1 items-center justify-center text-sm text-muted-foreground">
			Loading visualization...
		</div>
	{:else if error}
		<div class="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
			{error}
		</div>
	{:else if data && data.groups.length === 0}
		<div class="flex flex-1 flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground">
			<p>No groups found. Import data and generate groups first.</p>
			<button
				onclick={async () => {
					try {
						await api.autoGenerateGroups();
						loadData();
					} catch (e: unknown) {
						error = e instanceof Error ? e.message : 'Failed to generate groups';
					}
				}}
				class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
			>
				Auto-Generate Groups
			</button>
		</div>
	{:else}
		<div class="relative" style="height: calc(100vh - 10rem);" bind:this={container}>
			<svg bind:this={svgEl} class="absolute inset-0"></svg>
		</div>
	{/if}
</div>
