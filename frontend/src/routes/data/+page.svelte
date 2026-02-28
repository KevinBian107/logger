<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type SessionResponse } from '$lib/api/client';
	import { loadActiveSession } from '$lib/stores/session';
	import SessionList from '$lib/components/data/SessionList.svelte';
	import SessionDetail from '$lib/components/data/SessionDetail.svelte';
	import ImportDropzone from '$lib/components/data/ImportDropzone.svelte';
	import NewSessionDialog from '$lib/components/data/NewSessionDialog.svelte';
	import BubbleVisualization from '$lib/components/data/BubbleVisualization.svelte';
	import FamilyManager from '$lib/components/data/FamilyManager.svelte';

	let sessions = $state<SessionResponse[]>([]);
	let selectedSession = $state<SessionResponse | null>(null);
	let showImport = $state(false);
	let showNewSession = $state(false);
	let loading = $state(true);
	let rightTab = $state<'sessions' | 'groups' | 'families'>('sessions');

	async function loadSessions() {
		loading = true;
		try {
			const data = await api.getSessions();
			sessions = data.sessions;
		} catch (e) {
			console.error('Failed to load sessions:', e);
		}
		loading = false;
	}

	async function selectSession(id: number) {
		showImport = false;
		rightTab = 'sessions';
		try {
			selectedSession = await api.getSession(id);
		} catch (e) {
			console.error('Failed to load session:', e);
		}
	}

	function handleImportComplete() {
		showImport = false;
		loadSessions();
	}

	function handleSessionCreated() {
		showNewSession = false;
		loadSessions();
		loadActiveSession();
	}

	onMount(loadSessions);
</script>

<div class="flex h-full">
	<!-- Left panel: Session list -->
	<div class="shrink-0 space-y-3 border-r border-border" style="width: 320px; padding-right: 24px; margin-right: 48px;">
		<div class="flex items-center justify-between">
			<h1 class="text-2xl font-bold">Data</h1>
		</div>

		<div class="flex gap-2">
			<button
				onclick={() => { showNewSession = true; }}
				class="flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				New Session
			</button>
			<button
				onclick={() => { showImport = true; selectedSession = null; rightTab = 'sessions'; }}
				class="flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
				</svg>
				Import CSV
			</button>
		</div>

		{#if loading}
			<div class="py-8 text-center text-sm text-muted-foreground">Loading...</div>
		{:else}
			<SessionList
				{sessions}
				selectedId={selectedSession?.id ?? null}
				onSelect={selectSession}
			/>
		{/if}
	</div>

	<!-- Right panel: Detail / Import / Groups -->
	<div class="flex min-h-0 flex-1 flex-col">
		<!-- Tab bar -->
		<div class="mb-4 flex shrink-0 gap-1 rounded-lg bg-muted p-1">
			<button
				onclick={() => rightTab = 'sessions'}
				class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors
					{rightTab === 'sessions' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}"
			>
				Sessions
			</button>
			<button
				onclick={() => rightTab = 'groups'}
				class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors
					{rightTab === 'groups' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}"
			>
				Groups
			</button>
			<button
				onclick={() => rightTab = 'families'}
				class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors
					{rightTab === 'families' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}"
			>
				Families
			</button>
		</div>

		<div class="min-h-0 flex-1 {rightTab === 'groups' ? '' : 'overflow-y-auto'}">
			{#if rightTab === 'families'}
				<FamilyManager onChanged={loadSessions} />
			{:else if rightTab === 'groups'}
				<BubbleVisualization />
			{:else if showImport}
				<ImportDropzone onComplete={handleImportComplete} />
			{:else if selectedSession}
				<SessionDetail session={selectedSession} onUpdate={() => selectedSession && selectSession(selectedSession.id)} />
			{:else}
				<div class="flex h-full items-center justify-center text-muted-foreground">
					Select a session to view details, or import CSV data.
				</div>
			{/if}
		</div>
	</div>
</div>

{#if showNewSession}
	<NewSessionDialog
		{sessions}
		onCreated={handleSessionCreated}
		onCancel={() => showNewSession = false}
	/>
{/if}
