<script lang="ts">
	/**
	 * Notion-style "/" block editor for a plan item's notes. Stored as plain
	 * Markdown-ish text in the existing `notes` string column (no schema
	 * change) — each line round-trips to/from a typed block via a fixed set of
	 * prefixes, so any legacy plain-paragraph notes parse losslessly as a
	 * sequence of `text` blocks with no migration.
	 *
	 * Deliberately one native <input>/<textarea> per row rather than a single
	 * contenteditable region: Svelte's bind:value has no cursor-jump risk,
	 * whereas reconciling framework reactivity against a live contenteditable
	 * region is a well-known source of bugs.
	 */
	import { tick } from 'svelte';

	type BlockType = 'text' | 'h1' | 'h2' | 'bullet' | 'number' | 'todo' | 'divider';
	type Block = { id: number; type: BlockType; text: string; checked?: boolean };

	let { value, onChange }: { value: string; onChange: (v: string) => void } = $props();

	let nextId = 0;
	function makeBlock(type: BlockType = 'text', text = '', checked?: boolean): Block {
		return { id: nextId++, type, text, checked };
	}

	function parse(raw: string): Block[] {
		if (!raw || raw.trim() === '') return [makeBlock()];
		return raw.split('\n').map((line) => {
			let m: RegExpExecArray | null;
			if ((m = /^# (.*)$/.exec(line))) return makeBlock('h1', m[1]);
			if ((m = /^## (.*)$/.exec(line))) return makeBlock('h2', m[1]);
			if ((m = /^- \[x\] (.*)$/i.exec(line))) return makeBlock('todo', m[1], true);
			if ((m = /^- \[ \] (.*)$/.exec(line))) return makeBlock('todo', m[1], false);
			if ((m = /^- (.*)$/.exec(line))) return makeBlock('bullet', m[1]);
			if ((m = /^\d+\.\s(.*)$/.exec(line))) return makeBlock('number', m[1]);
			if (line === '---') return makeBlock('divider');
			return makeBlock('text', line);
		});
	}

	function serialize(bs: Block[]): string {
		return bs
			.map((b) => {
				switch (b.type) {
					case 'h1': return `# ${b.text}`;
					case 'h2': return `## ${b.text}`;
					case 'bullet': return `- ${b.text}`;
					case 'number': return `1. ${b.text}`;
					case 'todo': return `- [${b.checked ? 'x' : ' '}] ${b.text}`;
					case 'divider': return '---';
					default: return b.text;
				}
			})
			.join('\n');
	}

	let blocks = $state<Block[]>(parse(value));
	let elMap: Record<number, HTMLInputElement | HTMLTextAreaElement> = {};
	let lastSerialized = serialize(blocks);

	function commit() {
		const out = serialize(blocks);
		if (out !== lastSerialized) {
			lastSerialized = out;
			onChange(out);
		}
	}

	// `tick()`, not queueMicrotask — a block-type swap (e.g. h1 -> text) or a
	// freshly-spliced-in block destroys/creates a different DOM element, and
	// only `tick()` guarantees Svelte has actually flushed that to the DOM
	// before we try to focus it. A raw queueMicrotask can win the race against
	// Svelte's own render and focus a stale/not-yet-existing element.
	async function focusBlock(id: number, atStart = false) {
		await tick();
		const el = elMap[id];
		if (!el) return;
		el.focus();
		const pos = atStart ? 0 : el.value.length;
		el.setSelectionRange?.(pos, pos);
	}

	// `keywords` covers the natural typed trigger (e.g. "/todo") even where it
	// doesn't literally substring-match the display label (e.g. "To-do list"
	// has a hyphen "/todo" doesn't) — matched against label OR any keyword.
	const BLOCK_TYPES: { type: BlockType; label: string; hint: string; keywords: string[] }[] = [
		{ type: 'text', label: 'Text', hint: 'Plain paragraph', keywords: ['paragraph', 'p'] },
		{ type: 'h1', label: 'Heading 1', hint: 'Big section heading', keywords: ['heading1', 'h1', 'title'] },
		{ type: 'h2', label: 'Heading 2', hint: 'Smaller heading', keywords: ['heading2', 'h2', 'subheading'] },
		{ type: 'todo', label: 'To-do list', hint: 'Checkbox item', keywords: ['todo', 'to-do', 'task', 'check', 'checkbox'] },
		{ type: 'bullet', label: 'Bulleted list', hint: 'Simple bullet point', keywords: ['bullet', 'ul', 'list'] },
		{ type: 'number', label: 'Numbered list', hint: 'Ordered item', keywords: ['number', 'numbered', 'ol', 'ordered'] },
		{ type: 'divider', label: 'Divider', hint: 'A horizontal line', keywords: ['divider', 'hr', 'line', 'separator'] },
	];

	let slashMenu = $state<{ blockId: number; query: string; highlighted: number } | null>(null);
	const filteredTypes = $derived.by(() => {
		if (!slashMenu) return [];
		const q = slashMenu.query.toLowerCase();
		if (q === '') return BLOCK_TYPES;
		return BLOCK_TYPES.filter(
			(t) => t.label.toLowerCase().includes(q) || t.keywords.some((k) => k.includes(q))
		);
	});

	// Running display number for consecutive `number` blocks — the stored
	// serialization always writes "1." per line, so this is recomputed fresh
	// from the current block order rather than tracked as separate state.
	function displayNumber(index: number): number {
		let n = 1;
		for (let i = index - 1; i >= 0 && blocks[i].type === 'number'; i--) n++;
		return n;
	}

	function detectSlash(block: Block, e: Event) {
		const text = (e.currentTarget as HTMLInputElement | HTMLTextAreaElement).value;
		if (block.type === 'text' && text.startsWith('/')) {
			slashMenu = { blockId: block.id, query: text.slice(1), highlighted: 0 };
		} else if (slashMenu?.blockId === block.id) {
			slashMenu = null;
		}
	}

	function selectBlockType(block: Block, type: BlockType | undefined) {
		if (!type) return;
		const idx = blocks.findIndex((b) => b.id === block.id);
		block.text = '';
		block.type = type;
		block.checked = type === 'todo' ? false : undefined;
		slashMenu = null;
		if (type === 'divider') {
			const fresh = makeBlock('text');
			blocks.splice(idx + 1, 0, fresh);
			focusBlock(fresh.id);
		} else {
			focusBlock(block.id);
		}
		commit();
	}

	function insertAfter(index: number, block: Block) {
		blocks.splice(index + 1, 0, block);
		focusBlock(block.id);
		commit();
	}

	function removeAt(index: number) {
		blocks.splice(index, 1);
		commit();
	}

	function handleKeydown(e: KeyboardEvent, block: Block, index: number) {
		if (slashMenu?.blockId === block.id) {
			if (e.key === 'ArrowDown') {
				e.preventDefault();
				slashMenu = { ...slashMenu, highlighted: Math.min(slashMenu.highlighted + 1, filteredTypes.length - 1) };
				return;
			}
			if (e.key === 'ArrowUp') {
				e.preventDefault();
				slashMenu = { ...slashMenu, highlighted: Math.max(slashMenu.highlighted - 1, 0) };
				return;
			}
			if (e.key === 'Enter') {
				e.preventDefault();
				const picked = filteredTypes[slashMenu.highlighted]?.type;
				// No match (e.g. the query doesn't correspond to any block type) —
				// don't silently eat the Enter, just close the menu and fall
				// through to normal Enter/new-block handling below.
				if (!picked) { slashMenu = null; }
				else { selectBlockType(block, picked); return; }
			} else if (e.key === 'Escape') {
				e.preventDefault();
				slashMenu = null;
				return;
			} else {
				return;
			}
		}

		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			if (block.type === 'bullet' || block.type === 'number' || block.type === 'todo') {
				if (block.text.trim() === '') {
					block.type = 'text';
					block.checked = undefined;
					focusBlock(block.id);
					commit();
					return;
				}
				insertAfter(index, makeBlock(block.type, '', block.type === 'todo' ? false : undefined));
			} else {
				insertAfter(index, makeBlock('text'));
			}
			return;
		}

		if (e.key === 'Backspace') {
			const el = e.currentTarget as HTMLInputElement | HTMLTextAreaElement;
			if (el.selectionStart !== 0 || el.selectionEnd !== 0) return;
			if (block.type !== 'text') {
				e.preventDefault();
				block.type = 'text';
				block.checked = undefined;
				focusBlock(block.id);
				commit();
				return;
			}
			if (block.text === '' && index > 0) {
				e.preventDefault();
				removeAt(index);
				focusBlock(blocks[index - 1].id);
			}
		}
	}

	function autoGrow(node: HTMLTextAreaElement) {
		const resize = () => {
			node.style.height = 'auto';
			node.style.height = `${node.scrollHeight}px`;
		};
		resize();
		node.addEventListener('input', resize);
		return { destroy: () => node.removeEventListener('input', resize) };
	}

	function onWindowClick(e: MouseEvent) {
		if (!slashMenu) return;
		if (!(e.target as HTMLElement).closest('.notes-editor-root')) slashMenu = null;
	}
</script>

<svelte:window onclick={onWindowClick} />

<div class="notes-editor-root space-y-0.5">
	{#each blocks as block, index (block.id)}
		<div class="relative">
			{#if block.type === 'divider'}
				<hr class="my-2 border-border" />
			{:else}
				<div class="flex items-start gap-2 rounded px-1.5 py-0.5 hover:bg-muted/40">
					{#if block.type === 'todo'}
						<input
							type="checkbox"
							checked={block.checked}
							onchange={(e) => { block.checked = (e.currentTarget as HTMLInputElement).checked; commit(); }}
							class="mt-1.5 h-3.5 w-3.5 shrink-0 rounded border-border text-primary focus:ring-primary"
						/>
					{:else if block.type === 'bullet'}
						<span class="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground"></span>
					{:else if block.type === 'number'}
						<span class="mt-0.5 w-4 shrink-0 text-right text-sm tabular-nums text-muted-foreground">{displayNumber(index)}.</span>
					{/if}

					{#if block.type === 'text'}
						<textarea
							bind:this={elMap[block.id]}
							use:autoGrow
							rows="1"
							value={block.text}
							oninput={(e) => { block.text = (e.currentTarget as HTMLTextAreaElement).value; detectSlash(block, e); }}
							onkeydown={(e) => handleKeydown(e, block, index)}
							onblur={commit}
							placeholder={index === 0 ? "Add notes… type “/” for headings, lists, to-dos" : ''}
							class="min-w-0 flex-1 resize-none overflow-hidden border-none bg-transparent py-0.5 text-sm leading-relaxed placeholder:text-muted-foreground/70 focus:outline-none"
						></textarea>
					{:else}
						<input
							bind:this={elMap[block.id]}
							type="text"
							value={block.text}
							oninput={(e) => { block.text = (e.currentTarget as HTMLInputElement).value; detectSlash(block, e); }}
							onkeydown={(e) => handleKeydown(e, block, index)}
							onblur={commit}
							class="min-w-0 flex-1 border-none bg-transparent py-0.5 focus:outline-none
								{block.type === 'h1' ? 'text-xl font-bold' : ''}
								{block.type === 'h2' ? 'text-lg font-semibold' : ''}
								{block.type === 'todo' && block.checked ? 'text-muted-foreground line-through' : ''}
								{block.type === 'bullet' || block.type === 'number' || block.type === 'todo' ? 'text-sm' : ''}"
						/>
					{/if}
				</div>
			{/if}

			{#if slashMenu?.blockId === block.id}
				<div class="absolute left-6 top-full z-30 mt-1 w-60 rounded-xl border border-border bg-card p-1.5 shadow-2xl">
					{#if filteredTypes.length === 0}
						<p class="px-2 py-2 text-xs text-muted-foreground">No matching block type</p>
					{:else}
						{#each filteredTypes as t, i}
							<button
								type="button"
								onclick={() => selectBlockType(block, t.type)}
								onmouseenter={() => (slashMenu = { ...slashMenu!, highlighted: i })}
								class="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm {i === slashMenu.highlighted ? 'bg-muted' : ''}"
							>
								<span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-background text-[11px] font-semibold text-muted-foreground">
									{#if t.type === 'text'}¶{:else if t.type === 'h1'}H1{:else if t.type === 'h2'}H2{:else if t.type === 'todo'}☑{:else if t.type === 'bullet'}•{:else if t.type === 'number'}1.{:else}—{/if}
								</span>
								<span class="min-w-0 flex-1">
									<span class="block font-medium">{t.label}</span>
									<span class="block truncate text-xs text-muted-foreground">{t.hint}</span>
								</span>
							</button>
						{/each}
					{/if}
				</div>
			{/if}
		</div>
	{/each}
</div>
