// What a college match card says about a university, as words in the student's language (backend college_match.py
// sends the facts: subject rank, SAT position, aid status, cost against budget, and notes as code + params).
import { t, tx } from '../i18n.js';
import { money } from './format.js';
import { bandLabel, matchingPrograms } from './college.js';

// "#12 in Computer Science, QS 2026", or the overall QS rank when the student has no mapped major.
export function subjectRankText(subject) {
  if (!subject) return '';
  if (subject.overall) return subject.rank_label ? tx`Overall QS rank #${subject.rank_label}` : '';
  if (subject.rank_label == null) return tx`No QS rank in ${subject.name}`;
  return tx`#${subject.rank_label} in ${subject.name}, QS ${String(subject.year)}`;
}

// The student's SAT against the university's published range, in words and numbers. Without a SAT the band
// compared the student's ACT ('act_used').
export function satPositionText(sat) {
  if (!sat) return '';
  if (sat.position === 'act_used') return tx`Compared using your ACT ${String(sat.score)}`;
  const range = sat.max ? `${sat.min}–${sat.max}` : `${sat.min}+`;
  if (sat.position === 'no_range') return t("No SAT range listed");
  if (sat.position === 'no_score') return tx`Add your SAT to compare with ${range}`;
  if (sat.position === 'below') return tx`SAT ${String(sat.score)}: below the usual range (${range})`;
  if (sat.position === 'above') return tx`SAT ${String(sat.score)}: above the usual range (${range})`;
  return tx`SAT ${String(sat.score)}: inside the usual range (${range})`;
}

// Where the student's academics stand against the students this university admits (chance academic_position:
// 0 at their 25th percentile, 1 at the 75th). An English key the caller translates with t().
export function academicStanding(position) {
  if (position == null) return null;
  if (position < 0) return 'Below most admitted students';
  if (position < 1) return 'Inside the middle 50%';
  return 'Above most admitted students';
}

export function costText(university) {
  const budget = money(university.budget_usd);
  if (university.cost_vs_budget === 'within') return tx`Within your budget of ${budget}`;
  if (university.cost_vs_budget === 'within_with_aid') return tx`Within your budget of ${budget} with the largest aid`;
  if (university.cost_vs_budget === 'over') return tx`Over your budget of ${budget}`;
  if (university.cost_vs_budget === 'no_budget') return t("Set your budget to compare");
  return t("Cost unknown");
}

// A note or hint from the server: a code and params, with the English text as a fallback.
export function matchMessage(entry) {
  const { code, params = {}, text } = entry;
  if (code === 'pick_major') return t("Pick your major for a better list");
  if (code === 'broad_area') return t("Name a specific major for a sharper list");
  if (code === 'filled_from') return tx`Too few universities in the ${bandLabel(params.group)} group fit you; ${params.count} from the ${bandLabel(params.from)} group were added.`;
  if (code === 'short_list') return tx`Only ${params.count} universities fit your profile and budget.`;
  if (code === 'test_needed') return tx`${params.count} universities were left out because they expect an SAT or ACT score; add yours to see them.`;
  if (code === 'aid_unknown') return tx`${params.count} universities were left out: the catalogue has no aid details.`;
  if (code === 'no_intl_aid') return tx`${params.count} universities were left out: they list no aid for students from abroad.`;
  if (code === 'over_budget_with_aid') return tx`${params.count} universities were left out: even with the largest aid they publish, you would pay more than your budget.`;
  if (code === 'no_admission_data') return tx`${params.count} universities were left out because the catalogue has no admission data to place them.`;
  return text;
}

// The line under the list: where the ranks come from, and who wrote the "Why these fit you" lines when shown.
export function matchFootnote(data, reasonsShown) {
  const source = data?.subjects?.length
    ? t("Matched with fixed rules from QS subject rankings 2026: the same profile always gets the same list. Bands are estimates, not admission decisions.")
    : t("Matched with fixed rules from the overall QS World University Rankings 2027: the same profile always gets the same list. Bands are estimates, not admission decisions.");
  return reasonsShown ? `${source} ${t("Why these fit you lines are written by Naseeb AI from these facts only.")}` : source;
}

// The program an application is filed under: the match's own suggested program ("BSc Computer Science") first, then
// the College Search matcher on the typed major, then the typed major itself.
export function applicationProgram(university, major) {
  return university.suggested_programs?.[0]?.name || matchingPrograms(university, major)[0]?.name || major || 'Undeclared';
}

// The stored match belongs to one generation. Closing the panel or refreshing the research profile moves on to a new
// generation with nothing stored, so the old universities and bands, and any response still in flight, are dropped.
export const idleMatch = (generation) => ({ loading: false, data: null, error: '', generation });
export const invalidateMatch = (generation) => idleMatch(generation + 1);

// The "Why these fit you" lines belong to one match list in one language: the key is match generation + language.
export const reasonsKey = (generation, language) => `${generation}:${language}`;
export const idleReasons = (key) => ({ key, status: 'idle', lines: {}, error: '' });

// What the panel shows for ``key``: lines written for another list or language are never shown.
export const reasonsView = (state, key) => state.key === key ? state : idleReasons(key);

// A response only lands when no newer ask (a newer list or language) replaced the state since it started.
export const beginReasons = (state, key) => ({ key, status: 'loading', lines: state.key === key ? state.lines : {}, error: '' });
export const finishReasons = (state, key, lines) => state.key === key ? { key, status: 'done', lines: lines || {}, error: '' } : state;
export const failReasons = (state, key, error) => state.key === key ? { ...state, status: 'error', error } : state;

// One add at a time: an individual Add is off while Add all runs, and Add all is off while an add is pending.
export const individualAddBusy = ({ busyId, addingAll }, id) => addingAll || busyId === id;
export const addAllBusy = ({ busyId, addingAll }) => addingAll || busyId != null;

// Add all skips what is already on the list (it may have been added since the loop began) and what has no band.
export function bulkAddTier(university, listed, tiers) {
  if (listed.has(university.id)) return null;
  return tiers[university.fit?.admission_band] || null;
}
