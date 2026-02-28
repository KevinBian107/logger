<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/layout/Sidebar.svelte';
	import TopBar from '$lib/components/layout/TopBar.svelte';
	import { loadSessions, loadActiveSession } from '$lib/stores/session';
	import { onMount } from 'svelte';

	let { children } = $props();

	onMount(() => {
		loadSessions();
		loadActiveSession();
	});
</script>

<div class="flex h-screen overflow-hidden">
	<Sidebar />
	<div class="flex flex-1 flex-col overflow-hidden">
		<TopBar />
		<main class="flex-1 overflow-y-auto bg-background p-6">
			{@render children()}
		</main>
	</div>
</div>
