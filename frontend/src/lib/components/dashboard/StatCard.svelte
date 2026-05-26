<script lang="ts">
	let {
		label,
		value,
		sublabel,
		accent = false,
		icon
	}: {
		label: string;
		value: string;
		sublabel?: string;
		accent?: boolean;
		icon?: string;
	} = $props();
</script>

<div
	class="group relative overflow-hidden rounded-xl border bg-card p-4 transition-all hover:shadow-sm
		{accent ? 'border-primary/20' : 'border-border'}"
>
	{#if accent}
		<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent"></div>
	{/if}
	<div class="relative flex items-start justify-between gap-2">
		<div class="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
		{#if icon}
			<div class="text-muted-foreground/60 transition-colors group-hover:text-muted-foreground">
				{@html icon}
			</div>
		{/if}
	</div>
	<div class="relative mt-1.5 text-2xl font-bold tabular-nums leading-tight">
		{value}
	</div>
	{#if sublabel}
		<div class="relative mt-1 text-xs text-muted-foreground">{sublabel}</div>
	{/if}
</div>
