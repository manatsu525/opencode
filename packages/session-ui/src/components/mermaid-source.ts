/** A closed fence only: never turn a partially streamed diagram into an error SVG. */
export function closedMermaidFence(raw: string): boolean {
  const lines = raw.replace(/\r\n?/g, "\n").trimEnd().split("\n")
  if (lines.length < 2) return false
  const opening = lines[0]?.match(/^[ \t]{0,3}(`{3,}|~{3,})[ \t]*mermaid[ \t]*$/i)?.[1]
  if (!opening) return false
  return new RegExp(`^[ \\t]{0,3}${opening[0]}{${opening.length},}[ \\t]*$`).test(lines.at(-1) ?? "")
}

export function mermaidCode(source: string): string {
  const safe = source.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  return `<pre data-mermaid-complete="true"><code class="language-mermaid">${safe}</code></pre>\n`
}
