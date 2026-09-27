import { useState } from 'react'
import { Lightbulb } from 'lucide-react'
import { t } from '../i18n.js'
import { Dialog, FolderSelect } from './ui.jsx'
import { ESSAY_TYPES, essayLabApi } from './essayLabApi.js'

export const COMMON_APP_PROMPTS = [
  { short: 'Background, identity, interest or talent', text: 'Some students have a background, identity, interest, or talent that is so meaningful they believe their application would be incomplete without it. If this sounds like you, then please share your story.' },
  { short: 'A challenge, setback or failure', text: 'The lessons we take from obstacles we encounter can be fundamental to later success. Recount a time when you faced a challenge, setback, or failure. How did it affect you, and what did you learn from the experience?' },
  { short: 'Questioning a belief or idea', text: 'Reflect on a time when you questioned or challenged a belief or idea. What prompted your thinking? What was the outcome?' },
  { short: 'Unexpected gratitude', text: 'Reflect on something that someone has done for you that has made you happy or thankful in a surprising way. How has this gratitude affected or motivated you?' },
  { short: 'Personal growth', text: 'Discuss an accomplishment, event, or realization that sparked a period of personal growth and a new understanding of yourself or others.' },
  { short: 'Something that makes you lose track of time', text: 'Describe a topic, idea, or concept you find so engaging that it makes you lose all track of time. Why does it captivate you? What or who do you turn to when you want to learn more?' },
  { short: 'Any topic of your choice', text: "Share an essay on any topic of your choice. It can be one you've already written, one that responds to a different prompt, or one of your own design." },
]

const WHY_US = /\bwhy\b.*\b(us|our|this (university|college|school|program)|interested in|attend)\b|\bwhy (are you|do you want)\b/i

function initialPromptChoice(essay) {
  if (!essay) return 1
  const index = COMMON_APP_PROMPTS.findIndex((prompt) => prompt.text === essay.prompt)
  return index >= 0 ? index : (essay.prompt ? 'own' : 1)
}

function defaultTitle(type, { university, scholarship }) {
  if (type === 'personal_statement') return 'Common App — Personal Statement'
  if (type === 'supplement') return university ? `${university} — Supplement` : 'Supplement'
  if (type === 'scholarship') return scholarship ? `${scholarship} — Scholarship essay` : 'Scholarship essay'
  return 'Free writing'
}

