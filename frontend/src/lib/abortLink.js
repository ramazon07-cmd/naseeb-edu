// Ties a caller's AbortSignal and a timeout to one internal AbortController.
//
// fetch() binds the response body to the signal it was given, so for a stream the
// caller's abort must stay linked after the headers arrive: `release()` only
// clears the timeout, `unlink()` also drops the caller link (plain requests).
export function linkAbort(callerSignal, timeoutMs, timers = globalThis) {
  const controller = new AbortController()
  let timedOut = false
  const abortFromCaller = () => controller.abort()
  if (callerSignal?.aborted) controller.abort()
  else callerSignal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeoutId = timers.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    release: () => timers.clearTimeout(timeoutId),
    unlink: () => {
      timers.clearTimeout(timeoutId)
      callerSignal?.removeEventListener('abort', abortFromCaller)
    },
  }
}

function abortError() {
  return new DOMException('Aborted', 'AbortError')
}

// Reads a streamed text body, calling onText(textSoFar) per chunk. An abort of
// `signal` cancels the reader at once (even mid-read) and rejects with AbortError,
// so a Stop or Clear never lets later chunks through.
export async function readTextStream(body, signal, onText) {
  if (signal?.aborted) throw abortError()
  const reader = body.getReader()
  const decoder = new TextDecoder()
  const cancel = () => { reader.cancel().catch(() => {}) }
  signal?.addEventListener('abort', cancel, { once: true })
  let received = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (signal?.aborted) throw abortError()
      if (done) break
      received += decoder.decode(value, { stream: true })
      onText(received)
    }
    received += decoder.decode()
    return received
  } finally {
    signal?.removeEventListener('abort', cancel)
  }
}
