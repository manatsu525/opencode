import { For, Match, Show, Switch, createResource, createSignal } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { Button } from "@opencode/ui/button"
import { useDialog } from "@opencode/ui/context/dialog"
import { Dialog, DialogFooter, DialogHeader, DialogTitleGroup } from "@opencode/ui/dialog"
import { showToast } from "@opencode/ui/toast"
import { usePlugin } from "@opencode/plugin/gui"
import {
  crumbs,
  deleteWorkspaceEntry,
  fetchWorkspaceInfo,
  fetchWorkspaceListing,
  formatBytes,
  parentPath,
  workspaceDownloadUrl,
  WorkspaceFilesError,
  type WorkspaceEntry,
  type WorkspaceInfo,
} from "./api"

const ROW_ACTION =
  "grid size-9 shrink-0 place-items-center rounded-[6px] text-v2-text-text-muted hover:bg-v2-overlay-simple-overlay-hover focus-visible:bg-v2-overlay-simple-overlay-hover"

/**
 * The deployment's workspace (Git or not, ignored files included): browse folders, download files and delete files
 * or folders after a confirmation that states exactly what goes.
 */
export function WorkspaceFiles(props: { fetcher?: typeof fetch }) {
  const ctx = usePlugin()
  const dialog = useDialog()
  const [path, setPath] = createSignal("")
  const [busy, setBusy] = createSignal<string>()
  const [listing, { refetch }] = createResource(path, (value) => fetchWorkspaceListing(value, props.fetcher))

  const errorText = (error: unknown, missingRoot = true) => {
    const status = error instanceof WorkspaceFilesError ? error.status : 0
    const code = error instanceof WorkspaceFilesError ? error.code : undefined

    if (status === 401) return ctx.t("error.auth")
    if (status === 403) return ctx.t("error.forbidden")
    if (status === 404 && missingRoot && !path()) return ctx.t("error.unsupported")
    if (status === 404) return ctx.t("error.missing")
    if (code === "root") return ctx.t("error.root")
    if (code === "symlink") return ctx.t("error.symlink")
    if (code === "changed") return ctx.t("error.changed")

    return ctx.t("error.generic")
  }

  const scope = (entry: WorkspaceEntry, info: WorkspaceInfo) => {
    if (entry.type === "directory") {
      const counts = ctx.t("delete.folder.counts", {
        files: String(info.files),
        directories: String(info.directories),
        symlinks: String(info.symlinks),
        size: formatBytes(info.bytes),
      })

      return ctx.t("delete.folder.description", { name: entry.name, counts }) + (info.truncated ? ctx.t("delete.truncated") : "")
    }

    return ctx.t("delete.file.description", { name: entry.name, size: formatBytes(info.bytes) })
  }

  const remove = async (entry: WorkspaceEntry) => {
    setBusy(entry.path)

    try {
      await deleteWorkspaceEntry({ path: entry.path, type: entry.type }, props.fetcher)
      showToast({ variant: "success", title: ctx.t("delete.done", { name: entry.name }) })
    } catch (error) {
      showToast({ variant: "error", title: ctx.t("delete.failed", { name: entry.name }), description: errorText(error, false) })
    } finally {
      setBusy(undefined)
      void refetch()
    }
  }

  const confirm = async (entry: WorkspaceEntry) => {
    if (busy()) return
    setBusy(entry.path)
    const info = await fetchWorkspaceInfo(entry.path, props.fetcher).catch((error: unknown) => error)
    setBusy(undefined)

    if (info instanceof Error || !info || typeof info !== "object") {
      showToast({ variant: "error", title: ctx.t("delete.failed", { name: entry.name }), description: errorText(info, false) })
      void refetch()

      return
    }

    const title = entry.type === "directory" ? ctx.t("delete.folder.title") : ctx.t("delete.file.title")

    dialog.show(() => (
      <Dialog fit>
        <DialogHeader hideClose>
          <DialogTitleGroup title={title} description={scope(entry, info as WorkspaceInfo)} />
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" autofocus onClick={() => dialog.close()}>
            {ctx.t("common.cancel")}
          </Button>
          <Button
            variant="danger"
            data-action="workspace-files-confirm-delete"
            onClick={() => {
              dialog.close()
              void remove(entry)
            }}
          >
            {ctx.t("delete.button")}
          </Button>
        </DialogFooter>
      </Dialog>
    ))
  }

  const deleteButton = (entry: WorkspaceEntry) => (
    <button
      type="button"
      class={ROW_ACTION}
      data-action="workspace-files-delete"
      disabled={!!busy()}
      aria-label={ctx.t("delete.label", { name: entry.name })}
      title={ctx.t("delete.label", { name: entry.name })}
      onClick={() => void confirm(entry)}
    >
      <Icon name="trash" />
    </button>
  )

  return (
    <div data-component="workspace-files" class="flex h-full min-h-0 flex-col text-v2-text-text-base">
      <div class="flex shrink-0 items-center gap-1 border-b border-v2-border-border-muted px-2 py-1.5">
        <Show when={path()}>
          <button
            type="button"
            class={ROW_ACTION}
            aria-label={ctx.t("up")}
            data-action="workspace-files-up"
            onClick={() => setPath(parentPath(path()))}
          >
            <Icon name="chevron-left" />
          </button>
        </Show>
        <nav class="no-scrollbar flex min-w-0 flex-1 items-center gap-1 overflow-x-auto" aria-label={ctx.t("breadcrumb")}>
          <button
            type="button"
            class="shrink-0 rounded px-1.5 py-1 hover:bg-v2-overlay-simple-overlay-hover"
            classList={{ "text-v2-text-text-base": !path(), "text-v2-text-text-muted": !!path() }}
            onClick={() => setPath("")}
          >
            {ctx.t("root")}
          </button>
          <For each={crumbs(path())}>
            {(crumb) => (
              <>
                <span class="shrink-0 text-v2-text-text-faint">/</span>
                <button
                  type="button"
                  class="max-w-40 shrink-0 truncate rounded px-1.5 py-1 hover:bg-v2-overlay-simple-overlay-hover"
                  classList={{
                    "text-v2-text-text-base": crumb.path === path(),
                    "text-v2-text-text-muted": crumb.path !== path(),
                  }}
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
          class={ROW_ACTION}
          aria-label={ctx.t("refresh")}
          data-action="workspace-files-refresh"
          onClick={() => void refetch()}
        >
          <Icon name="refresh" />
        </button>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto">
        <Switch>
          <Match when={listing.error}>
            <div class="px-4 py-6 text-v2-text-text-muted" data-slot="workspace-files-error">
              {errorText(listing.error)}
            </div>
          </Match>
          <Match when={listing.loading && !listing.latest}>
            <div class="px-4 py-6 text-v2-text-text-muted">{ctx.t("loading")}</div>
          </Match>
          <Match when={listing.latest && listing.latest.entries.length === 0}>
            <div class="px-4 py-6 text-v2-text-text-muted">{ctx.t("empty")}</div>
          </Match>
          <Match when={listing.latest}>
            {(data) => (
              <ul class="py-1" role="list">
                <For each={data().entries}>
                  {(entry) => (
                    <li
                      class="flex min-h-11 items-center gap-1 px-2 hover:bg-v2-overlay-simple-overlay-hover"
                      classList={{ "opacity-50": busy() === entry.path }}
                      data-type={entry.type}
                      data-path={entry.path}
                    >
                      <Switch>
                        <Match when={entry.type === "directory"}>
                          <button
                            type="button"
                            class="flex min-w-0 flex-1 items-center gap-2 py-2 text-start"
                            data-action="workspace-files-open"
                            onClick={() => setPath(entry.path)}
                          >
                            <Icon name="folder" class="shrink-0 text-v2-icon-icon-muted" />
                            <span class="truncate">{entry.name}</span>
                            <Icon name="chevron-right" class="ms-auto shrink-0 text-v2-icon-icon-faint" />
                          </button>
                          {deleteButton(entry)}
                        </Match>
                        <Match when={entry.type === "file"}>
                          <a
                            href={workspaceDownloadUrl(entry.path)}
                            download={entry.name}
                            class="flex min-w-0 flex-1 items-center gap-2 py-2"
                            data-action="workspace-files-download"
                          >
                            <Icon name="file-document" class="shrink-0 text-v2-icon-icon-muted" />
                            <span class="truncate">{entry.name}</span>
                            <span class="ms-auto shrink-0 text-v2-text-text-faint">{formatBytes(entry.size)}</span>
                          </a>
                          <a
                            href={workspaceDownloadUrl(entry.path)}
                            download={entry.name}
                            class={ROW_ACTION}
                            aria-label={ctx.t("download", { name: entry.name })}
                            title={ctx.t("download", { name: entry.name })}
                          >
                            <Icon name="download" />
                          </a>
                          {deleteButton(entry)}
                        </Match>
                        <Match when={true}>
                          <div
                            class="flex min-w-0 flex-1 items-center gap-2 py-2 text-v2-text-text-muted"
                            title={ctx.t("notDownloadable")}
                          >
                            <Icon name="outline-dots" class="shrink-0 text-v2-icon-icon-faint" />
                            <span class="truncate">{entry.name}</span>
                          </div>
                        </Match>
                      </Switch>
                    </li>
                  )}
                </For>
                <Show when={data().truncated}>
                  <li class="px-4 py-3 text-v2-text-text-muted">{ctx.t("truncated")}</li>
                </Show>
              </ul>
            )}
          </Match>
        </Switch>
      </div>
    </div>
  )
}

export default WorkspaceFiles
