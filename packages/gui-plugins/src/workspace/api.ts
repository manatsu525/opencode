/**
 * Client for the deployment's workspace file service: an authenticated, same-origin sidecar beside the opencode
 * server (`/files/*`). Listing and download are GETs; deletion is a POST that also carries a custom header, so a
 * cross-site form or a plain link can never trigger it.
 */
export type WorkspaceEntry = {
  name: string
  path: string
  type: "directory" | "file" | "symlink" | "other"
  size: number | null
  mtime: number
}

export type WorkspaceListing = { path: string; entries: WorkspaceEntry[]; truncated: boolean }

export type WorkspaceInfo = {
  path: string
  type: "directory" | "file" | "symlink" | "other"
  files: number
  directories: number
  symlinks: number
  bytes: number
  truncated: boolean
}

export type WorkspaceDeleted = { files: number; directories: number; symlinks: number }

/** The header the sidecar requires on every mutation. */
export const MUTATION_HEADER = "X-OpenCode-Files"

export class WorkspaceFilesError extends Error {
  constructor(
    readonly status: number,
    readonly code?: string,
  ) {
    super(`workspace files request failed: ${status}${code ? ` (${code})` : ""}`)
  }
}

const query = (path: string) => "?path=" + encodeURIComponent(path)

export function workspaceDownloadUrl(path: string) {
  return "/files/download" + query(path)
}

export function workspaceListUrl(path: string) {
  return "/files/list" + query(path)
}

async function failure(response: Response) {
  const body = (await response.json().catch(() => undefined)) as { error?: unknown } | undefined

  return new WorkspaceFilesError(response.status, typeof body?.error === "string" ? body.error : undefined)
}

export async function fetchWorkspaceListing(path: string, fetcher: typeof fetch = fetch): Promise<WorkspaceListing> {
  const response = await fetcher(workspaceListUrl(path), { credentials: "same-origin", cache: "no-store" })

  if (!response.ok) throw await failure(response)

  return (await response.json()) as WorkspaceListing
}

export async function fetchWorkspaceInfo(path: string, fetcher: typeof fetch = fetch): Promise<WorkspaceInfo> {
  const response = await fetcher("/files/info" + query(path), { credentials: "same-origin", cache: "no-store" })

  if (!response.ok) throw await failure(response)

  return (await response.json()) as WorkspaceInfo
}

export async function deleteWorkspaceEntry(
  input: { path: string; type: WorkspaceEntry["type"] },
  fetcher: typeof fetch = fetch,
): Promise<WorkspaceDeleted> {
  const response = await fetcher("/files/delete", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", [MUTATION_HEADER]: "delete" },
    body: JSON.stringify({ path: input.path, type: input.type }),
  })

  if (!response.ok) throw await failure(response)

  return ((await response.json()) as { deleted: WorkspaceDeleted }).deleted
}

export function formatBytes(value: number | null | undefined) {
  if (value === null || value === undefined) return ""

  if (value < 1024) return `${value} B`
  const units = ["KB", "MB", "GB", "TB"]
  let size = value / 1024
  let unit = 0

  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit++
  }

  return `${size >= 10 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`
}

export function parentPath(path: string) {
  const parts = path.split("/").filter(Boolean)
  parts.pop()

  return parts.join("/")
}

export function crumbs(path: string) {
  const parts = path.split("/").filter(Boolean)

  return parts.map((name, index) => ({ name, path: parts.slice(0, index + 1).join("/") }))
}
