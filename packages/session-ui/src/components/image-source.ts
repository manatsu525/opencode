import type { ToolPart } from "@opencode-ai/sdk/v2"
import { marked } from "marked"

/** No file:, javascript:, executable document data, or relative server filesystem paths. */
export function safeImageUrl(value: string): string | undefined {
  if (!value || /[\u0000-\u001f\u007f]/.test(value)) return
  if (/^data:image\/[a-z0-9.+-]+(?:;[^,]*)?,/i.test(value)) return value
  try {
    const url = new URL(value)
    if ((url.protocol === "http:" || url.protocol === "https:") && !url.username && !url.password) return url.href
    if (url.protocol === "blob:") return url.href
  } catch { /* Invalid or incomplete streamed URL. */ }
}

export type ReplyImage = { url: string; alt: string }
export function toolImages(part: ToolPart): ReplyImage[] {
  if (part.state.status !== "completed") return []
  const result: ReplyImage[] = []
  const add = (url: string, alt = "Image") => {
    const safe = safeImageUrl(url)
    if (safe && !result.some((image) => image.url === safe) && result.length < 16) result.push({ url: safe, alt })
  }
  for (const file of part.state.attachments ?? []) {
    if (file.mime.startsWith("image/")) add(file.url, file.filename || "Tool image")
  }
  // Structured FilePart attachments are authoritative. Also accept explicit Markdown
  // images and plain image-file URLs from text-only search/plugin results.
  const output = part.state.output.slice(0, 100000)
  marked.walkTokens(marked.lexer(output), (token) => {
    if (token.type === "image") add(token.href, token.text)
  })
  for (const match of output.matchAll(/https?:\/\/[^\s<>"'`]+\.(?:png|jpe?g|gif|webp|avif|bmp|svg)(?:[?#][^\s<>"'`]*)?/gi)) add(match[0].replace(/[),.;]+$/, ""))
  return result
}
