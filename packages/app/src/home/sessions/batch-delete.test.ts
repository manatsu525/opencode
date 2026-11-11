import { describe, expect, test } from "bun:test"
import { batchDeletePreview, partitionBatchDelete, runBatchDelete, toggleAll, visibleSelection } from "./batch-delete"

describe("batch session delete", () => {
  test("running sessions are skipped, not deleted", () => {
    const sessions = [{ id: "a" }, { id: "b" }, { id: "c" }]
    const parts = partitionBatchDelete(sessions, (id) => id === "b")

    expect(parts.deletable.map((s) => s.id)).toEqual(["a", "c"])
    expect(parts.running.map((s) => s.id)).toEqual(["b"])
  })

  test("preview lists at most five titles", () => {
    expect(batchDeletePreview(["1", "2", "3"])).toEqual({ shown: ["1", "2", "3"], more: false })
    const long = batchDeletePreview(["1", "2", "3", "4", "5", "6", "7"])
    expect(long.shown).toEqual(["1", "2", "3", "4", "5"])
    expect(long.more).toBe(true)
  })

  test("deletes with bounded concurrency, reports progress and keeps failures", async () => {
    let active = 0
    let peak = 0
    const progress: number[] = []
    const calls: string[] = []
    const result = await runBatchDelete(
      ["a", "b", "c", "d", "e"],
      async (id) => {
        calls.push(id)
        active++
        peak = Math.max(peak, active)
        await new Promise((resolve) => setTimeout(resolve, 5))
        active--

        if (id === "b") throw new Error("boom")

        if (id === "d") return false
      },
      { concurrency: 2, onProgress: (done) => progress.push(done) },
    )

    expect(peak).toBe(2)
    expect(calls.sort()).toEqual(["a", "b", "c", "d", "e"])
    expect(progress).toEqual([1, 2, 3, 4, 5])
    expect(result).toEqual({ deleted: ["a", "c", "e"], failed: ["b", "d"] })
  })

  test("a synchronous throw counts as one failure and the batch continues", async () => {
    const result = await runBatchDelete(["a", "b"], (id) => {
      if (id === "a") throw new Error("sync")

      return Promise.resolve()
    })

    expect(result).toEqual({ deleted: ["b"], failed: ["a"] })
  })

  test("empty batch resolves without calling remove", async () => {
    let called = false
    const result = await runBatchDelete([], async () => {
      called = true
    })

    expect(called).toBe(false)
    expect(result).toEqual({ deleted: [], failed: [] })
  })

  test("selection only counts listed sessions; select all toggles", () => {
    expect(visibleSelection({ a: true, gone: true, b: false }, ["a", "b", "c"])).toEqual(["a"])
    expect(toggleAll(["a", "b"], { a: true })).toEqual({ a: true, b: true })
    expect(toggleAll(["a", "b"], { a: true, b: true })).toEqual({ a: false, b: false })
  })
})
