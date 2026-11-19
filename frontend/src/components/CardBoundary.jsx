import { Component } from 'react';
import { AlertCircle } from 'lucide-react';
import { t } from '../i18n';

// Keeps one failing card from replacing the whole page: it shows a small notice
// with a Retry button that mounts the card again. No request is made.
export class CardBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error(error);
  }

  retry = () => this.setState({ failed: false });

  render() {
    if (!this.state.failed) return this.props.children;
    return <div className="nb-card-err" role="alert">
      <AlertCircle size={18} aria-hidden="true" />
      <b>{t('This card did not load.')}</b>
      <button type="button" className="nb-btn nb-btn-ghost nb-btn-sm" onClick={this.retry}>{t('Retry')}</button>
    </div>;
  }
}
