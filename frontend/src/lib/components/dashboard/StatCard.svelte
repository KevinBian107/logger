<script lang="ts">
	let {
		label,
		value,
		sublabel
	}: {
		label: string;
		value: string;
		sublabel?: string;
	} = $props();
</script>

<div class="rounded-lg border border-border bg-card p-4">
	<div class="text-xs font-medium text-muted-foreground">{label}</div>
	<div class="mt-1 text-2xl font-bold">{value}</div>
	{#if sublabel}
		<div class="mt-0.5 text-xs text-muted-foreground">{sublabel}</div>
	{/if}
</div>
