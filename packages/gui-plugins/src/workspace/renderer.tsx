import { lazy, onCleanup, Show, Suspense } from "solid-js"
import { Command, MenuItem, usePanel, type Plugin } from "@opencode/plugin/gui"
import { BuiltinPanel, onIdle, type BuiltinPanelTab } from "@opencode/plugin/gui/builtin"
import type definition from "./index"

const setup: Plugin.Setup<typeof definition> = (ctx) => {
  const View = lazy(() => import("./view"))
  onCleanup(onIdle(() => void View.preload()))

  const key = `${ctx.id}:main`

  const tab: BuiltinPanelTab = {
    id: "main",
    get title() {
      return ctx.t("tab.title")
    },
    closable: "hover",
  }

  const open = () => {
    const session = ctx.sessions.current()

    if (session) ctx.layout.open(key, session)
  }

  ctx.add(
    BuiltinPanel,
    (): BuiltinPanel => ({
      id: "main",
      region: "side",
      mobile: { title: ctx.t("mobile.title"), order: 25, kind: "menu", icon: "folder" },
      list: (input) => (input.open.includes("main") ? [tab] : []),
      closed: () => ({ icon: "folder" }),
      render: () => {
        const panel = usePanel()

        return (
          <Show
            when={panel.placement() !== "mobile"}
            fallback={
              <Suspense>
                <View />
              </Suspense>
            }
          >
            <div class="relative flex min-h-0 flex-1 flex-col overflow-hidden">
              <Suspense>
                <View />
              </Suspense>
            </div>
          </Show>
        )
      },
    }),
  )

  ctx.add(
    Command,
    (): Command => ({
      id: "open",
      title: ctx.t("command.open"),
      enabled: !!ctx.sessions.current(),
      run: open,
    }),
  )

  ctx.add(
    MenuItem,
    (): MenuItem => ({
      menu: "session.panel",
      id: "open",
      title: ctx.t("command.open"),
      icon: "folder",
      order: 31,
      run: open,
    }),
  )
}

export default setup
