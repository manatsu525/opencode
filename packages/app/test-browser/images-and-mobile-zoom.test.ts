import { afterEach, describe, expect, mock, test } from "bun:test"
import { readFileSync } from "node:fs"
import { setupInlineImages } from "../../session-ui/src/components/inline-images"
import { safeImageUrl, toolImages } from "../../session-ui/src/components/image-source"

import { openMediaViewer } from "../../session-ui/src/components/mermaid-viewer"
import { setupPageZoomGuard } from "../src/utils/page-zoom"
import type { ToolPart } from "@opencode-ai/sdk/v2"

mock.module("../../session-ui/src/components/markdown.worker.ts?worker&url", () => ({ default: "/test-worker.js" }))
const { sanitizeMarkdown } = await import("../../session-ui/src/components/markdown-cache")

const cleanups: Array<() => void> = []
afterEach(() => { cleanups.splice(0).reverse().forEach((fn) => fn()); document.body.innerHTML = "" })

describe("safe inline images", () => {
  test("accepts only image-compatible schemes without credentials", () => {
    for (const url of ["https://example.com/a.jpg", "http://example.com/a.png", "data:image/png;base64,AAAA", "data:image/svg+xml,<svg></svg>", "blob:https://example.com/123"]) expect(safeImageUrl(url)).toBeDefined()
    for (const url of ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,<script>x</script>", "https://user:secret@example.com/a.png", "/etc/image.png", "https://example.com/\nimage.png"]) expect(safeImageUrl(url)).toBeUndefined()
  })
  test("Markdown sanitizer prepares lazy no-referrer images and removes unsafe attributes", () => {
    const root = document.createElement("div")
    root.innerHTML = sanitizeMarkdown('<img src="https://example.com/a.jpg" srcset="https://example.com/b.jpg 2x" onerror="alert(1)">')
    const img = root.querySelector("img")!
    expect(img.getAttribute("src")).toBe("https://example.com/a.jpg")
    expect(img.getAttribute("referrerpolicy")).toBe("no-referrer")
    expect(img.getAttribute("loading")).toBe("lazy")
    expect(img.getAttribute("srcset")).toBeNull()
    expect(img.getAttribute("onerror")).toBeNull()
    root.innerHTML = sanitizeMarkdown('<img src="javascript:alert(1)">')
    expect(root.querySelector("img")?.getAttribute("src")).toBeNull()
  })
  test("broken URLs become source links; broken data images never become navigation links", () => {
    const root = document.createElement("div")
    root.innerHTML = '<img src="https://example.com/a.jpg" alt="Landscape"><img src="data:image/png;base64,AAAA" alt="Embedded">'
    document.body.append(root); cleanups.push(setupInlineImages(root))
    root.querySelectorAll("img").forEach((img) => img.dispatchEvent(new Event("error")))
    expect(root.querySelector("a")?.href).toBe("https://example.com/a.jpg")
    expect(root.querySelector("a")?.rel).toBe("noopener noreferrer")
    expect(root.querySelectorAll("a").length).toBe(1)
    expect(root.querySelector("span[data-image-fallback]")?.textContent).toContain("Embedded")
  })
  test("click reuses the media modal and restores the same image", () => {
    const root = document.createElement("div")
    root.innerHTML = '<img src="https://example.com/a.jpg" alt="Landscape">'
    document.body.append(root); cleanups.push(setupInlineImages(root))
    const img = root.querySelector("img")!; img.click()
    expect(document.querySelector('[data-media-viewer="image"] img')).toBe(img)
    expect(document.querySelectorAll("img").length).toBe(1)
    document.querySelector<HTMLButtonElement>('button[aria-label="Close"]')!.click()
    expect(root.querySelector("img")).toBe(img)
  })
  test("tool FilePart attachments render; image_search output Markdown images and image URLs render", () => {
    const part = { type: "tool", tool: "image_search_search_images", state: { status: "completed", output: "![remote](https://example.com/no-extension?id=1) https://example.com/photo.jpg", attachments: [{ type: "file", mime: "text/plain", url: "file:///secret.txt" }] } } as ToolPart
    expect(toolImages(part).map((x) => x.url)).toEqual(["https://example.com/no-extension?id=1", "https://example.com/photo.jpg"])
    const attached = { type: "tool", tool: "bash", state: { status: "completed", output: "", attachments: [{ type: "file", mime: "image/png", url: "data:image/png;base64,AAAA" }] } } as ToolPart
    expect(toolImages(attached).map((x) => x.url)).toEqual(["data:image/png;base64,AAAA"])
    expect(toolImages({ ...part, state: { status: "running" } } as ToolPart)).toEqual([])
  })
})

test("image-search MCP attachments take precedence over duplicate output URLs", () => {
 const part = { tool: "image_search_search_images", state: { status: "completed", output: "![dog](https://example.com/a.jpg)", attachments: [{ mime: "image/jpeg", url: "data:image/jpeg;base64,AAAA" }] } } as ToolPart
 expect(toolImages(part).map((image) => image.url)).toEqual(["data:image/jpeg;base64,AAAA"])
})

test("bash/webfetch output never auto-renders images (lain.la error page regression)", () => {
  const errorPage = '=== https://pomf2.lain.la/upload.php\n<!DOCTYPE html>\n<html><body><h1>If you are seeing this message, Lain.la\'s log cabin datacenter is having a few issues.</h1>\n<img src="https://lain.la/sadlain.PNG" width="400" height="600"></body></html>\n![x](https://example.com/x.png) https://example.com/y.jpg'
  for (const tool of ["bash", "webfetch", "websearch", "keenable_search_search", "read", undefined]) {
    const part = { type: "tool", tool, state: { status: "completed", output: errorPage, attachments: [] } } as unknown as ToolPart
    expect(toolImages(part)).toEqual([])
  }
  const fake = { type: "tool", tool: "my_image_search_lookalike", state: { status: "completed", output: errorPage } } as unknown as ToolPart
  expect(toolImages(fake)).toEqual([])
})

describe("mobile page zoom", () => {
  test("viewport and editable controls carry iOS focus protections", () => {
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8")
    const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8")
    expect(html).toContain("maximum-scale=1, user-scalable=no")
    expect(css).toContain('input, textarea, [contenteditable]:not([contenteditable="false"])')
    expect(css).toContain("font-size: max(16px, 1em) !important")
  })
  test("native page gestures are blocked but custom image pinch still transforms the canvas", () => {
    cleanups.push(setupPageZoomGuard())
    const outside = document.createElement("div"); document.body.append(outside)
    const native = new Event("gesturestart", { bubbles: true, cancelable: true }); outside.dispatchEvent(native)
    expect(native.defaultPrevented).toBe(true)
    const img = document.createElement("img"); img.src = "data:image/png;base64,AAAA"; document.body.append(img)
    cleanups.push(openMediaViewer(img))
    const stage = document.querySelector<HTMLElement>(".mermaid-viewer-stage")!
    const inner = new Event("gesturestart", { bubbles: true, cancelable: true }); stage.dispatchEvent(inner)
    expect(inner.defaultPrevented).toBe(false)
    const canvas = document.querySelector<HTMLElement>(".mermaid-viewer-canvas")!; const initial = canvas.style.transform
    const pointer = (type: string, id: number, x: number) => stage.dispatchEvent(new PointerEvent(type, { pointerId: id, button: 0, clientX: x, clientY: 100, bubbles: true, cancelable: true }))
    pointer("pointerdown", 1, 100); pointer("pointerdown", 2, 200); pointer("pointermove", 2, 300)
    expect(canvas.style.transform).not.toBe(initial)
    pointer("pointerup", 1, 100); pointer("pointerup", 2, 300)
    const touch = new Event("touchmove", { bubbles: true, cancelable: true }); Object.defineProperty(touch, "touches", { value: [{}, {}] }); outside.dispatchEvent(touch)
    expect(touch.defaultPrevented).toBe(true)
  })
})
