import { memo } from 'react'
import { ChevronDown } from 'lucide-react'
import { t, tp } from '../i18n.js'
import { Popover, ProgressBar } from './ui.jsx'

const LABELS = {
  words: 'Words',
  chars: 'Characters',
  charsNoSpaces: 'Characters excluding spaces',
  pages: 'Pages',
}

export function counterText(mode, value, limit) {
  if (mode === 'words') return limit ? tp('{n} / {limit} words', limit, { n: value, limit }) : tp('{n} words', value, { n: value })
  if (mode === 'chars') return tp('{n} characters', value, { n: value })
  if (mode === 'charsNoSpaces') return tp('{n} characters without spaces', value, { n: value })
  return tp('{n} pages', value, { n: value })
}

// The status counter: pick what it shows (like Docs' word count) and for
// which part of the document. An optional word limit shows as "N / limit".
function Counter({ setting, onChange, tab, document, pages, limit, multipleTabs }) {
  const pagesAvailable = pages > 0
  const mode = setting.mode === 'pages' && !pagesAvailable ? 'words' : setting.mode
  const scope = mode === 'pages' || !multipleTabs ? 'tab' : setting.scope
  const counts = scope === 'tab' ? tab : document
  const value = mode === 'pages' ? pages : counts[mode]
  const over = mode === 'words' && limit ? counts.words > limit : false
  const rows = [
    pagesAvailable && ['pages', pages],
    ['words', counts.words],
    ['chars', counts.chars],
    ['charsNoSpaces', counts.charsNoSpaces],
  ].filter(Boolean)
  return <Popover label={t('Word count')} className="el-counter" buttonClassName={`el-counter-btn${over ? ' is-over' : ''}`} align="right"
    button={<>
      <span className="el-counter-text">{counterText(mode, value, mode === 'words' ? limit : null)}</span>
      {over && <span className="el-over">{t('{n} over', { n: counts.words - limit })}</span>}
      <ChevronDown size={14} aria-hidden="true" />
      {mode === 'words' && limit ? <ProgressBar ratio={counts.words / limit} over={over} label={t('{words} of {limit} words', { words: counts.words, limit })} /> : null}
    </>}>
    <div className="el-counter-panel">
      {multipleTabs && <div className="el-segmented is-small" role="group" aria-label={t('Count')}>
        <button type="button" aria-pressed={scope === 'tab'} className={scope === 'tab' ? 'is-on' : ''} onClick={() => onChange({ ...setting, scope: 'tab' })}>{t('This tab')}</button>
        <button type="button" aria-pressed={scope === 'document'} className={scope === 'document' ? 'is-on' : ''} disabled={mode === 'pages'}
          onClick={() => onChange({ ...setting, scope: 'document' })}>{t('Whole document')}</button>
      </div>}
      <div role="radiogroup" aria-label={t('Show in the status bar')} className="el-counter-rows">
        {rows.map(([id, count]) => <label key={id} className={`el-counter-row${mode === id ? ' is-on' : ''}`}>
          <input type="radio" name="el-counter-mode" checked={mode === id} onChange={() => onChange({ ...setting, mode: id })} />
          <span>{t(LABELS[id])}</span>
          <strong>{id === 'pages' ? pages : scope === 'tab' ? tab[id] : document[id]}</strong>
        </label>)}
      </div>
      {limit ? <p className="el-small">{t('Word limit: {limit}', { limit })}</p> : null}
    </div>
  </Popover>
}

export default memo(Counter)
