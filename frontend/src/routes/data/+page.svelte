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

	type Tab = 'sessions' | 'families' | 'overview';

	// Layout: page header (title + actions) → full-width tabs → tab content.
	// The session rail belongs to the Sessions tab only, so Families and the
	// Overview get the whole width. Import and New Session are both modals —
	// creating data never replaces what you were looking at.
	const tabs: { id: Tab; label: string; hint: string }[] = [
		{ id: 'sessions', label: 'Sessions', hint: 'Categories and time per session' },
		{ id: 'families', label: 'Families', hint: 'Projects that span sessions' },
		{ id: 'overview', label: 'Overview', hint: 'Groups → families → categories' },
	];

	let sessions = $state<SessionResponse[]>([]);
	let selectedSession = $state<SessionResponse | null>(null);
	let showImport = $state(false);
	let showNewSession = $state(false);
	let loading = $state(true);
	let tab = $state<Tab>('sessions');
	// Set synchronously by snapshot.restore so the default selection below
	// doesn't race (and override) the session the user had open.
	let restoredSessionId: number | null = null;

	async function loadSessions() {
		loading = true;
		try {
			const data = await api.getSessions();
			sessions = data.sessions;
			// Land on something useful instead of an empty pane: the active
			// session, else the most recent one.
			if (!selectedSession && restoredSessionId == null && sessions.length) {
				const initial = sessions.find((s) => s.is_active) ?? sessions[0];
				selectSession(initial.id);
			}
		} catch (e) {
			console.error('Failed to load sessions:', e);
		}
		loading = false;
	}

	async function selectSession(id: number) {
		try {
			selectedSession = await api.getSession(id);
		} catch (e) {
			console.error('Failed to load session:', e);
		}
	}

	async function handleImportComplete() {
		showImport = false;
		const before = new Set(sessions.map((s) => s.id));
		await loadSessions();
		// Jump to what was just imported (a new session, if one was created).
		const created = sessions.find((s) => !before.has(s.id));
		tab = 'sessions';
		if (created) selectSession(created.id);
		else if (selectedSession) selectSession(selectedSession.id);
	}

	function handleSessionCreated() {
		showNewSession = false;
		const before = new Set(sessions.map((s) => s.id));
		loadSessions().then(() => {
			const created = sessions.find((s) => !before.has(s.id));
			tab = 'sessions';
			if (created) selectSession(created.id);
		});
		loadActiveSession();
	}

	onMount(() => {
		// Deep link: /data?tab=families | overview | sessions
		const requested = new URLSearchParams(window.location.search).get('tab');
		if (requested && tabs.some((t) => t.id === requested)) tab = requested as Tab;
		loadSessions();
	});

	// Preserve which tab + which session were selected across tab navigation.
	// Recovers selectedSession by id so we don't stash a stale full payload.
	export const snapshot = {
		capture: () => ({
			tab,
			selectedSessionId: selectedSession?.id ?? null,
		}),
		restore: async (s: { tab?: Tab; rightTab?: string; selectedSessionId: number | null }) => {
			// `rightTab` is the pre-redesign key; 'groups' became 'overview'.
			const legacy = s.rightTab === 'groups' ? 'overview' : (s.rightTab as Tab | undefined);
			tab = s.tab ?? legacy ?? 'sessions';
			if (s.selectedSessionId != null) {
				restoredSessionId = s.selectedSessionId;
				try {
					selectedSession = await api.getSession(s.selectedSessionId);
				} catch { /* session may have been deleted */ }
			}
		},
	};
</script>

<div class="flex h-full flex-col">
	<!-- Header -->
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold">Data</h1>
			<p class="text-sm text-muted-foreground">Sessions, project families, and imports</p>
		</div>
		<div class="flex gap-2">
			<button
				onclick={() => (showImport = true)}
				class="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
			>
				<svg class="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.75">
					<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
				</svg>
				Import CSV
			</button>
			<button
				onclick={() => (showNewSession = true)}
				class="inline-flex items-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				New Session
			</button>
		</div>
	</div>

	<!-- Tabs -->
	<div class="mt-5 flex shrink-0 items-end gap-6 border-b border-border" role="tablist">
		{#each tabs as t}
			<button
				role="tab"
				aria-selected={tab === t.id}
				title={t.hint}
				onclick={() => (tab = t.id)}
				class="-mb-px flex items-center gap-2 border-b-2 pb-2.5 text-sm font-medium transition-colors
					{tab === t.id
						? 'border-primary text-foreground'
						: 'border-transparent text-muted-foreground hover:text-foreground'}"
			>
				{t.label}
				{#if t.id === 'sessions' && sessions.length}
					<span class="rounded-full bg-muted px-1.5 py-px text-[11px] font-medium tabular-nums text-muted-foreground">
						{sessions.length}
					</span>
				{/if}
			</button>
		{/each}
	</div>

	<!-- Content -->
	<div class="min-h-0 flex-1 pt-5">
		{#if tab === 'sessions'}
			<div class="flex h-full gap-6">
				<aside class="w-72 shrink-0 overflow-y-auto pr-1">
					{#if loading && sessions.length === 0}
						<div class="py-8 text-center text-sm text-muted-foreground">Loading…</div>
					{:else}
						<SessionList
							{sessions}
							selectedId={selectedSession?.id ?? null}
							onSelect={selectSession}
						/>
					{/if}
				</aside>
				<section class="min-w-0 flex-1 overflow-y-auto pb-6">
					{#if selectedSession}
						<SessionDetail
							session={selectedSession}
							onUpdate={() => selectedSession && selectSession(selectedSession.id)}
						/>
					{:else if !loading}
						<div class="flex h-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border text-center">
							<p class="text-sm text-muted-foreground">No sessions yet.</p>
							<p class="text-xs text-muted-foreground">Create one, or import your CSV history.</p>
						</div>
					{/if}
				</section>
			</div>
		{:else if tab === 'families'}
			<div class="h-full overflow-y-auto pb-6">
				<FamilyManager onChanged={loadSessions} />
			</div>
		{:else}
			<BubbleVisualization />
		{/if}
	</div>
</div>

{#if showNewSession}
	<NewSessionDialog
		{sessions}
		onCreated={handleSessionCreated}
		onCancel={() => (showNewSession = false)}
	/>
{/if}

<svelte:window onkeydown={(e) => { if (showImport && e.key === 'Escape') showImport = false; }} />

{#if showImport}
	<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onclick={() => (showImport = false)}>
		<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
		<div
			class="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-border bg-card p-6 shadow-lg"
			onclick={(e) => e.stopPropagation()}
		>
			<ImportDropzone onComplete={handleImportComplete} onCancel={() => (showImport = false)} />
		</div>
	</div>
{/if}
