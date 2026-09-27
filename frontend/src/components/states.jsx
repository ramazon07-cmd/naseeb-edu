import { Component, Suspense } from 'react';
import { AlertTriangle, RefreshCw, WifiOff } from 'lucide-react';
import { t } from '../i18n';
import { boundaryStateFor, retryFailedImports } from '../lib/retryableLazy';

// Suspense for lazily loaded routes, plus a recovery screen when a chunk
// cannot be fetched (offline, or an old tab after a deploy replaced the files).
// It resets when `resetKey` (the page) changes, and Retry re-imports the chunk.
export class ChunkErrorBoundary extends Component {
  constructor(props) {super(props);this.state = { failed: false, resetKey: props.resetKey };this.retry = this.retry.bind(this);}
  static getDerivedStateFromError() {return { failed: true };}
  static getDerivedStateFromProps(props, state) {return boundaryStateFor(props.resetKey, state);}
  retry() {retryFailedImports();this.setState({ failed: false });}
  render() {
    if (!this.state.failed) return this.props.children;
    return <div className="data-state error" role="alert"><AlertTriangle size={20} /><div><b>{t('This part of the app could not be loaded.')}</b><p>{t('Check your connection, then try again.')}</p><div className="data-state-actions"><button type="button" className="button primary small" onClick={this.retry}><RefreshCw size={14} /> {t('Retry')}</button><button type="button" className="button quiet small" onClick={() => window.location.reload()}>{t('Reload page')}</button></div></div></div>;
  }
}

export function LazyBoundary({ fallback, children, resetKey }) {
  return <ChunkErrorBoundary resetKey={resetKey}><Suspense fallback={fallback}>{children}</Suspense></ChunkErrorBoundary>;
}

export function PageSkeleton() {
  return <div className="page-skeleton" role="status" aria-label={t("Loading page data")}>
    <div className="skeleton-stat-grid">{[0, 1, 2, 3].map((item) => <span className="skeleton-block" key={item} />)}</div>
    <div className="skeleton-panel"><span className="skeleton-line title" />{[0, 1, 2, 3].map((item) => <span className="skeleton-line" key={item} />)}</div>
    <span className="sr-only">{t("Loading page data…")}</span>
  </div>;
}

export function ChannelListSkeleton({ count = 4 }) {
  return <div className="channel-skeleton" role="status" aria-label={t("Loading conversations")}>{Array.from({ length: count }, (_, index) => <span key={index}><i /><b /><small /></span>)}</div>;
}

export function MessageListSkeleton() {
  return <div className="message-skeleton" role="status" aria-label={t("Loading messages")}>{[58, 74, 46, 66].map((width, index) => <span className={index % 2 ? "mine" : ''} style={{ '--skeleton-width': `${width}%` }} key={`${width}-${index}`}><i /><b /><small /></span>)}</div>;
}

export function StaffStatsSkeleton() {
  return <div className="staff-stats-skeleton" role="status" aria-label={t("Loading messaging overview")}>{Array.from({ length: 5 }, (_, index) => <span key={index}><i /><b /></span>)}</div>;
}

export function InlineLoadError({ message, onRetry }) {
  return <div className="inline-load-error" role="alert"><WifiOff size={20} /><p>{message}</p><button type="button" className="button quiet small" onClick={onRetry}><RefreshCw size={14} /> {t("Retry")}</button></div>;
}
