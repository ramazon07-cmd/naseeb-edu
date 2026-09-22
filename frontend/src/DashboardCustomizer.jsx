import { useEffect, useRef, useState } from 'react';
import { ArrowLeftRight, GripVertical, Minus, Plus } from 'lucide-react';
import { t } from './i18n';
import { moveDashboardWidget, normalizeDashboardPreferences } from './dashboardPreferences';

const descriptions = {
  roadmap: 'Your study goal, level, and overall progress.',
  journey: 'Your study goal, level, and overall progress.',
  tasks: 'Assignments and upcoming deadlines.',
  meetings: 'Your upcoming counselor meetings.',
  applications: 'University applications, essays, and achievements.',
  discovery: 'Explore your strengths and university matches.',
  team: 'Your counselors and school contacts.',
};
export default function DashboardCustomizer({ draft, setDraft, metadata, Modal, onClose, onSave }) {
  const [dragged, setDragged] = useState(null);
  const pointerDrag = useRef(null);
  useEffect(() => {
    function pointerMove(event) {
      const drag = pointerDrag.current;
      if (!drag) return;
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 5) {
        drag.active = true;
        setDragged(drag.id);
        const modal = event.target.closest?.('.dashboard-customize-modal');
        if (modal) { const bounds = modal.getBoundingClientRect(); if (event.clientY > bounds.bottom - 40) modal.scrollTop += 12; else if (event.clientY < bounds.top + 40) modal.scrollTop -= 12; }
      }
    }
    function pointerUp(event) {
      const drag = pointerDrag.current;
      pointerDrag.current = null;
      setDragged(null);
      if (!drag?.active) return;
      const target = document.elementFromPoint(event.clientX, event.clientY);
      const column = target?.closest('[data-widget-column]')?.dataset.widgetColumn;
      const before = target?.closest('[data-widget-id]')?.dataset.widgetId || null;
      if (!['main', 'rail'].includes(column) || before === drag.id) return;
      setDraft((current) => moveDashboardWidget(current, drag.id, column, before));
      setAnnouncement(t('Widget moved'));
    }
    function cancel() { pointerDrag.current = null; setDragged(null); }
    document.addEventListener('pointermove', pointerMove);
    document.addEventListener('pointerup', pointerUp);
    document.addEventListener('pointercancel', cancel);
    return () => {document.removeEventListener('pointermove', pointerMove);document.removeEventListener('pointerup', pointerUp);document.removeEventListener('pointercancel', cancel);};
  }, [setDraft]);
  const [announcement, setAnnouncement] = useState('');
  const groups = ['main', 'rail', 'hidden'];
  const names = { main: 'Main column', rail: 'Side rail', hidden: 'Hidden widgets' };
  const itemsFor = (column) => draft.order.filter((id) => column === 'hidden' ? draft.hidden.includes(id) : !draft.hidden.includes(id) && (column === 'rail' ? draft.rail.includes(id) : !draft.rail.includes(id)));
  function move(id, column, before = null) {
    if (id === before) return;
    setDraft((current) => moveDashboardWidget(current, id, column, before));
    setAnnouncement(`${t(metadata[id][0])}: ${t(names[column])}`);
    setDragged(null);
  }
  function keyboardMove(event, id, column, items) {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const index = items.indexOf(id);
    const other = index + (event.key === 'ArrowUp' ? -1 : 1);
    if (other < 0 || other >= items.length) return;
    setDraft((current) => { const order = [...current.order]; const a = order.indexOf(id); const b = order.indexOf(items[other]); [order[a], order[b]] = [order[b], order[a]]; return {...current, order}; });
    setAnnouncement(`${t(metadata[id][0])}: ${other + 1}`);
  }
  return <Modal title={t('Customize dashboard')} onClose={onClose} className="dashboard-customize-modal"><div className="dashboard-customizer-v2">
    <p className="customizer-instructions">{t('Drag to reorder. Use ⇄ to move widgets between the main column and side rail.')}</p>
    <span className="sr-only" aria-live="polite">{announcement}</span>
    {groups.map((column) => { const items = itemsFor(column); if (column === 'hidden' && !items.length) return null; return <section key={column} className={`customizer-column ${dragged ? 'accepts-drop' : ''}`} data-widget-column={column} aria-label={t(names[column])} onDragOver={(event) => { if (dragged && column !== 'hidden') { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; } }} onDrop={(event) => {event.preventDefault(); if (dragged && column !== 'hidden') move(dragged, column);}}>
      <h3>{t(names[column])}<span>— {items.length}</span></h3>
      {!items.length && <p className="customizer-drop-empty">{t('Move a widget here with ⇄ or drag it here.')}</p>}
      {items.map((id) => { const [title, Icon] = metadata[id]; return <div key={id} data-widget-id={id} className={`customizer-widget ${dragged === id ? 'dragging' : ''}`} onDragOver={(event) => {if (dragged && column !== 'hidden') {event.preventDefault();event.stopPropagation();}}} onDrop={(event) => {event.preventDefault();event.stopPropagation();if (dragged && column !== 'hidden') move(dragged, column, id);}}>
        {column !== 'hidden' ? <button className="customizer-grip" onPointerDown={(event) => { if (event.button === 0) pointerDrag.current = {id, x: event.clientX, y: event.clientY, active: false}; }} onDragStart={(event) => {setDragged(id);event.dataTransfer.setData('text/plain', id);event.dataTransfer.effectAllowed = 'move';}} onDragEnd={() => setDragged(null)} onKeyDown={(event) => keyboardMove(event, id, column, items)} aria-label={`${t('Reorder with arrow keys')}: ${t(title)}`} title={t('Drag or use ↑ and ↓')}><GripVertical size={18} /></button> : <span className="customizer-grip" />}
        <Icon className="customizer-widget-icon" size={21} /><div className="customizer-widget-copy"><b>{t(title)}</b><p>{t(descriptions[id])}</p></div>
        {column !== 'hidden' && <button className="icon-button" onClick={() => move(id, column === 'main' ? 'rail' : 'main')} aria-label={`${t(column === 'main' ? 'Move to side rail' : 'Move to main column')}: ${t(title)}`} title={t(column === 'main' ? 'Move to side rail' : 'Move to main column')}><ArrowLeftRight size={18} /></button>}
        <button className="icon-button" disabled={column !== 'hidden' && draft.hidden.length === draft.order.length - 1} onClick={() => {setDraft((current) => ({...current, hidden: column === 'hidden' ? current.hidden.filter((key) => key !== id) : [...current.hidden, id]}));}} aria-label={`${t(column === 'hidden' ? 'Show widget' : 'Hide widget')}: ${t(title)}`} title={t(column === 'hidden' ? 'Show widget' : 'Hide widget')}>{column === 'hidden' ? <Plus size={18} /> : <Minus size={18} />}</button>
      </div>; })}
    </section>; })}
    <footer><button className="button quiet" onClick={() => setDraft(normalizeDashboardPreferences())}>{t('Reset layout')}</button><button className="button quiet" onClick={onClose}>{t('Cancel')}</button><button className="button primary" onClick={onSave}>{t('Save')}</button></footer>
  </div></Modal>;
}
