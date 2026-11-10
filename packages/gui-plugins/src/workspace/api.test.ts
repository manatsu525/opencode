import { describe, expect, test } from "bun:test"
import {
  crumbs,
  deleteWorkspaceEntry,
  fetchWorkspaceListing,
  formatBytes,
  MUTATION_HEADER,
  parentPath,
  workspaceDownloadUrl,
  WorkspaceFilesError,
} from "./api"

describe("workspace files api", () => {
  test("urls encode the relative path", () => {
    expect(workspaceDownloadUrl("a b/中文#?.html")).toBe("/files/download?path=a%20b%2F%E4%B8%AD%E6%96%87%23%3F.html")
  })

  test("path helpers", () => {
    expect(parentPath("a/b/c")).toBe("a/b")
    expect(parentPath("a")).toBe("")
    expect(crumbs("a/b")).toEqual([
      { name: "a", path: "a" },
      { name: "b", path: "a/b" },
    ])
    expect(formatBytes(512)).toBe("512 B")
    expect(formatBytes(1536)).toBe("1.5 KB")
    expect(formatBytes(null)).toBe("")
  })

  test("delete is a same-origin POST with the mutation header and JSON body", async () => {
    const calls: { url: string; init?: RequestInit }[] = []
    const fetcher = (async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return new Response(JSON.stringify({ deleted: { files: 2, directories: 1, symlinks: 0 } }), { status: 200 })
    }) as unknown as typeof fetch
    const result = await deleteWorkspaceEntry({ path: "out", type: "directory" }, fetcher)
    expect(result).toEqual({ files: 2, directories: 1, symlinks: 0 })
    expect(calls[0].url).toBe("/files/delete")
    expect(calls[0].init?.method).toBe("POST")
    expect(calls[0].init?.credentials).toBe("same-origin")
    expect((calls[0].init?.headers as Record<string, string>)[MUTATION_HEADER]).toBe("delete")
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ path: "out", type: "directory" })
  })

  test("errors carry status and server code", async () => {
    const fetcher = (async () =>
      new Response(JSON.stringify({ error: "root" }), { status: 400 })) as unknown as typeof fetch
    const error = await fetchWorkspaceListing("", fetcher).catch((cause) => cause)
    expect(error).toBeInstanceOf(WorkspaceFilesError)
    expect(error.status).toBe(400)
    expect(error.code).toBe("root")
  })
})
