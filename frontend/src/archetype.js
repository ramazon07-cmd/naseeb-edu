// GENERATED from TestMind's strings.js -- do not edit by hand.
//
// The ten names and the four-letter code are two readings of ONE Big Five
// result: the code asks which side of the middle each trait sits on, the name
// asks which two traits stand out. Neither is a second test.
//
// Deliberately NAMES ONLY. The historical figures and Uzbek names live in
// TestMind and must not be shipped in this bundle -- see gen_archetypes.js.

export const TRAIT_ORDER = ["ES","E","O","A","C"]

// Keyed by the two strongest traits, so all C(5,2) = 10 pairs are covered.
export const ARCHETYPE_NAME = {
  "ES|E": "Leader",
  "ES|O": "Explorer",
  "ES|A": "Trusted Friend",
  "ES|C": "Planner",
  "E|O": "Creator",
  "E|A": "Heart of the Group",
  "E|C": "Organiser",
  "O|A": "Kind Soul",
  "O|C": "Visionary",
  "A|C": "True to Their Word"
}

const rank = (scores) => TRAIT_ORDER.slice().sort((a, b) =>
  (scores[b] - scores[a]) || (TRAIT_ORDER.indexOf(a) - TRAIT_ORDER.indexOf(b)))

export function archetypeKeyOf(scores) {
  const ranked = rank(scores)
  const pair = [ranked[0], ranked[1]].sort((a, b) => TRAIT_ORDER.indexOf(a) - TRAIT_ORDER.indexOf(b))
  return pair[0] + '|' + pair[1]
}

export const archetypeNameOf = (scores) => ARCHETYPE_NAME[archetypeKeyOf(scores)]
