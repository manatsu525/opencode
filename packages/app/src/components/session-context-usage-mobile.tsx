import type { JSX, ParentProps } from "solid-js"
import { Popover } from "@opencode-ai/ui/popover"

/** A touch target and a dismissible popover, not a hover-only tooltip on phones. */
export function MobileContextUsage(props: ParentProps<{ title: string; trigger: JSX.Element }>) {
  return <Popover
    title={props.title}
    placement="bottom-end"
    class="w-80 max-w-[calc(100vw-24px)]"
    triggerAs="button"
    triggerProps={{ type: "button", "aria-label": props.title, class: "flex size-10 shrink-0 items-center justify-center rounded-md" }}
    trigger={props.trigger}
  >
    <div data-component="mobile-context-usage">{props.children}</div>
  </Popover>
}
