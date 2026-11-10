import { For, Match, Show, Switch, createResource, createSignal } from "solid-js"
import { Icon } from "@opencode-ai/ui/icon"
import { useLanguage } from "@/context/language"

/**
 * Read-only browser for the deployment's workspace, served by the authenticated same-origin
 * sidecar (`/files/list`, `/files/download`). Works with or without Git and lists ignored files.
 */
export type WorkspaceEntry = {
  name: string
  path: string
  type: "directory" | "file" | "symlink" | "other"
  size: number | null
  mtime: number
}
export type WorkspaceListing = { path: string; entries: WorkspaceEntry[]; truncated: boolean }

export class WorkspaceFilesError extends Error {
  constructor(readonly status: number) {
    super(`workspace files request failed: ${status}`)
  }
}

export function workspaceDownloadUrl(path: string) {
  return "/files/download?path=" + encodeURIComponent(path)
}

export function workspaceListUrl(path: string) {
  return "/files/list?path=" + encodeURIComponent(path)
}

export async function fetchWorkspaceListing(path: string, fetcher: typeof fetch = fetch): Promise<WorkspaceListing> {
  const response = await fetcher(workspaceListUrl(path), { credentials: "same-origin", cache: "no-store" })
  if (!response.ok) throw new WorkspaceFilesError(response.status)
  return (await response.json()) as WorkspaceListing
}

