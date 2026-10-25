import { Pencil } from 'lucide-react';
import { t, tx } from '../i18n';
import { CxAvatar, CxTag, ReasonTags } from './counselorUi';
import { gradeText } from '../lib/format';
import { splitList } from '../lib/profileSections';
import { isQuiet, needsAttention } from '../lib/studentReasons';
import '../pages/counselor-students.css';

export function StatusTag({ reasons }) {
  if (needsAttention(reasons)) return <CxTag tone="late">{t("Needs you")}</CxTag>;
  if (reasons.some((reason) => reason.key === 'to_review')) return <CxTag tone="warn">{t("To review")}</CxTag>;
  if (isQuiet(reasons)) return <CxTag tone="quiet">{t("Quiet")}</CxTag>;
  return <CxTag tone="ok">{t("On track")}</CxTag>;
}

// A class the student has not picked yet is an empty slot, not an error: a dashed outline, no status colour.
export function GradeTag({ grade }) {
  return grade ? <CxTag>{gradeText(grade)}</CxTag> : <CxTag tone="pending">{t("Not chosen")}</CxTag>;
}

export function LateWork({ reasons }) {
  const late = reasons.filter((reason) => reason.key === 'late_task' || reason.key === 'missing_document');
  return late.length ? <ReasonTags reasons={late} /> : <span className="cx-faint">{t("No late work")}</span>;
}

export const targetText = (student) => splitList(student.target_countries).map((country) => t(country)).join(', ') || student.target_major || '';

export function CounselorStudentTable({ rows, selecting = false, selected, toggle, onPreview, onEdit }) {
  if (!rows.length) return <p className="cx-empty">{t("No students found.")}</p>;
  return <div className="cx-card cs-table-card">
    <table className="cs-table">
      <thead><tr>
        {selecting && <th scope="col" className="cs-check-col"><span className="sr-only">{t("Select")}</span></th>}
        <th scope="col">{t("Student")}</th><th scope="col">{t("Grade")}</th><th scope="col">{t("Late work")}</th><th scope="col">{t("Target")}</th><th scope="col">{t("Status")}</th>{onEdit && <th scope="col"><span className="sr-only">{t("Edit")}</span></th>}
      </tr></thead>
      <tbody>
        {rows.map(({ student, reasons, name }) => <tr key={student.id} className={selecting && selected.has(student.id) ? 'selected' : ''} onClick={() => (selecting ? toggle(student.id) : onPreview(student))}>
          {selecting && <td className="cs-check-col"><input type="checkbox" checked={selected.has(student.id)} onChange={() => toggle(student.id)} onClick={(event) => event.stopPropagation()} aria-label={tx`Select ${name}`} /></td>}
          <td>
            <div className="cx-person">
              <CxAvatar name={name} />
              <span className="cx-row-copy">
                <button type="button" className="cx-name-link" onClick={(event) => { event.stopPropagation(); if (selecting) toggle(student.id); else onPreview(student); }}>{name}</button>
              </span>
            </div>
          </td>
          <td data-label={t("Grade")} className="cs-col-grade"><GradeTag grade={student.grade} /></td>
          <td data-label={t("Late work")} className="cs-col-late"><LateWork reasons={reasons} /></td>
          <td data-label={t("Target")}>{targetText(student) || <span className="cx-faint">—</span>}</td>
          <td data-label={t("Status")} className="cs-col-status"><StatusTag reasons={reasons} /></td>
          {onEdit && <td className="cs-col-edit"><button type="button" className="icon-button" title={t("Edit")} aria-label={tx`Edit ${name}`} onClick={(event) => { event.stopPropagation(); onEdit(student); }}><Pencil size={16} /></button></td>}
        </tr>)}
      </tbody>
    </table>
  </div>;
}
