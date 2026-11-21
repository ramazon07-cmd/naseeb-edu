import { Component, Fragment, Suspense, lazy } from 'react';
import { t } from '../i18n';

// The Subject rankings view is its own chunk: nothing of it (code, styles or data) loads until a student opens
// it. This loader stays in the College Search chunk and keeps its own small recovery: when the chunk cannot be
// fetched (offline, or an old tab after a deploy) Retry imports it again.
const load = () => import('./SubjectRankings').then((module) => ({ default: module.SubjectRankings }));
let View = lazy(load);

class LoadBoundary extends Component {
  state = { failed: false, attempt: 0 };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  retry = () => {
    View = lazy(load);
    // The children element already holds the rejected lazy type: a new key remounts it so it reads the new one.
    this.setState((state) => ({ failed: false, attempt: state.attempt + 1 }));
  };

  render() {
    if (!this.state.failed) return <Fragment key={this.state.attempt}>{this.props.children}</Fragment>;
    return <div className="college-research-state error" role="alert"><div><b>{t('This part of the app could not be loaded.')}</b><p>{t('Check your connection, then try again.')}</p></div><button type="button" className="button quiet small" onClick={this.retry}>{t('Retry')}</button></div>;
  }
}

// Reads the current lazy type on every render, so a Retry's new View is the one that renders.
function CurrentView(props) {
  return <View {...props} />;
}

export function SubjectRankingsView(props) {
  return <LoadBoundary><Suspense fallback={<p className="uni-loading" role="status">{t('Loading universities…')}</p>}><CurrentView {...props} /></Suspense></LoadBoundary>;
}
