// Ships only the visitor's language. The translation tables under
// src/translations/ stay the single source (each entry holds every language);
// this plugin turns them into one virtual module per language at build time:
//   virtual:i18n/uz, virtual:i18n/ru, virtual:i18n/en
// i18n.js imports them lazily, so each becomes its own chunk (i18n-<lang>) and
// a visitor downloads only the one they need. English is the key itself and
// only has the small code-keyed table.
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const PREFIX = 'virtual:i18n/'
const RESOLVED = '\0' + PREFIX
const LANGUAGES = ['uz', 'ru', 'en']

export function i18nDictionaries() {
  const allPath = path.resolve(import.meta.dirname, '../src/translations/all.js')
  const tablesDir = path.dirname(allPath) + path.sep
  let server = null

  async function loadTables() {
    if (server) return (await server.ssrLoadModule(allPath)).TRANSLATIONS
    return (await import(pathToFileURL(allPath).href)).TRANSLATIONS
  }

  return {
    name: 'naseeb-i18n-dictionaries',
    config: () => ({ define: { __I18N_SPLIT__: 'true' } }),
    configureServer(devServer) { server = devServer },
    resolveId(id) { return id.startsWith(PREFIX) ? '\0' + id : null },
    async load(id) {
      if (!id.startsWith(RESOLVED)) return null
      const language = id.slice(RESOLVED.length)
      if (!LANGUAGES.includes(language)) throw new Error(`Unknown i18n language: ${language}`)
      this.addWatchFile(allPath)
      const tables = await loadTables()
      return `export default ${JSON.stringify(tables[language] || {})}`
    },
    handleHotUpdate({ file, server: devServer }) {
      if (!file.startsWith(tablesDir)) return
      for (const language of LANGUAGES) {
        const module = devServer.moduleGraph.getModuleById(RESOLVED + language)
        if (module) devServer.moduleGraph.invalidateModule(module)
      }
      devServer.ws.send({ type: 'full-reload' })
      return []
    },
  }
}