export function formatBytes(value: number | null) {
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

type Translate = (key: string, params?: Record<string, string>) => string

export function WorkspaceFiles(props: { class?: string; fetcher?: typeof fetch }) {
  const language = useLanguage()
  return (
    <WorkspaceFilesView
      class={props.class}
      fetcher={props.fetcher}
      t={(key, params) => language.t(key as Parameters<typeof language.t>[0], params)}
    />
  )
}

export function WorkspaceFilesView(props: { class?: string; fetcher?: typeof fetch; t: Translate }) {
  const language = { t: (key: string, params?: Record<string, string>) => props.t(key, params) }
  const [path, setPath] = createSignal("")
  const [listing, { refetch }] = createResource(path, (value) => fetchWorkspaceListing(value, props.fetcher))
  const crumbs = () => {
    const parts = path().split("/").filter(Boolean)
    return parts.map((name, index) => ({ name, path: parts.slice(0, index + 1).join("/") }))
  }
  const errorText = () => {
    const error = listing.error
    const status = error instanceof WorkspaceFilesError ? error.status : 0
    if (status === 401) return language.t("workspace.files.error.auth")
    if (status === 404 && !path()) return language.t("workspace.files.error.unsupported")
    if (status === 404) return language.t("workspace.files.error.missing")
    return language.t("workspace.files.error.generic")
  }

  return (
    <div data-component="workspace-files" class={`flex flex-col min-h-0 h-full ${props.class ?? ""}`}>
      <div class="flex items-center gap-1 px-3 py-2 border-b border-border-weaker-base shrink-0">
        <Show when={path()}>
          <button
            type="button"
            class="size-8 shrink-0 grid place-items-center rounded-md hover:bg-surface-raised-base-hover"
            aria-label={language.t("workspace.files.up")}
            data-action="workspace-files-up"
            onClick={() => setPath(parentPath(path()))}
          >
            <Icon name="chevron-left" size="small" />
          </button>
        </Show>
        <nav class="flex-1 min-w-0 flex items-center gap-1 overflow-x-auto no-scrollbar text-13-medium" aria-label="breadcrumb">
          <button
            type="button"
            class="shrink-0 px-1.5 py-1 rounded hover:bg-surface-raised-base-hover"
            classList={{ "text-text-strong": !path(), "text-text-weak": !!path() }}
            onClick={() => setPath("")}
          >
            {language.t("workspace.files.root")}
          </button>
          <For each={crumbs()}>
            {(crumb) => (
              <>
                <span class="text-text-weaker shrink-0">/</span>
                <button
                  type="button"
                  class="shrink-0 max-w-40 truncate px-1.5 py-1 rounded hover:bg-surface-raised-base-hover"
                  classList={{ "text-text-strong": crumb.path === path(), "text-text-weak": crumb.path !== path() }}
                  onClick={() => setPath(crumb.path)}
                >
                  {crumb.name}
                </button>
              </>
            )}
          </For>
        </nav>
        <button
          type="button"
          class="size-8 shrink-0 grid place-items-center rounded-md hover:bg-surface-raised-base-hover"
          aria-label={language.t("workspace.files.refresh")}
          data-action="workspace-files-refresh"
          onClick={() => refetch()}
        >
          <Icon name="reset" size="small" />
        </button>
      </div>
      <div class="flex-1 min-h-0 overflow-y-auto">
        <Switch>
          <Match when={listing.error}>
            <div class="px-4 py-6 text-13-regular text-text-weak" data-slot="workspace-files-error">
              {errorText()}
            </div>
          </Match>
          <Match when={listing.loading && !listing.latest}>
            <div class="px-4 py-6 text-13-regular text-text-weak">
              {language.t("common.loading")}
              {language.t("common.loading.ellipsis")}
            </div>
          </Match>
          <Match when={listing.latest && listing.latest.entries.length === 0}>
            <div class="px-4 py-6 text-13-regular text-text-weak">{language.t("workspace.files.empty")}</div>
          </Match>
          <Match when={listing.latest}>
            {(data) => (
              <ul class="py-1" role="list">
                <For each={data().entries}>
                  {(entry) => (
                    <li class="flex items-center gap-2 px-3 min-h-11 hover:bg-surface-raised-base-hover" data-type={entry.type}>
                      <Switch>
                        <Match when={entry.type === "directory"}>
                          <button
                            type="button"
                            class="flex-1 min-w-0 flex items-center gap-2 py-2 text-left"
                            data-action="workspace-files-open"
                            onClick={() => setPath(entry.path)}
                          >
                            <Icon name="folder" size="small" class="shrink-0 text-icon-weak" />
                            <span class="truncate text-13-regular text-text-strong">{entry.name}</span>
                          </button>
                          <Icon name="chevron-right" size="small" class="shrink-0 text-icon-weaker" />
                        </Match>
                        <Match when={entry.type === "file"}>
                          <a
                            href={workspaceDownloadUrl(entry.path)}
                            download={entry.name}
                            class="flex-1 min-w-0 flex items-center gap-2 py-2"
                            data-action="workspace-files-download"
                          >
                            <Icon name="open-file" size="small" class="shrink-0 text-icon-weak" />
                            <span class="truncate text-13-regular text-text-strong">{entry.name}</span>
                            <span class="ml-auto shrink-0 text-12-regular text-text-weak">{formatBytes(entry.size)}</span>
                          </a>
                          <a
                            href={workspaceDownloadUrl(entry.path)}
                            download={entry.name}
                            class="size-9 shrink-0 grid place-items-center rounded-md hover:bg-surface-raised-base-hover"
                            aria-label={language.t("workspace.files.download", { name: entry.name })}
                          >
                            <Icon name="download" size="small" />
                          </a>
                        </Match>
                        <Match when={true}>
                          <div class="flex-1 min-w-0 flex items-center gap-2 py-2 opacity-60" title={language.t("workspace.files.notDownloadable")}>
                            <Icon name="link" size="small" class="shrink-0 text-icon-weaker" />
                            <span class="truncate text-13-regular text-text-weak">{entry.name}</span>
                          </div>
                        </Match>
                      </Switch>
                    </li>
                  )}
                </For>
                <Show when={data().truncated}>
                  <li class="px-4 py-3 text-12-regular text-text-weak">{language.t("workspace.files.truncated")}</li>
                </Show>
              </ul>
            )}
          </Match>
        </Switch>
      </div>
    </div>
  )
}
