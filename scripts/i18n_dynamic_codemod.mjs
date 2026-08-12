import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(path.join(root, 'frontend/package.json'))
const parser = require('@babel/parser')
const traverse = require('@babel/traverse').default
const generate = require('@babel/generator').default
const types = require('@babel/types')

const appPath = path.join(root, 'frontend/src/App.jsx')
const source = fs.readFileSync(appPath, 'utf8')
const ast = parser.parse(source, { sourceType: 'module', plugins: ['jsx'] })
const translatedAttributes = new Set(['aria-label', 'description', 'hint', 'label', 'note', 'placeholder', 'text', 'title'])
const feedbackCalls = new Set(['notify', 'setBootstrapError', 'setError'])
const normalized = (value) => String(value || '').replace(/\s+/g, ' ').trim()

function isRenderedTemplate(templatePath) {
  if (templatePath.parentPath?.isTaggedTemplateExpression()) return false
  if (!templatePath.node.quasis.some((quasi) => /[A-Za-z]/.test(quasi.value.cooked || ''))) return false
  if (templatePath.parentPath?.isTemplateLiteral()) return false
  const expressionContainer = templatePath.findParent((parent) => parent.isJSXExpressionContainer())
  if (!expressionContainer) return false
  const attributePath = templatePath.findParent((parent) => parent.isJSXAttribute())
  const attributeName = attributePath?.node?.name?.name
  if (attributeName && !translatedAttributes.has(attributeName)) return false
  let ancestor = templatePath.parentPath
  while (ancestor && ancestor !== expressionContainer) {
    if (ancestor.isCallExpression() || ancestor.isNewExpression()) return false
    ancestor = ancestor.parentPath
  }
  return true
}

traverse(ast, {
  TemplateLiteral(pathRef) {
    if (!isRenderedTemplate(pathRef)) return
    pathRef.replaceWith(types.taggedTemplateExpression(types.identifier('tx'), pathRef.node))
  },
  CallExpression(pathRef) {
    const calleeName = pathRef.node.callee?.name
    const isConfirm = pathRef.node.callee?.type === 'MemberExpression'
      && pathRef.node.callee.object?.name === 'window'
      && pathRef.node.callee.property?.name === 'confirm'
    if (!feedbackCalls.has(calleeName) && !isConfirm) return
    const argument = pathRef.node.arguments[0]
    if (argument?.type === 'StringLiteral' && normalized(argument.value)) {
      pathRef.node.arguments[0] = types.callExpression(types.identifier('t'), [types.stringLiteral(argument.value)])
    } else if (argument?.type === 'TemplateLiteral') {
      pathRef.node.arguments[0] = types.taggedTemplateExpression(types.identifier('tx'), argument)
    }
  },
})

fs.writeFileSync(appPath, `${generate(ast, { comments: true, compact: false, jsescOption: { minimal: true }, retainLines: true }, source).code}\n`)
