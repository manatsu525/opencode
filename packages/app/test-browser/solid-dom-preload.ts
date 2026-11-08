// Use the existing Vite/Solid compiler for DOM component tests. Bun's hyperscript
// preload suffices for pure functions but currently loses JSX helper bindings.
import { plugin } from "bun"
import { createRequire } from "node:module"
const requireSolid = createRequire(import.meta.resolve("vite-plugin-solid"))
const babel = requireSolid("@babel/core")
plugin({
  name: "solid-dom-test-compiler",
  setup(build) {
    build.onLoad({ filter: /\.[jt]sx$/ }, async ({ path }) => ({
      contents: babel.transformSync(await Bun.file(path).text(), {
        filename: path,
        babelrc: false,
        configFile: false,
        plugins: [[requireSolid.resolve("@babel/plugin-transform-typescript"), { isTSX: true, allExtensions: true, allowDeclareFields: true }]],
        presets: [[requireSolid.resolve("babel-preset-solid"), { generate: "dom", hydratable: false }]],
      }).code,
      loader: "js",
    }))
  },
})
