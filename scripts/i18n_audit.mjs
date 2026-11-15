import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { createRequire } from 'node:module'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(path.join(root, 'frontend/package.json'))
const parser = require('@babel/parser')
const traverse = require('@babel/traverse').default
const generate = require('@babel/generator').default

const i18nPath = path.join(root, 'frontend/src/i18n.js')
// App.jsx plus every module split out of it (see frontend_smoke.js's own
// workspaceDirs) — most t()/tx calls live in pages/components/hooks/lib now,
// not App.jsx, so the audit has to parse all of them, not just the shell.
const workspaceDirs = ['frontend/src/pages', 'frontend/src/components', 'frontend/src/hooks', 'frontend/src/lib']
const workspaceFiles = [
  path.join(root, 'frontend/src/App.jsx'),
  ...workspaceDirs.filter((dir) => fs.existsSync(path.join(root, dir))).flatMap((dir) =>
    fs.readdirSync(path.join(root, dir)).filter((name) => /\.jsx?$/.test(name)).sort()
      .map((name) => path.join(root, dir, name))),
]
const keys = new Map()
const { TRANSLATIONS } = await import(`${path.toNamespacedPath(i18nPath)}?audit=${Date.now()}`)
const dictionary = Object.fromEntries(Object.entries(TRANSLATIONS).map(([language, messages]) => [language, new Set(Object.keys(messages))]))
const translatedAttributes = new Set(['aria-label', 'description', 'hint', 'label', 'note', 'placeholder', 'text', 'title'])
const translatedObjectProperties = new Set(['description', 'label', 'note', 'title'])
const feedbackCalls = new Set(['notify', 'setBootstrapError', 'setError'])
const dynamicIssues = []
// Set before each file's traversal: scanning many files now (not just
// App.jsx), so every recorded hit needs to say which one it came from.
let currentFile = ''

function normalized(value) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function addKey(value, line, origin) {
  const key = normalized(value)
  if (!key || !/[A-Za-z]/.test(key)) return
  if (!keys.has(key)) keys.set(key, [])
  keys.get(key).push({ file: currentFile, line, origin })
}

