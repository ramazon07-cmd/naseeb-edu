// A response body as JSON when it is JSON, else the raw text (null when empty).
export async function readPayload(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}
