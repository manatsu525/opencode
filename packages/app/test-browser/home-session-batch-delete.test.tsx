import { afterEach, describe, expect, test } from "bun:test"
import { render } from "solid-js/web"
import zh from "@/runtime/i18n/zh"
import {
  BatchDeleteSummary,
  HomeSessionCheckbox,
  HomeSessionSelectionBar,
  type BatchDeleteTranslate,
} from "@/home/sessions/batch-delete-view"

const dict = zh as Record<string, string>
const t: BatchDeleteTranslate = (key, params) =>
  (dict[key] ?? key).replace(/{{\s*(\w+)\s*}}/g, (_, name: string) => String(params?.[name] ?? ""))

let dispose: (() => void) | undefined

function mount(view: () => any) {
  const root = document.createElement("div")
  document.body.append(root)
  const stop = render(view, root)
  dispose = () => {
    stop()
    root.remove()
  }

  return root
}

afterEach(() => {
  dispose?.()
  dispose = undefined
})

// Solid's hyperscript runtime treats zero-argument functions passed as props
// as reactive getters. Give event callbacks an arity of one so they arrive as
// plain handlers, as they do under the Solid compiler.
const handler = (fn: () => void) => Object.defineProperty(() => fn(), "length", { value: 1 }) as () => void

const button = (root: HTMLElement, action: string) =>
  root.querySelector<HTMLButtonElement>(`[data-action="${action}"]`)!

describe("Home session selection bar", () => {
  test("shows the count and wires select all, delete and cancel", () => {
    const clicks: string[] = []
    const root = mount(() => (
      <HomeSessionSelectionBar
        t={t}
        count={3}
        total={8}
        allSelected={false}
        progress={undefined}
        onToggleAll={handler(() => clicks.push("all"))}
        onDelete={handler(() => clicks.push("delete"))}
        onCancel={handler(() => clicks.push("cancel"))}
      />
    ))

    expect(clicks).toEqual([])
    expect(root.querySelector('[data-slot="selection-count"]')!.textContent).toBe("已选 3 项")
    expect(button(root, "home-session-select-all").textContent).toBe("全选")
    expect(button(root, "home-session-select-delete").textContent).toBe("删除")
    expect(button(root, "home-session-select-cancel").textContent).toBe("取消")
    button(root, "home-session-select-all").click()
    button(root, "home-session-select-delete").click()
    button(root, "home-session-select-cancel").click()
    expect(clicks).toEqual(["all", "delete", "cancel"])
  })

  test("offers deselect when everything is selected; delete is disabled with nothing selected", () => {
    const root = mount(() => (
      <div>
        <HomeSessionSelectionBar
          t={t}
          count={2}
          total={2}
          allSelected
          progress={undefined}
          onToggleAll={handler(() => {})}
          onDelete={handler(() => {})}
          onCancel={handler(() => {})}
        />
        <HomeSessionSelectionBar
          t={t}
          count={0}
          total={2}
          allSelected={false}
          progress={undefined}
          onToggleAll={handler(() => {})}
          onDelete={handler(() => {})}
          onCancel={handler(() => {})}
        />
      </div>
    ))
    const bars = root.querySelectorAll<HTMLElement>('[data-component="home-session-selection-bar"]')

    expect(button(bars[0]!, "home-session-select-all").textContent).toBe("取消全选")
    expect(button(bars[1]!, "home-session-select-delete").disabled).toBe(true)
  })

  test("shows progress and locks the controls while deleting", () => {
    const root = mount(() => (
      <HomeSessionSelectionBar
        t={t}
        count={3}
        total={3}
        allSelected
        progress={{ done: 1, total: 3 }}
        onToggleAll={handler(() => {})}
        onDelete={handler(() => {})}
        onCancel={handler(() => {})}
      />
    ))

    expect(root.querySelector('[data-slot="selection-count"]')!.textContent).toBe("正在删除 1/3…")
    expect(button(root, "home-session-select-all").disabled).toBe(true)
    expect(button(root, "home-session-select-delete").disabled).toBe(true)
    expect(button(root, "home-session-select-cancel").disabled).toBe(true)
  })

  test("checkbox reflects the selected state", () => {
    const root = mount(() => (
      <div>
        <HomeSessionCheckbox checked />
        <HomeSessionCheckbox checked={false} />
      </div>
    ))
    const boxes = root.querySelectorAll<HTMLElement>('[data-component="home-session-checkbox"]')

    expect(boxes[0]!.dataset.checked).toBe("true")
    expect(boxes[0]!.querySelector("svg")).not.toBeNull()
    expect(boxes[1]!.dataset.checked).toBeUndefined()
  })
})

describe("batch delete confirmation", () => {
  test("names the count, lists five titles, says 等 N 个 and notes skipped running sessions", () => {
    const titles = ["一", "二", "三", "四", "五", "六", "七"]
    const root = mount(() => <BatchDeleteSummary t={t} titles={titles} running={2} />)

    expect(root.querySelector('[data-slot="confirm"]')!.textContent).toBe(
      "删除 7 个会话？只删除对话记录，不删除工作区文件。",
    )
    expect(Array.from(root.querySelectorAll("li"), (li) => li.textContent)).toEqual(["一", "二", "三", "四", "五"])
    expect(root.querySelector('[data-slot="more"]')!.textContent).toBe("等 7 个")
    expect(root.querySelector('[data-slot="running"]')!.textContent).toContain("2 个正在运行")
  })

  test("short list has no 等 line and no running note", () => {
    const root = mount(() => <BatchDeleteSummary t={t} titles={["甲", "乙"]} running={0} />)

    expect(root.querySelectorAll("li").length).toBe(2)
    expect(root.querySelector('[data-slot="more"]')).toBeNull()
    expect(root.querySelector('[data-slot="running"]')).toBeNull()
  })

  test("all running: explains instead of offering a delete", () => {
    const root = mount(() => <BatchDeleteSummary t={t} titles={[]} running={3} />)

    expect(root.querySelector('[data-slot="all-running"]')!.textContent).toBe("所选会话都在运行中，请先停止后再删除。")
    expect(root.querySelector('[data-slot="confirm"]')).toBeNull()
  })
})
