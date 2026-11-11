import { For, Show } from "solid-js"
import { batchDeletePreview } from "./batch-delete"

export type BatchDeleteKey =
  | "home.sessions.select"
  | "home.sessions.select.count"
  | "home.sessions.select.all"
  | "home.sessions.select.none"
  | "home.sessions.select.deleting"
  | "session.batchDelete.confirm"
  | "session.batchDelete.more"
  | "session.batchDelete.running"
  | "session.batchDelete.allRunning"
  | "common.cancel"
  | "common.delete"

export type BatchDeleteTranslate = (key: BatchDeleteKey, params?: Record<string, string | number>) => string

// Selection-mode toolbar. Sticks to the bottom of the list so it stays under
// the thumb on phones and never collides with the sticky group headers.
export function HomeSessionSelectionBar(props: {
  t: BatchDeleteTranslate
  count: number
  allSelected: boolean
  total: number
  progress: { done: number; total: number } | undefined
  onToggleAll: () => void
  onDelete: () => void
  onCancel: () => void
}) {
  const busy = () => !!props.progress

  return (
    <div
      data-component="home-session-selection-bar"
      role="toolbar"
      aria-label={props.t("home.sessions.select")}
      class={`
        sticky bottom-0 z-40 -mx-1 mt-2 flex min-h-12 flex-wrap items-center gap-x-2 gap-y-1 rounded-[10px]
        bg-v2-background-bg-base px-3 py-2 shadow-[var(--v2-elevation-floating)]
        pb-[max(0.5rem,env(safe-area-inset-bottom))]
      `}
    >
      <span
        data-slot="selection-count"
        aria-live="polite"
        class="me-auto min-w-0 whitespace-nowrap text-v2-text-text-base [font-weight:530]"
      >
        <Show when={props.progress} fallback={props.t("home.sessions.select.count", { count: props.count })}>
          {(progress) => props.t("home.sessions.select.deleting", { done: progress().done, total: progress().total })}
        </Show>
      </span>
      <button
        type="button"
        data-action="home-session-select-all"
        disabled={busy() || props.total === 0}
        class="h-9 rounded-[6px] px-3 text-v2-text-text-base hover:bg-v2-overlay-simple-overlay-hover disabled:opacity-50"
        onClick={props.onToggleAll}
      >
        {props.allSelected ? props.t("home.sessions.select.none") : props.t("home.sessions.select.all")}
      </button>
      <button
        type="button"
        data-action="home-session-select-delete"
        disabled={busy() || props.count === 0}
        class="h-9 rounded-[6px] px-3 text-v2-state-fg-danger [font-weight:530] hover:bg-v2-overlay-simple-overlay-hover disabled:opacity-50"
        onClick={props.onDelete}
      >
        {props.t("common.delete")}
      </button>
      <button
        type="button"
        data-action="home-session-select-cancel"
        disabled={busy()}
        class="h-9 rounded-[6px] px-3 text-v2-text-text-muted hover:bg-v2-overlay-simple-overlay-hover disabled:opacity-50"
        onClick={props.onCancel}
      >
        {props.t("common.cancel")}
      </button>
    </div>
  )
}

export function HomeSessionCheckbox(props: { checked: boolean }) {
  return (
    <span
      data-component="home-session-checkbox"
      data-checked={props.checked || undefined}
      aria-hidden="true"
      class="grid size-[18px] shrink-0 place-items-center rounded-[4px] border"
      classList={{
        "border-v2-border-border-strong bg-transparent": !props.checked,
        "border-transparent bg-v2-background-bg-inverse text-v2-text-text-inverse": props.checked,
      }}
    >
      <Show when={props.checked}>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M2.5 6.2 5 8.5l4.5-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
      </Show>
    </span>
  )
}

// Body of the batch delete confirmation: what will be deleted and what is skipped.
export function BatchDeleteSummary(props: { t: BatchDeleteTranslate; titles: string[]; running: number }) {
  const preview = () => batchDeletePreview(props.titles)

  return (
    <div data-component="batch-delete-summary" class="flex flex-col gap-2 px-6 pb-2 text-[13px] leading-5">
      <Show
        when={props.titles.length > 0}
        fallback={<p data-slot="all-running">{props.t("session.batchDelete.allRunning")}</p>}
      >
        <p data-slot="confirm" class="text-v2-text-text-base">
          {props.t("session.batchDelete.confirm", { count: props.titles.length })}
        </p>
        <ul data-slot="titles" class="flex list-disc flex-col gap-0.5 ps-5 text-v2-text-text-muted">
          <For each={preview().shown}>
            {(title) => <li class="overflow-hidden text-ellipsis whitespace-nowrap">{title}</li>}
          </For>
        </ul>
        <Show when={preview().more}>
          <p data-slot="more" class="text-v2-text-text-muted">
            {props.t("session.batchDelete.more", { count: props.titles.length })}
          </p>
        </Show>
        <Show when={props.running > 0}>
          <p data-slot="running" class="text-v2-text-text-muted">
            {props.t("session.batchDelete.running", { count: props.running })}
          </p>
        </Show>
      </Show>
    </div>
  )
}
