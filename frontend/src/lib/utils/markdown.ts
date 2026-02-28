/**
 * Lightweight regex-based markdown to HTML converter.
 * Supports: headers, bold, italic, inline code, code blocks, lists, line breaks.
 * Output is sanitized (no raw HTML passthrough).
 */

function escapeHtml(text: string): string {
	return text
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

export function renderMarkdown(md: string): string {
	// Escape HTML first
	let html = escapeHtml(md);

	// Code blocks (``` ... ```)
	html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
		return `<pre class="md-code-block"><code>${code.trim()}</code></pre>`;
	});

	// Inline code
	html = html.replace(/`([^`\n]+)`/g, '<code class="md-inline-code">$1</code>');

	// Headers (### before ## before #)
	html = html.replace(/^#### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
	html = html.replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>');
	html = html.replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>');
	html = html.replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>');

	// Bold + italic
	html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
	// Bold
	html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
	// Italic
	html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

	// Unordered lists
	html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
	// Wrap consecutive <li> in <ul>
	html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul class="md-list">$1</ul>');

	// Ordered lists
	html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

	// Line breaks (double newline = paragraph break)
	html = html.replace(/\n\n/g, '</p><p>');
	// Single newlines within paragraphs
	html = html.replace(/\n/g, '<br>');

	// Wrap in paragraph tags
	html = `<p>${html}</p>`;

	// Clean up empty paragraphs
	html = html.replace(/<p>\s*<\/p>/g, '');
	// Don't wrap block elements in <p>
	html = html.replace(/<p>(<(?:h[1-4]|pre|ul|ol))/g, '$1');
	html = html.replace(/(<\/(?:h[1-4]|pre|ul|ol)>)<\/p>/g, '$1');

	return html;
}
