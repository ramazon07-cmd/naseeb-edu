import { Component, Suspense, lazy } from 'react';
import { t } from '../i18n';

// The Subject rankings view is its own chunk: nothing of it (code, styles or data) loads until a student opens
// it. This loader stays in the College Search chunk and keeps its own small recovery: when the chunk cannot be
// fetched (offline, or an old tab after a deploy) Retry imports it again.
const load = () => import('./SubjectRankings').then((module) => ({ default: module.SubjectRankings }));
let View = lazy(load);

class LoadBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  retry = () => {
    View = lazy(load);
    this.setState({ failed: false });
  };

  render() {
    if (!this.state.failed) return this.props.children;
    return <div className="college-research-state error" role="alert"><div><b>{t('This part of the app could not be loaded.')}</b><p>{t('Check your connection, then try again.')}</p></div><button type="button" className="button quiet small" onClick={this.retry}>{t('Retry')}</button></div>;
  }
}

export function SubjectRankingsView(props) {
  return <LoadBoundary><Suspense fallback={<p className="uni-loading" role="status">{t('Loading universities…')}</p>}><View {...props} /></Suspense></LoadBoundary>;
}
