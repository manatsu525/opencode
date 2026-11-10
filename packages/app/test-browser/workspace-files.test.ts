import { afterEach, expect, mock, test } from "bun:test"
import { createComponent } from "solid-js"
import { render } from "solid-js/web"
import { readFileSync } from "node:fs"
import {
  WorkspaceFilesView,
  fetchWorkspaceListing,
  formatBytes,
  parentPath,
  workspaceDownloadUrl,
} from "../src/components/workspace-files"
import { markWorkspaceDownload, workspaceDownloadTarget } from "../../session-ui/src/components/workspace-download-link"
// markdown-cache imports the Vite worker URL; the sanitizer itself does not need it.
mock.module("../../session-ui/src/components/markdown-worker", () => ({ parseMarkdown: async (text: string) => text }))
const { sanitizeMarkdown } = await import("../../session-ui/src/components/markdown-cache")

let cleanup: (() => void) | undefined
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ""
})
const tick = () => new Promise((resolve) => setTimeout(resolve, 20))
const t = (key: string, params?: Record<string, string>) => (params?.name ? `${key}:${params.name}` : key)

const tree: Record<string, unknown> = {
  "": { path: "", truncated: false, entries: [
    { name: "docs", path: "docs", type: "directory", size: null, mtime: 1 },
    { name: "xiangqi.html", path: "xiangqi.html", type: "file", size: 39065, mtime: 1 },
    { name: "link", path: "link", type: "symlink", size: null, mtime: 1 },
  ] },
  docs: { path: "docs", truncated: false, entries: [
    { name: "报告 #1.pdf", path: "docs/报告 #1.pdf", type: "file", size: 2048, mtime: 1 },
  ] },
}
function fakeFetch(calls: string[], status = 200): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "https://example.test")
    calls.push(url.pathname + url.search)
    expect(init?.credentials).toBe("same-origin")
    const body = tree[url.searchParams.get("path") ?? ""]
    if (status !== 200 || !body) return new Response("no", { status: status === 200 ? 404 : status })
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })
  }) as typeof fetch
}

test("helpers encode paths, format sizes and walk up", async () => {
  expect(workspaceDownloadUrl("docs/报告 #1.pdf")).toBe("/files/download?path=docs%2F%E6%8A%A5%E5%91%8A%20%231.pdf")
  expect(formatBytes(39065)).toBe("38 KB")
  expect(formatBytes(512)).toBe("512 B")
  expect(parentPath("a/b/c")).toBe("a/b")
  expect(parentPath("a")).toBe("")
  const calls: string[] = []
  expect((await fetchWorkspaceListing("docs", fakeFetch(calls))).entries[0].name).toBe("报告 #1.pdf")
  expect(calls).toEqual(["/files/list?path=docs"])
})

test("workspace browser lists all files, navigates folders, downloads files and refreshes", async () => {
  const calls: string[] = []
  const root = document.createElement("div")
  document.body.append(root)
  cleanup = render(() => createComponent(WorkspaceFilesView, { t, fetcher: fakeFetch(calls) }), root)
  await tick()
  const download = root.querySelector<HTMLAnchorElement>('a[data-action="workspace-files-download"]')!
  expect(download.getAttribute("href")).toBe("/files/download?path=xiangqi.html")
  expect(download.getAttribute("download")).toBe("xiangqi.html")
  expect(download.getAttribute("target")).toBeNull()
  expect(root.textContent).toContain("38 KB")
  expect(root.querySelector('li[data-type="symlink"] a')).toBeNull()
  root.querySelector<HTMLButtonElement>('button[data-action="workspace-files-open"]')!.click()
  await tick()
  const nested = root.querySelector<HTMLAnchorElement>('a[data-action="workspace-files-download"]')!
  expect(nested.getAttribute("href")).toBe(workspaceDownloadUrl("docs/报告 #1.pdf"))
  expect(nested.getAttribute("download")).toBe("报告 #1.pdf")
  expect(root.querySelector('nav[aria-label="breadcrumb"]')!.textContent).toContain("docs")
  root.querySelector<HTMLButtonElement>('button[data-action="workspace-files-refresh"]')!.click()
  await tick()
  root.querySelector<HTMLButtonElement>('button[data-action="workspace-files-up"]')!.click()
  await tick()
  expect(calls).toEqual(["/files/list?path=", "/files/list?path=docs", "/files/list?path=docs", "/files/list?path="])
})

