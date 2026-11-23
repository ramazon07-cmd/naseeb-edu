import { useEffect, useRef, useState } from 'react'
import { t, tp } from '../i18n.js'
import { DEFAULT_EXPECTED_MS, STAGES, checkTimer, progressFraction, secondsLeft, stageIndex } from '../lib/checkProgress.js'

const TICK_MS = 500
const FINISH_MS = 450

// Estimated progress for the Naseeb AI check. Purely client-side: it is driven by
// elapsed time, never by extra requests. The start time lives in checkTimer (set
// where the request starts), so hiding and reopening the panel resumes the bar.
// When the check ends without `failed`, the bar fills to 100% briefly and goes away.
export default function CheckProgress({ active, failed = false }) {
  const [now, setNow] = useState(() => Date.now())
  const [finishing, setFinishing] = useState(false)
  const fallbackStart = useRef(Date.now())
  const wasActive = useRef(false)

  useEffect(() => {
    if (!active) return undefined
    fallbackStart.current = Date.now()
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS)
    return () => window.clearInterval(timer)
  }, [active])

  useEffect(() => {
    if (active) { wasActive.current = true; setFinishing(false); return undefined }
    if (!wasActive.current) return undefined
    wasActive.current = false
    if (failed) return undefined
    setFinishing(true)
    const timer = window.setTimeout(() => setFinishing(false), FINISH_MS)
    return () => window.clearTimeout(timer)
  }, [active, failed])

  if (!active && !(finishing && !failed)) return null

  const pending = checkTimer.state()
  const startedAt = pending?.startedAt ?? fallbackStart.current
  const total = pending?.expected || DEFAULT_EXPECTED_MS
  const elapsed = Math.max(0, now - startedAt)
  const done = !active
  const fraction = done ? 1 : progressFraction(elapsed, total)
  const percent = Math.round(fraction * 100)
  const left = done ? 0 : secondsLeft(elapsed, total)
  const stage = t(STAGES[done ? STAGES.length - 1 : stageIndex(elapsed, total)].label)
  const timeText = done ? t('Done') : left === null ? t('Almost done…') : tp('About {n} seconds left', left, { n: left })

  return <div className="el-check-progress">
    {/* Announced politely when the check starts and when the stage changes, not on every tick. */}
    <span className="el-sr-only" role="status" aria-live="polite">{done ? '' : stage}</span>
    <div className="el-check-progress-top" aria-hidden="true">
      <strong>{stage}…</strong>
      <span>{timeText}</span>
    </div>
    <div className="el-check-bar" role="progressbar" aria-label={t('Naseeb AI check progress')} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={percent} aria-valuetext={`${stage}. ${timeText}`}>
      <span style={{ width: `${percent}%` }} />
    </div>
    <p>{t('You can keep reading your essay while Naseeb AI works.')}</p>
  </div>
}
