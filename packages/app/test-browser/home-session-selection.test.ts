import { describe, expect, test } from "bun:test"
import { createRoot, createSignal } from "solid-js"
import { createHomeSessionSelection, type BatchDeleteHandlers } from "@/home/sessions/batch-delete"

describe("Home session selection state", () => {
  function setup() {
    return createRoot((dispose) => {
      const [sessions, setSessions] = createSignal([{ id: "a" }, { id: "b" }, { id: "c" }])
      const requests: { ids: string[]; handlers: BatchDeleteHandlers }[] = []
      const selection = createHomeSessionSelection({
        sessions,
        onDelete: (list, handlers) => requests.push({ ids: list.map((s) => s.id), handlers }),
      })

      return { selection, requests, setSessions, dispose }
    })
  }

  test("toggling only works in selection mode; select all and deselect all", () => {
    const { selection, dispose } = setup()

    selection.toggle("a")
    expect(selection.selected()).toEqual([])
    selection.start()
    selection.toggle("a")
    selection.toggle("c")
    expect(selection.selected()).toEqual(["a", "c"])
    selection.toggle("a")
    expect(selection.selected()).toEqual(["c"])
    selection.toggleAll()
    expect(selection.allSelected()).toBe(true)
    selection.toggleAll()
    expect(selection.selected()).toEqual([])
    dispose()
  })

  test("delete sends selected sessions, locks during progress, keeps failures selected", () => {
    const { selection, requests, setSessions, dispose } = setup()

    selection.start()
    selection.toggleAll()
    selection.deleteSelected()
    expect(requests.map((r) => r.ids)).toEqual([["a", "b", "c"]])
    const { handlers } = requests[0]!

    handlers.onStart(3)
    handlers.onProgress(1, 3)
    expect(selection.state.progress).toEqual({ done: 1, total: 3 })
    selection.toggle("a")
    expect(selection.selected()).toEqual(["a", "b", "c"])
    selection.deleteSelected()
    expect(requests.length).toBe(1)

    setSessions([{ id: "b" }, { id: "c" }])
    handlers.onDone({ deleted: ["a"], failed: ["b"], skipped: ["c"] })
    expect(selection.state.progress).toBeUndefined()
    expect(selection.state.active).toBe(true)
    expect(selection.selected()).toEqual(["b", "c"])
    dispose()
  })

  test("a fully successful delete leaves selection mode", () => {
    const { selection, requests, dispose } = setup()

    selection.start()
    selection.toggle("b")
    selection.deleteSelected()
    requests[0]!.handlers.onStart(1)
    requests[0]!.handlers.onDone({ deleted: ["b"], failed: [], skipped: [] })
    expect(selection.state.active).toBe(false)
    expect(selection.selected()).toEqual([])
    dispose()
  })

  test("nothing selected does not open the delete dialog", () => {
    const { selection, requests, dispose } = setup()

    selection.start()
    selection.deleteSelected()
    expect(requests.length).toBe(0)
    dispose()
  })
})
