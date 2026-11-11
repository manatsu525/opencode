import { createMemo } from "solid-js"
import { createStore } from "solid-js/store"

// Batch (multi-select) session deletion for the Home session list.
// Pure helpers so the selection rules and the delete loop can be unit tested
// without the server runtime.

export const BATCH_DELETE_PREVIEW_LIMIT = 5

export const BATCH_DELETE_CONCURRENCY = 2

export type BatchDeleteResult = {
  deleted: string[]
  failed: string[]
}

export type BatchDeleteHandlers = {
  onStart: (total: number) => void
  onProgress: (done: number, total: number) => void
  // `skipped` are running sessions left out of the batch.
  onDone: (result: BatchDeleteResult & { skipped: string[] }) => void
}

// Busy (running) sessions are never deleted in a batch. Single delete does not
// stop a running session first, so the safe batch behaviour is to skip them and
// leave them selected; the user can stop them and delete again.
export function partitionBatchDelete<T extends { id: string }>(sessions: readonly T[], busy: (id: string) => boolean) {
  const deletable: T[] = []
  const running: T[] = []

  for (const session of sessions) (busy(session.id) ? running : deletable).push(session)

  return { deletable, running }
}

export function batchDeletePreview(titles: readonly string[], limit = BATCH_DELETE_PREVIEW_LIMIT) {
  return {
    shown: titles.slice(0, limit),
    more: titles.length > limit,
  }
}

// Deletes with small concurrency through the same remove call single delete
// uses. Never throws: every id ends up in either `deleted` or `failed`, in the
// original order.
export async function runBatchDelete(
  ids: readonly string[],
  remove: (id: string) => Promise<unknown>,
  options?: { concurrency?: number; onProgress?: (done: number, total: number) => void },
): Promise<BatchDeleteResult> {
  const total = ids.length
  const concurrency = Math.max(1, Math.min(options?.concurrency ?? BATCH_DELETE_CONCURRENCY, total || 1))
  const ok = new Array<boolean>(total).fill(false)
  let next = 0
  let done = 0

  const worker = async () => {
    while (next < total) {
      const index = next++
      ok[index] = await Promise.resolve()
        .then(() => remove(ids[index]!))
        .then(
          (value) => value !== false,
          () => false,
        )
      done++
      options?.onProgress?.(done, total)
    }
  }

  await Promise.all(Array.from({ length: total === 0 ? 0 : concurrency }, worker))

  return {
    deleted: ids.filter((_, index) => ok[index]),
    failed: ids.filter((_, index) => !ok[index]),
  }
}

// Selection set helpers. Only sessions still listed count as selected, so a
// session deleted elsewhere silently leaves the selection.
export function visibleSelection(selected: Readonly<Record<string, boolean | undefined>>, listed: readonly string[]) {
  return listed.filter((id) => !!selected[id])
}

export function toggleAll(listed: readonly string[], selected: Readonly<Record<string, boolean | undefined>>) {
  const all = listed.length > 0 && listed.every((id) => !!selected[id])

  return Object.fromEntries(listed.map((id) => [id, !all])) as Record<string, boolean>
}

export type HomeSessionSelection = {
  active: boolean
  ids: Record<string, boolean>
  progress: { done: number; total: number } | undefined
}

// Multi-select state for the Home list. Selected IDs are keyed by session ID so
// row recreation on store updates keeps the selection.
export function createHomeSessionSelection<T extends { id: string }>(input: {
  sessions: () => readonly T[]
  onDelete: (sessions: T[], handlers: BatchDeleteHandlers) => void
  onBeforeStart?: () => void
}) {
  const [state, setState] = createStore<HomeSessionSelection>({ active: false, ids: {}, progress: undefined })
  const listed = createMemo(() => input.sessions().map((session) => session.id))
  const selected = createMemo(() => visibleSelection(state.ids, listed()))
  const allSelected = createMemo(() => listed().length > 0 && selected().length === listed().length)

  const end = () => setState({ active: false, ids: {}, progress: undefined })

  return {
    state,
    listed,
    selected,
    allSelected,
    start() {
      input.onBeforeStart?.()
      setState({ active: true, ids: {}, progress: undefined })
    },
    end,
    toggle(id: string) {
      if (!state.active || state.progress) return
      setState("ids", id, (value) => !value)
    },
    toggleAll() {
      if (state.progress) return
      setState("ids", toggleAll(listed(), state.ids))
    },
    deleteSelected() {
      const ids = new Set(selected())
      const sessions = input.sessions().filter((session) => ids.has(session.id))

      if (sessions.length === 0 || state.progress) return
      input.onDelete(sessions, {
        onStart: (total) => setState("progress", total > 0 ? { done: 0, total } : undefined),
        onProgress: (done, total) => setState("progress", { done, total }),
        onDone: (result) => {
          // Failed and skipped (running) sessions stay selected for another try.
          setState("progress", undefined)
          result.deleted.forEach((id) => setState("ids", id, false))

          if (result.failed.length === 0 && result.skipped.length === 0) end()
        },
      })
    },
  }
}
