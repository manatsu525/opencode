import { createMarkdownParser } from "@opencode-ai/ui/context/marked-parser"
import { describe, expect, test } from "bun:test"
import { closedMermaidFence, mermaidCode, markMermaidToken } from "./mermaid-source"
import { stream } from "./markdown-stream"

describe("Mermaid source eligibility", () => {
  test("accepts closed backtick and tilde fences, including CRLF and a longer closer", () => {
    expect(closedMermaidFence("```mermaid\ngraph LR\nA --> B\n```\n")).toBe(true)
    expect(closedMermaidFence("``` mermaid\nA --> B\n```" )).toBe(true)
    expect(closedMermaidFence("  ~~~~Mermaid  \r\ngraph LR\r\n~~~~~\r\n")).toBe(true)
  })
  test("rejects open, mismatched, short, non-Mermaid, and same-line fences", () => {
    for (const text of ["```mermaid\nA --> B", "```mermaid\nA --> B\n~~~", "````mermaid\nA --> B\n```", "```js\nx\n```", "```mermaid```", "```mermaid"]) {
      expect(closedMermaidFence(text)).toBe(false)
    }
  })
  test("streaming waits for a matching closing fence", () => {
    const open = stream("```mermaid\ngraph LR\nA --> B", true)[0]!
    expect(open.complete).toBeUndefined()
    expect(closedMermaidFence(open.raw)).toBe(false)
    const closed = stream("```mermaid\ngraph LR\nA --> B\n```", true)[0]!
    expect(closed.complete).toBe(true)
    expect(closedMermaidFence(closed.raw)).toBe(true)
  })
  test("escapes source rather than inserting diagram HTML into Markdown", () => {
    expect(mermaidCode('<script>alert(1)</script> & test')).toBe('<pre data-mermaid-complete="true"><code class="language-mermaid">&lt;script&gt;alert(1)&lt;/script&gt; &amp; test</code></pre>\n')
  })
})

describe("Mermaid and marked-shiki integration", () => {
  test("marks closed fences before Shiki changes the token type", async () => {
    let highlights = 0
    const parser = createMarkdownParser(async () => { highlights++; return "<pre>highlighted</pre>" })
    parser.use({ walkTokens: markMermaidToken })
    const html = await parser.parse("## Heading\n\n```mermaid\ngraph LR\nA --> B\n```")
    expect(html).toContain('data-mermaid-complete="true"')
    expect(html).toContain('class="language-mermaid"')
    expect(html).toContain("A --&gt; B")
    expect(highlights).toBe(0)
  })
  test("open Mermaid and ordinary code retain the original Shiki fallback", async () => {
    const languages: string[] = []
    const parser = createMarkdownParser(async (_code, language) => { languages.push(language); return "<pre>highlighted</pre>" })
    parser.use({ walkTokens: markMermaidToken })
    expect(await parser.parse("```mermaid\ngraph LR\nA --> B")).not.toContain("data-mermaid-complete")
    expect(await parser.parse("```python\nprint(1)\n```")).toContain("highlighted")
    expect(languages).toEqual(["mermaid", "python"])
  })
})
