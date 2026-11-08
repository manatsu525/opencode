import { createEffect, createMemo, type Accessor } from "solid-js"

/** Mobile chat has no terminal pane. Repair only its persisted open flag, not PTYs. */
export function createMobileTerminalVisibility(input: {
  desktop: Accessor<boolean>
  opened: Accessor<boolean>
  close: () => void
}) {
  // Mask immediately, including before async persisted layout hydration finishes.
  const visible = createMemo(() => input.desktop() && input.opened())
  createEffect(() => {
    if (!input.desktop() && input.opened()) input.close()
  })
  return visible
}
