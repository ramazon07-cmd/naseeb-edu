import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(path.join(root, 'frontend/package.json'))
const parser = require('@babel/parser')
const traverse = require('@babel/traverse').default
const generate = require('@babel/generator').default
const t = require('@babel/types')

const appPath = path.join(root, 'frontend/src/App.jsx')
const source = fs.readFileSync(appPath, 'utf8')
const ast = parser.parse(source, { sourceType: 'module', plugins: ['jsx'] })
const translatedAttributes = new Set(['aria-label', 'description', 'hint', 'label', 'note', 'placeholder', 'text', 'title'])

const callTranslation = (value) => t.callExpression(t.identifier('t'), [t.stringLiteral(value)])
const normalized = (value) => String(value || '').replace(/\s+/g, ' ').trim()
const isTranslatable = (value) => /[A-Za-z]/.test(normalized(value))

traverse(ast, {
  JSXText(pathRef) {
    const original = pathRef.node.value
    const key = normalized(original)
    if (!isTranslatable(original)) return
    const prefix = original.match(/^\s*/)?.[0] || ''
    const suffix = original.match(/\s*$/)?.[0] || ''
    const nodes = []
    if (prefix) nodes.push(t.jsxText(prefix))
    nodes.push(t.jsxExpressionContainer(callTranslation(key)))
    if (suffix) nodes.push(t.jsxText(suffix))
    pathRef.replaceWithMultiple(nodes)
  },
  JSXAttribute(pathRef) {
    const name = pathRef.node.name?.name
    const value = pathRef.node.value
    if (!translatedAttributes.has(name) || value?.type !== 'StringLiteral' || !isTranslatable(value.value)) return
    pathRef.node.value = t.jsxExpressionContainer(callTranslation(normalized(value.value)))
  },
  JSXExpressionContainer(pathRef) {
    const attributeName = pathRef.parentPath?.node?.type === 'JSXAttribute' ? pathRef.parentPath.node.name?.name : null
    if (attributeName && !translatedAttributes.has(attributeName)) return
    const expression = pathRef.node.expression
    if (expression.type === 'StringLiteral' && isTranslatable(expression.value)) {
      pathRef.node.expression = callTranslation(normalized(expression.value))
      return
    }
    if (expression.type === 'ConditionalExpression') {
      for (const branch of ['consequent', 'alternate']) {
        const candidate = expression[branch]
        if (candidate.type === 'StringLiteral' && isTranslatable(candidate.value)) {
          expression[branch] = callTranslation(normalized(candidate.value))
        }
      }
    }
    pathRef.traverse({
      StringLiteral(stringPath) {
        if (stringPath.findParent((parent) => parent.isJSXExpressionContainer())?.node !== pathRef.node) return
        if (!isTranslatable(stringPath.node.value)) return
        const parent = stringPath.parentPath
        const renderedFallback = parent?.isLogicalExpression() && parent.node.right === stringPath.node
        const renderedConditional = parent?.isConditionalExpression()
          && (parent.node.consequent === stringPath.node || parent.node.alternate === stringPath.node)
        if (!renderedFallback && !renderedConditional) return
        stringPath.replaceWith(callTranslation(normalized(stringPath.node.value)))
        stringPath.skip()
      },
    })
  },
})

const output = generate(ast, {
  comments: true,
  compact: false,
  jsescOption: { minimal: true },
  retainLines: true,
}, source).code
fs.writeFileSync(appPath, `${output}\n`)