// Create a new essay, or (with `essay`) edit its type, question, university, limit and folder.
export default function NewEssay({ folders, defaultFolder = null, essay = null, onClose, onCreated, onSaved, notify = () => {} }) {
  const editing = Boolean(essay)
  const [type, setType] = useState(essay?.essay_type || 'personal_statement')
  const [promptChoice, setPromptChoice] = useState(() => initialPromptChoice(essay))
  const [showAllPrompts, setShowAllPrompts] = useState(() => typeof initialPromptChoice(essay) === 'number' && initialPromptChoice(essay) > 1)
  const [ownPrompt, setOwnPrompt] = useState(() => (essay && initialPromptChoice(essay) === 'own' ? essay.prompt : ''))
  const [question, setQuestion] = useState(essay?.prompt || '')
  const [university, setUniversity] = useState(essay?.university_name || '')
  const [wordLimit, setWordLimit] = useState(essay?.word_limit ? String(essay.word_limit) : '')
  const [folder, setFolder] = useState(essay ? essay.folder ?? null : defaultFolder)
  const [title, setTitle] = useState(essay?.title || '')
  const [titleTouched, setTitleTouched] = useState(editing)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const autoTitle = defaultTitle(type, { university: university.trim(), scholarship: university.trim() })
  const shownTitle = titleTouched ? title : autoTitle
  const looksLikeWhyUs = type === 'supplement' && WHY_US.test(question)

  // A word limit is optional: empty means none.
  const effectiveLimit = wordLimit.trim()

  const prompt = type === 'personal_statement'
    ? (promptChoice === 'own' ? ownPrompt.trim() : COMMON_APP_PROMPTS[promptChoice]?.text || '')
    : type === 'free_writing' ? '' : question.trim()

  async function submit(event) {
    event.preventDefault()
    const limit = effectiveLimit ? Number(effectiveLimit) : null
    if (limit !== null && (!Number.isInteger(limit) || limit < 1 || limit > 20000)) {
      setError(t('Word limit must be a whole number between 1 and 20000, or empty.'))
      return
    }
    const payload = {
      title: (shownTitle || autoTitle).trim().slice(0, 220),
      essay_type: type,
      prompt,
      university_name: type === 'supplement' || type === 'scholarship' ? university.trim().slice(0, 220) : '',
      word_limit: type === 'free_writing' ? null : limit,
      folder: folder ?? null,
    }
    if (!editing) payload.first_tab_title = t('Tab {n}', { n: 1 })
    setSaving(true)
    setError('')
    try {
      if (editing) onSaved?.(await essayLabApi.updateEssay(essay.id, payload))
      else onCreated?.(await essayLabApi.createEssay(payload))
    } catch (err) {
      setError(err?.message || t('Could not save. Try again.'))
      notify(err?.message || t('Could not save. Try again.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const footer = <>
    <span className="el-foot-note">{editing ? t('Your text stays exactly as it is.') : t('You can change the question any time from the top of the page.')}</span>
    <button type="button" className="el-btn" onClick={onClose}>{t('Cancel')}</button>
    <button type="submit" form="el-new-essay" className="el-btn is-primary" disabled={saving} aria-busy={saving}>
      {saving ? t('Saving…') : editing ? t('Save changes') : t('Create and start writing')}
    </button>
  </>

  return <Dialog title={editing ? t('Essay details') : t('New essay')} onClose={onClose} footer={footer} wide>
    <form id="el-new-essay" className="el-form" onSubmit={submit}>
      <fieldset className="el-field">
        <legend className="el-label">{t('What are you writing?')}</legend>
        <div className="el-type-grid">
          {ESSAY_TYPES.map((kind) => <button key={kind.id} type="button" className={`el-type${type === kind.id ? ' is-on' : ''}`} aria-pressed={type === kind.id}
            data-autofocus={type === kind.id ? '' : undefined} onClick={() => setType(kind.id)}>
            <strong>{t(kind.name)}</strong><span>{t(kind.hint)}</span>
          </button>)}
        </div>
      </fieldset>

      {type === 'personal_statement' && <fieldset className="el-field">
        <legend className="el-label">{t('Pick a Common App prompt, or write your own')}</legend>
        <div className="el-radio-list">
          {COMMON_APP_PROMPTS.map((item, index) => (index < 2 || showAllPrompts || promptChoice === index) && <label key={item.short} className={`el-radio${promptChoice === index ? ' is-on' : ''}`} title={item.text}>
            <input type="radio" name="el-prompt" checked={promptChoice === index} onChange={() => setPromptChoice(index)} />
            <span>{index + 1} · {t(item.short)}</span>
          </label>)}
          {!showAllPrompts && <button type="button" className="el-radio is-more" onClick={() => setShowAllPrompts(true)}>{t('3–7 · More prompts…')}</button>}
          <label className={`el-radio is-own${promptChoice === 'own' ? ' is-on' : ''}`}>
            <input type="radio" name="el-prompt" checked={promptChoice === 'own'} onChange={() => setPromptChoice('own')} />
            <span>{t('Type my own prompt')}</span>
          </label>
        </div>
        {promptChoice === 'own'
          ? <textarea className="el-textarea" aria-label={t('Your prompt')} placeholder={t('Paste or type the prompt')} value={ownPrompt} onChange={(event) => setOwnPrompt(event.target.value)} />
          : <p className="el-prompt-text">{COMMON_APP_PROMPTS[promptChoice]?.text}</p>}
      </fieldset>}

      {type === 'supplement' && <div className="el-field">
        <label className="el-label" htmlFor="el-question">{t("The question, in your university's words")}</label>
        <textarea id="el-question" className="el-textarea" placeholder={t('Paste or type the question they ask')} value={question} onChange={(event) => setQuestion(event.target.value)} />
        {looksLikeWhyUs && <div className="el-hint" role="note"><Lightbulb size={16} aria-hidden="true" />
          <span>{t('Looks like a “Why us?” question. Coach will look for real courses or people you name, why you fit, and details only this university has.')}</span></div>}
      </div>}

      {type === 'scholarship' && <div className="el-field">
        <label className="el-label" htmlFor="el-scholarship">{t('Scholarship name and question')}</label>
        <input id="el-scholarship" className="el-input" placeholder={t('Scholarship name')} value={university} onChange={(event) => setUniversity(event.target.value)} maxLength={220} />
        <textarea className="el-textarea" aria-label={t('Scholarship question')} placeholder={t('Paste or type the question they ask')} value={question} onChange={(event) => setQuestion(event.target.value)} />
      </div>}

      {type === 'free_writing' && <div className="el-note-box">
        <strong>{t('No question, no limit.')}</strong>
        <span>{t('Free writing is for brainstorming memories and ideas. Coach stays off unless you ask. You can turn it into an essay later.')}</span>
      </div>}

      <div className={`el-field-row${type === 'supplement' ? ' has-three' : ''}`}>
        {type === 'supplement' && <div className="el-field">
          <label className="el-label" htmlFor="el-university">{t('University')} <span className="el-optional">{t('(optional)')}</span></label>
          <input id="el-university" className="el-input" value={university} onChange={(event) => setUniversity(event.target.value)} maxLength={220} />
        </div>}
        {type !== 'free_writing' && <div className="el-field">
          <label className="el-label" htmlFor="el-limit">{t('Word limit')} <span className="el-optional">{t('(optional)')}</span></label>
          <input id="el-limit" className="el-input" inputMode="numeric" value={wordLimit} placeholder={type === 'personal_statement' ? t('e.g. {n}', { n: 650 }) : ''}
            onChange={(event) => setWordLimit(event.target.value.replace(/[^0-9]/g, ''))} aria-describedby="el-limit-hint" />
          <span id="el-limit-hint" className="el-small">{t('Or leave empty for none')}</span>
        </div>}
        <div className="el-field">
          <label className="el-label" htmlFor="el-folder">{t('Folder')}</label>
          <FolderSelect id="el-folder" folders={folders} value={folder} onChange={setFolder} />
        </div>
      </div>

      <div className="el-field">
        <label className="el-label" htmlFor="el-title">{t('Title')}</label>
        <input id="el-title" className="el-input" value={shownTitle} maxLength={220}
          onChange={(event) => { setTitleTouched(true); setTitle(event.target.value) }} />
      </div>
      {error && <div className="el-alert is-error" role="alert">{error}</div>}
    </form>
  </Dialog>
}
