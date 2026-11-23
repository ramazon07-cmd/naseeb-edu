import { useEffect, useRef, useState } from 'react'
import { t, tp } from '../i18n.js'
import { STAGES, expectedDuration, progressFraction, recordDuration, secondsLeft, stageIndex } from '../lib/checkProgress.js'

const TICK_MS = 500
const FINISH_MS = 450

// Estimated progress for the Naseeb AI check. Purely client-side: it is driven by
// elapsed time, never by extra requests. `active` is true while the check runs;
// when it ends without `failed`, the bar fills to 100% briefly and goes away.
export default function CheckProgress({ active, failed = false }) {
  const [elapsed, setElapsed] = useState(0)
  const [finishing, setFinishing] = useState(false)
  const startedAt = useRef(0)
  const expected = useRef(0)

  useEffect(() => {
    if (!active) return undefined
    startedAt.current = Date.now()
    expected.current = expectedDuration()
    setElapsed(0)
    setFinishing(false)
    const timer = window.setInterval(() => setElapsed(Date.now() - startedAt.current), TICK_MS)
    return () => {
      window.clearInterval(timer)
      if (startedAt.current) {
        const took = Date.now() - startedAt.current
        startedAt.current = 0
        if (!failedRef.current) { recordDuration(took); setFinishing(true) }
      }
    }
  }, [active])

  const failedRef = useRef(failed)
  failedRef.current = failed

  useEffect(() => {
    if (!finishing) return undefined
    const timer = window.setTimeout(() => setFinishing(false), FINISH_MS)
    return () => window.clearTimeout(timer)
  }, [finishing])

  if (!active && !(finishing && !failed)) return null

  const done = !active
  const total = expected.current || expectedDuration()
  const fraction = done ? 1 : progressFraction(elapsed, total)
  const percent = Math.round(fraction * 100)
  const left = done ? 0 : secondsLeft(elapsed, total)
  const stage = t(STAGES[done ? STAGES.length - 1 : stageIndex(elapsed, total)].label)
  const timeText = done ? t('Done') : left === null ? t('Almost done…') : tp('About {n} seconds left', left, { n: left })

  return <div className="el-check-progress">
    <div className="el-check-progress-top">
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
