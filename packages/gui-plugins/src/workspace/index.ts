import { builtinCatalog } from "@opencode/plugin/gui/builtin"
import { Plugin } from "@opencode/plugin/gui"
import en from "./i18n/en"

/** Deployment-specific: the authenticated workspace file service (`/files/*`) served beside the web app. */
export default Plugin.define({
  i18n: builtinCatalog({
    en,
    zh: () => import("./i18n/zh"),
    zht: () => import("./i18n/zht"),
  }),
})
