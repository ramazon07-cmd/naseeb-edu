// What a college match card says about a university, as words in the student's language (backend college_match.py
// sends the facts: subject rank, SAT position, aid status, cost against budget, and notes as code + params).
import { t, tx } from '../i18n.js';
import { money } from './format.js';
import { bandLabel } from './college.js';

// "#12 in Computer Science, QS 2026", or the overall QS rank when the student has no mapped major.
export function subjectRankText(subject) {
  if (!subject) return '';
  if (subject.overall) return subject.rank_label ? tx`Overall QS rank #${subject.rank_label}` : '';
  if (subject.rank_label == null) return tx`No QS rank in ${subject.name}`;
  return tx`#${subject.rank_label} in ${subject.name}, QS ${String(subject.year)}`;
}

// The student's SAT against the university's published range, in words and numbers.
export function satPositionText(sat) {
  if (!sat) return '';
  const range = sat.max ? `${sat.min}–${sat.max}` : `${sat.min}+`;
  if (sat.position === 'no_range') return t("No SAT range listed");
  if (sat.position === 'no_score') return tx`Add your SAT to compare with ${range}`;
  if (sat.position === 'below') return tx`SAT ${String(sat.score)}: below the usual range (${range})`;
  if (sat.position === 'above') return tx`SAT ${String(sat.score)}: above the usual range (${range})`;
  return tx`SAT ${String(sat.score)}: inside the usual range (${range})`;
}

export function costText(university) {
  const budget = money(university.budget_usd);
  if (university.cost_vs_budget === 'within') return tx`Within your budget of ${budget}`;
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
  if (code === 'aid_unlisted') return tx`${params.count} universities were left out because the catalogue lists no aid for international students.`;
  if (code === 'no_admission_data') return tx`${params.count} universities were left out because the catalogue has no admission data to place them.`;
  return text;
}