test("expired login and unsupported servers show a clear message", async () => {
  for (const [status, key] of [[401, "workspace.files.error.auth"], [404, "workspace.files.error.unsupported"]] as const) {
    const root = document.createElement("div")
    document.body.append(root)
    const dispose = render(() => createComponent(WorkspaceFilesView, { t, fetcher: fakeFetch([], status) }), root)
    await tick()
    expect(root.querySelector('[data-slot="workspace-files-error"]')!.textContent).toBe(key)
    dispose()
  }
})

test("chat links to /files/download become same-origin direct downloads, others untouched", () => {
  const origin = "https://163.192.16.104:8558"
  expect(workspaceDownloadTarget("/files/download?path=xiangqi.html", origin)).toEqual({ url: "/files/download?path=xiangqi.html", name: "xiangqi.html" })
  expect(workspaceDownloadTarget(origin + "/files/download?path=docs%2F%E6%8A%A5%E5%91%8A.pdf", origin)!.name).toBe("报告.pdf")
  expect(workspaceDownloadTarget("https://evil.example/files/download?path=x", origin)).toBeUndefined()
  expect(workspaceDownloadTarget("/files/list?path=", origin)).toBeUndefined()
  expect(workspaceDownloadTarget("/files/download", origin)).toBeUndefined()
  const a = document.createElement("a")
  a.setAttribute("href", "/files/download?path=docs/a%20b.zip")
  a.setAttribute("target", "_blank")
  expect(markWorkspaceDownload(a, origin)).toBe(true)
  expect(a.getAttribute("target")).toBeNull()
  expect(a.getAttribute("download")).toBe("a b.zip")
  const external = document.createElement("a")
  external.setAttribute("href", "https://example.com/files/download?path=x")
  expect(markWorkspaceDownload(external, origin)).toBe(false)
})

test("sanitized Markdown keeps the download link and marks it", () => {
  ;(window as unknown as { happyDOM?: { setURL(url: string): void } }).happyDOM?.setURL("https://163.192.16.104:8558/")
  expect(location.origin).toBe("https://163.192.16.104:8558")
  const html = sanitizeMarkdown('<p><a href="/files/download?path=xiangqi.html" class="external-link" target="_blank" rel="noopener noreferrer">下载 xiangqi.html</a> <a href="https://opencode.ai" target="_blank">x</a></p>')
  const root = document.createElement("div")
  root.innerHTML = html
  const [download, external] = Array.from(root.querySelectorAll("a"))
  expect(download.getAttribute("href")).toBe("/files/download?path=xiangqi.html")
  expect(download.hasAttribute("download")).toBe(true)
  expect(download.getAttribute("target")).toBeNull()
  expect(external.getAttribute("target")).toBe("_blank")
  expect(external.getAttribute("rel")).toContain("noopener")
})

test("mobile gets a Files tab and desktop a workspace tab, both with or without Git", () => {
  const session = readFileSync(new URL("../src/pages/session.tsx", import.meta.url), "utf8")
  expect(session).toContain('value="files"')
  expect(session).toContain("<WorkspaceFiles")
  expect(session).toContain("!mobileChanges() && !mobileFiles()")
  const panel = readFileSync(new URL("../src/pages/session/session-side-panel.tsx", import.meta.url), "utf8")
  expect(panel).toContain('<Tabs.Trigger value="workspace"')
  expect(panel).toContain("<WorkspaceFiles />")
})
