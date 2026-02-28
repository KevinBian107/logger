<script lang="ts">
	import { api, type ImportPreviewResponse } from '$lib/api/client';

	let { onComplete }: { onComplete: () => void } = $props();

	let studyFile = $state<File | null>(null);
	let textFile = $state<File | null>(null);
	let preview = $state<ImportPreviewResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let isDragOver = $state(false);

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		isDragOver = false;
		const files = Array.from(e.dataTransfer?.files ?? []);
		assignFiles(files);
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const files = Array.from(input.files ?? []);
		assignFiles(files);
	}

	function assignFiles(files: File[]) {
		for (const f of files) {
			const name = f.name.toLowerCase();
			if (name.includes('study') && name.endsWith('.csv')) {
				studyFile = f;
			} else if (name.includes('text') && name.endsWith('.csv')) {
				textFile = f;
			}
		}
	}

	async function handlePreview() {
		if (!studyFile) return;
		loading = true;
		error = null;
		try {
			preview = await api.importPreview(studyFile, textFile ?? undefined);
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Preview failed';
		}
		loading = false;
	}

	async function handleConfirm() {
		if (!preview) return;
		loading = true;
		error = null;
		try {
			await api.importConfirm(preview.preview_id);
			onComplete();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Import failed';
		}
		loading = false;
	}

	function reset() {
		studyFile = null;
		textFile = null;
		preview = null;
		error = null;
	}

	function formatHours(minutes: number): string {
		return (minutes / 60).toFixed(1);
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h2 class="text-xl font-semibold">Import CSV Data</h2>
		{#if preview || studyFile}
			<button
				onclick={reset}
				class="text-sm text-muted-foreground hover:text-foreground"
			>
				Reset
			</button>
		{/if}
	</div>

	{#if !preview}
		<!-- Two-file upload -->
		<div class="grid gap-4 sm:grid-cols-2">
			<!-- Study CSV -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors
					{studyFile ? 'border-green-500/50 bg-green-500/5' : isDragOver ? 'border-primary bg-primary/5' : 'border-border'}"
				ondragover={(e) => { e.preventDefault(); isDragOver = true; }}
				ondragleave={() => isDragOver = false}
				ondrop={(e) => { e.preventDefault(); isDragOver = false; const files = Array.from(e.dataTransfer?.files ?? []); for (const f of files) { if (f.name.endsWith('.csv')) { studyFile = f; break; } } }}
			>
				{#if studyFile}
					<svg class="mb-2 h-8 w-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
					<p class="text-sm font-medium">{studyFile.name}</p>
					<button onclick={() => studyFile = null} class="mt-1 text-xs text-muted-foreground hover:text-foreground">Remove</button>
				{:else}
					<svg class="mb-2 h-8 w-8 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M13.125 12h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125M20.625 12c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5M12 14.625v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 14.625c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m0 0v.75" />
					</svg>
					<p class="mb-1 text-sm font-medium">Timesheet CSV</p>
					<p class="mb-2 text-xs text-muted-foreground">e.g. 2024_fall_study.csv</p>
					<label class="cursor-pointer rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90">
						Choose file
						<input type="file" accept=".csv" class="hidden" onchange={(e) => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) studyFile = f; }} />
					</label>
				{/if}
			</div>

			<!-- Text CSV -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors
					{textFile ? 'border-green-500/50 bg-green-500/5' : 'border-border'}"
				ondragover={(e) => { e.preventDefault(); }}
				ondrop={(e) => { e.preventDefault(); const files = Array.from(e.dataTransfer?.files ?? []); for (const f of files) { if (f.name.endsWith('.csv')) { textFile = f; break; } } }}
			>
				{#if textFile}
					<svg class="mb-2 h-8 w-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
					<p class="text-sm font-medium">{textFile.name}</p>
					<button onclick={() => textFile = null} class="mt-1 text-xs text-muted-foreground hover:text-foreground">Remove</button>
				{:else}
					<svg class="mb-2 h-8 w-8 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
					</svg>
					<p class="mb-1 text-sm font-medium">Text/Notes CSV</p>
					<p class="mb-2 text-xs text-muted-foreground">e.g. 2024_fall_text.csv</p>
					<label class="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted">
						Choose file
						<input type="file" accept=".csv" class="hidden" onchange={(e) => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) textFile = f; }} />
					</label>
				{/if}
			</div>
		</div>

		<!-- Combined drag-and-drop hint -->
		<p class="text-center text-xs text-muted-foreground">
			Or drag and drop both files at once
		</p>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="flex items-center justify-center rounded-lg border-2 border-dashed p-4 transition-colors
				{isDragOver ? 'border-primary bg-primary/5' : 'border-border/50'}"
			ondragover={(e) => { e.preventDefault(); isDragOver = true; }}
			ondragleave={() => isDragOver = false}
			ondrop={handleDrop}
		>
			<p class="text-xs text-muted-foreground">
				Drop both CSVs here — filenames with "study" and "text" are auto-detected
			</p>
		</div>

		<!-- Preview button -->
		{#if studyFile}
			<button
				onclick={handlePreview}
				disabled={loading}
				class="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
			>
				{loading ? 'Processing...' : 'Preview Import'}
			</button>
		{/if}
	{:else}
		<!-- Preview -->
		<div class="space-y-4">
			<div class="rounded-lg border border-border bg-card p-5">
				<h3 class="text-lg font-semibold">{preview.session_label}</h3>
				<div class="mt-2 grid grid-cols-2 gap-3 text-sm">
					<div>
						<span class="text-muted-foreground">Date range:</span>
						<span class="ml-1">{preview.date_range[0]} to {preview.date_range[1]}</span>
					</div>
					<div>
						<span class="text-muted-foreground">Days:</span>
						<span class="ml-1">{preview.row_count}</span>
					</div>
					<div>
						<span class="text-muted-foreground">Categories:</span>
						<span class="ml-1">{preview.categories.length}</span>
					</div>
					<div>
						<span class="text-muted-foreground">Text entries:</span>
						<span class="ml-1">{preview.text_row_count}</span>
					</div>
				</div>
			</div>

			<!-- Categories preview -->
			<div class="rounded-lg border border-border">
				<table class="w-full text-sm">
					<thead>
						<tr class="border-b border-border bg-muted/50">
							<th class="px-4 py-2 text-left font-medium text-muted-foreground">Category</th>
							<th class="px-4 py-2 text-left font-medium text-muted-foreground">Auto-linked Family</th>
						</tr>
					</thead>
					<tbody>
						{#each preview.categories as cat}
							<tr class="border-b border-border last:border-0">
								<td class="px-4 py-2">
									<span class="font-medium text-sm">{cat.display_name || cat.name}</span>
									{#if cat.source_columns && cat.source_columns.length > 1}
										<div class="mt-0.5 text-xs text-muted-foreground">
											{cat.source_columns.join(' + ')} &rarr; {cat.display_name || cat.name}
										</div>
									{:else if cat.source_columns && cat.source_columns.length === 1 && cat.source_columns[0] !== cat.name}
										<div class="mt-0.5 text-xs text-muted-foreground">
											{cat.source_columns[0]}
										</div>
									{/if}
								</td>
								<td class="px-4 py-2">
									{#if cat.auto_family}
										<span class="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
											{cat.family_display_name}
											{#if cat.is_new_family}
												<span class="ml-1 text-amber-500">(new)</span>
											{/if}
										</span>
									{:else}
										<span class="text-muted-foreground">—</span>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<!-- Warnings -->
			{#if preview.warnings.length > 0}
				<div class="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950">
					<h4 class="text-sm font-medium text-amber-800 dark:text-amber-200">Warnings</h4>
					<ul class="mt-1 list-inside list-disc text-sm text-amber-700 dark:text-amber-300">
						{#each preview.warnings as warning}
							<li>{warning}</li>
						{/each}
					</ul>
				</div>
			{/if}

			<div class="flex gap-3">
				<button
					onclick={reset}
					class="flex-1 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground hover:bg-muted"
				>
					Cancel
				</button>
				<button
					onclick={handleConfirm}
					disabled={loading}
					class="flex-1 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
				>
					{loading ? 'Importing...' : 'Confirm Import'}
				</button>
			</div>
		</div>
	{/if}

	{#if error}
		<div class="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
			{error}
		</div>
	{/if}
</div>
