// The four-letter type code, derived from the Big Five scores of challenge 1.
//
// NOTE ON SCOPE: this file deliberately contains NO archetypes, characters or
// historical figures. Those belong to TestMind and are its differentiator --
// shipping them here would put them in a public JavaScript bundle that anyone
// can read. Naseeb Edu shows the code; TestMind shows the character. One label
// per product.
//
// The mapping is the one 16Personalities uses: their published theory says they
// dropped Jung's cognitive functions as unmeasurable and rebalanced the Big
// Five instead. Note the two reversals -- high Agreeableness is FEELING, and
// Emotional steadiness drives the Assertive/Turbulent suffix, which is the
// fifth axis a Jungian instrument does not have at all.

export const TYPE_AXES = [
  { trait: 'E',  low: 'I', high: 'E', name: 'Mind',     lowName: 'Introverted', highName: 'Extraverted' },
  { trait: 'O',  low: 'S', high: 'N', name: 'Energy',   lowName: 'Observant',   highName: 'Intuitive' },
  { trait: 'A',  low: 'T', high: 'F', name: 'Nature',   lowName: 'Thinking',    highName: 'Feeling' },
  { trait: 'C',  low: 'P', high: 'J', name: 'Tactics',  lowName: 'Prospecting', highName: 'Judging' },
  { trait: 'ES', low: 'T', high: 'A', name: 'Identity', lowName: 'Turbulent',   highName: 'Assertive' },
]

// Trait means run 1..5, so the midpoint is 3 and the half-span is 2.
export const TYPE_MIDPOINT = 3
// Within this of the midpoint the letter would flip if the student answered one
// or two items differently, so the UI marks it rather than printing all five in
// the same confident type.
export const TYPE_BORDERLINE = 0.35

export function typeCodeOf(scores) {
  const letters = {}, margins = {}, borderline = []
  for (const axis of TYPE_AXES) {
    const value = scores[axis.trait]
    letters[axis.trait] = value >= TYPE_MIDPOINT ? axis.high : axis.low
    margins[axis.trait] = Math.abs(value - TYPE_MIDPOINT)
    if (margins[axis.trait] <= TYPE_BORDERLINE) borderline.push(axis.trait)
  }
  // Printed in the order everyone recognises: Mind, Energy, Nature, Tactics,
  // then the Identity suffix.
  const four = TYPE_AXES.slice(0, 4).map((axis) => letters[axis.trait]).join('')
  return { code: `${four}-${letters.ES}`, four, letters, margins, borderline }
}