const visitors = {
  JSXAttribute(pathRef) {
    const name = pathRef.node.name?.name
    if (!translatedAttributes.has(name)) return
    const value = pathRef.node.value
    if (value?.type === 'StringLiteral') addKey(value.value, value.loc?.start.line, `prop:${name}`)
  },
  JSXText(pathRef) {
    addKey(pathRef.node.value, pathRef.node.loc?.start.line, 'jsx-text')
  },
  JSXExpressionContainer(pathRef) {
    const attributeName = pathRef.parentPath?.node?.type === 'JSXAttribute' ? pathRef.parentPath.node.name?.name : null
    if (attributeName && !translatedAttributes.has(attributeName)) return
    pathRef.traverse({
      StringLiteral(stringPath) {
        if (stringPath.findParent((parent) => parent.isJSXExpressionContainer())?.node !== pathRef.node) return
        if (stringPath.findParent((parent) => parent.isCallExpression() && ['t', 'tx'].includes(parent.node.callee?.name))) return
        const parent = stringPath.parentPath
        const directlyRendered = parent?.isJSXExpressionContainer()
        const renderedFallback = parent?.isLogicalExpression() && parent.node.right === stringPath.node
        const renderedConditional = parent?.isConditionalExpression()
          && (parent.node.consequent === stringPath.node || parent.node.alternate === stringPath.node)
        if (!directlyRendered && !renderedFallback && !renderedConditional) return
        const value = normalized(stringPath.node.value)
        if (!/[A-Za-z]/.test(value)) return
        const signature = `${stringPath.node.loc?.start.line}:${value}`
        if (!dynamicIssues.some((issue) => issue.signature === signature)) {
          dynamicIssues.push({ file: currentFile, line: stringPath.node.loc?.start.line, source: JSON.stringify(value), origin: 'jsx-string', signature })
        }
      },
      TemplateLiteral(templatePath) {
        if (templatePath.parentPath?.isTaggedTemplateExpression() && templatePath.parentPath.node.tag?.name === 'tx') return
        if (templatePath.findParent((parent) => parent.isCallExpression() && parent.node.callee?.name === 't')) return
        if (!templatePath.node.quasis.some((quasi) => /[A-Za-z]/.test(quasi.value.cooked || ''))) return
        if (templatePath.parentPath?.isTemplateLiteral()) return
        const expressionContainer = templatePath.findParent((parent) => parent.isJSXExpressionContainer())
        let ancestor = templatePath.parentPath
        while (ancestor && ancestor !== expressionContainer) {
          if (ancestor.isCallExpression() || ancestor.isNewExpression()) return
          ancestor = ancestor.parentPath
        }
        const attributePath = templatePath.findParent((parent) => parent.isJSXAttribute())
        const closestAttributeName = attributePath?.node?.name?.name
        if (closestAttributeName && !translatedAttributes.has(closestAttributeName)) return
        const source = generate(templatePath.node).code
        const signature = `${templatePath.node.loc?.start.line}:${source}`
        if (!dynamicIssues.some((issue) => issue.signature === signature)) dynamicIssues.push({ file: currentFile, line: templatePath.node.loc?.start.line, source, origin: 'jsx-template', signature })
      },
    })
  },
  TaggedTemplateExpression(pathRef) {
    if (pathRef.node.tag?.name !== 'tx') return
    const key = pathRef.node.quasi.quasis.reduce((result, quasi, index) => `${result}${quasi.value.cooked}${index < pathRef.node.quasi.expressions.length ? `{${index}}` : ''}`, '')
    addKey(key, pathRef.node.loc?.start.line, 'tx``')
  },
  CallExpression(pathRef) {
    if (pathRef.node.callee.type === 'Identifier' && pathRef.node.callee.name === 't') {
      const argument = pathRef.node.arguments[0]
      if (argument?.type === 'StringLiteral') addKey(argument.value, argument.loc?.start.line, 't()')
    }
    // tp(key, count, vars): the plural pattern is its own key, same as t() — the
    // t()-only check above never covered `tp`, so plural strings sitting apart
    // from any t()/tx use never got a coverage check.
    if (pathRef.node.callee.type === 'Identifier' && pathRef.node.callee.name === 'tp') {
      const argument = pathRef.node.arguments[0]
      if (argument?.type === 'StringLiteral') addKey(argument.value, argument.loc?.start.line, 'tp()')
    }
    const calleeName = pathRef.node.callee?.name
    const isConfirm = pathRef.node.callee?.type === 'MemberExpression'
      && pathRef.node.callee.object?.name === 'window'
      && pathRef.node.callee.property?.name === 'confirm'
    if (!feedbackCalls.has(calleeName) && !isConfirm) return
    const argument = pathRef.node.arguments[0]
    if (!argument) return
    const inspectFeedbackNode = (candidate) => {
      if (!candidate) return
      if (candidate.type === 'CallExpression' && ['t', 'tx'].includes(candidate.callee?.name)) return
      if (candidate.type === 'TaggedTemplateExpression' && candidate.tag?.name === 'tx') return
      if (candidate.type === 'ConditionalExpression') {
        inspectFeedbackNode(candidate.consequent)
        inspectFeedbackNode(candidate.alternate)
        return
      }
      if (candidate.type === 'LogicalExpression') {
        inspectFeedbackNode(candidate.right)
        return
      }
      if (candidate.type !== 'StringLiteral' && candidate.type !== 'TemplateLiteral') return
      if (!normalized(candidate.value || candidate.quasis?.map((quasi) => quasi.value.cooked).join(''))) return
      const signature = `${candidate.loc?.start.line}:${generate(candidate).code}`
      if (!dynamicIssues.some((issue) => issue.signature === signature)) {
        dynamicIssues.push({ file: currentFile, line: candidate.loc?.start.line, source: generate(candidate).code, origin: isConfirm ? 'confirm' : calleeName, signature })
      }
    }
    inspectFeedbackNode(argument)
  },
  ObjectProperty(pathRef) {
    const propertyName = pathRef.node.key?.name || pathRef.node.key?.value
    if (!translatedObjectProperties.has(propertyName)) return
    if (pathRef.node.value?.type === 'StringLiteral') {
      addKey(pathRef.node.value.value, pathRef.node.value.loc?.start.line, `object:${propertyName}`)
    }
  },
}

for (const filePath of workspaceFiles) {
  currentFile = path.relative(root, filePath)
  const fileAst = parser.parse(fs.readFileSync(filePath, 'utf8'), { sourceType: 'module', plugins: ['jsx'] })
  traverse(fileAst, visitors)
}

const apiPath = path.join(root, 'frontend/src/api.js')
currentFile = path.relative(root, apiPath)
const apiAst = parser.parse(fs.readFileSync(apiPath, 'utf8'), { sourceType: 'module' })
traverse(apiAst, {
  CallExpression(pathRef) {
    if (pathRef.node.callee?.name !== 't') return
    const argument = pathRef.node.arguments[0]
    if (argument?.type === 'StringLiteral') addKey(argument.value, argument.loc?.start.line, 'api:t()')
  },
  NewExpression(pathRef) {
    if (pathRef.node.callee?.name !== 'ApiError') return
    const argument = pathRef.node.arguments[0]
    if (argument?.type === 'StringLiteral' || argument?.type === 'TemplateLiteral') {
      dynamicIssues.push({ file: currentFile, line: argument.loc?.start.line, source: generate(argument).code, origin: 'api-error' })
    }
  },
})

const missing = [...keys.keys()].filter((key) => !dictionary.uz.has(key) || !dictionary.ru.has(key)).sort()
if (process.argv.includes('--list')) {
  for (const key of missing) {
    const first = keys.get(key)[0]
    console.log(`${first.file}:${first.line}\t${first.origin}\t${key}`)
  }
  for (const issue of dynamicIssues) console.log(`${issue.file}:${issue.line}\t${issue.origin}\t${issue.source}`)
}
console.log(`UI keys: ${keys.size}; missing uz/ru keys: ${missing.length}; untranslated dynamic messages: ${dynamicIssues.length}`)
if (missing.length || dynamicIssues.length) process.exitCode = 1
