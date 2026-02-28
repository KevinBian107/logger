<script lang="ts">
	let {
		onSend,
		disabled = false
	}: {
		onSend: (message: string) => void;
		disabled?: boolean;
	} = $props();

	let value = $state('');
	let textarea: HTMLTextAreaElement;

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			submit();
		}
	}

	function submit() {
		const trimmed = value.trim();
		if (!trimmed || disabled) return;
		onSend(trimmed);
		value = '';
		// Reset height
		if (textarea) textarea.style.height = 'auto';
	}

	function autoResize() {
		if (!textarea) return;
		textarea.style.height = 'auto';
		textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
	}
</script>

<div class="border-t border-border bg-background p-4">
	<div class="mx-auto flex max-w-3xl items-end gap-2">
		<textarea
			bind:this={textarea}
			bind:value
			oninput={autoResize}
			onkeydown={handleKeydown}
			{disabled}
			placeholder={disabled ? 'Configure API key in Settings to start chatting' : 'Ask about your productivity data...'}
			rows="1"
			class="flex-1 resize-none rounded-xl border border-input bg-background px-4 py-2.5 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
		></textarea>
		<button
			onclick={submit}
			disabled={disabled || !value.trim()}
			class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
			</svg>
		</button>
	</div>
</div>
