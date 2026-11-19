import { locale, t, formatCurrencyLocale } from '../i18n';
import { matchesQuery } from '../lib/searchIndex';
import { ChevronLeft, Lock, ShoppingCart } from 'lucide-react';
import { BlueButton, Chip, EmptyState, GlassCard, PageHeader } from '../design/blue/ui';
import '../design/pages/catalog-blue-base.css';
import '../design/pages/store-blue.css';

export function StorePage({ data, query, setPage }) {
  const items = data.storeItems.filter((item) => matchesQuery(item, query, locale()));
  const price = (item) => item.price_label ? t(item.price_label)
    : item.price_amount != null ? formatCurrencyLocale(Number(item.price_amount), item.currency || 'UZS')
    : t("Ask your counselor");
  return <div className="section-stack student-portal nb-bridge nb-store">
    <PageHeader title={t('Naseeb Store')} subtitle={t('Additional education and application services')} />
    <div className="store-grid">{items.map((item) => <GlassCard key={item.id} as="article" tone="solid" headingLevel="h3" title={t(item.title)} className={`nb-store-item${item.is_featured ? ' is-featured' : ''}`}
      footer={<><b>{price(item)}</b><BlueButton variant="ghost" size="sm" onClick={() => setPage('messages')}>{t("Ask your team")}</BlueButton></>}>
      <Chip variant={item.is_featured ? 'gold' : 'default'}>{t(item.category)}</Chip>
      <p>{t(item.description)}</p>
    </GlassCard>)}</div>
    {!items.length && <GlassCard tone="solid"><EmptyState icon={ShoppingCart} title={t('No information available yet.')} /></GlassCard>}
  </div>;
}

// Shown at /store and /roadmap while they are locked for students: a calm "opens soon" page with a way back.
const LOCK_PAGES = {
  store: { title: 'Naseeb Store', subtitle: 'Additional education and application services', text: 'The Naseeb Store opens soon. Rewards for approved missions and services will appear here.' },
  roadmap: { title: 'Roadmap', subtitle: 'Level-linked missions, milestones, and reflections', text: 'The Roadmap opens soon. Your level path and missions will appear here.' },
};
export function StoreComingSoon({ setPage, kind = 'store' }) {
  const copy = LOCK_PAGES[kind] || LOCK_PAGES.store;
  return <div className="section-stack student-portal nb-bridge nb-store">
    <PageHeader title={t(copy.title)} subtitle={t(copy.subtitle)} />
    <GlassCard tone="solid" className="nb-store-lock">
      <span className="nb-store-lock-icon" aria-hidden="true"><Lock size={28} /></span>
      <h2>{t(copy.title)}</h2>
      <Chip variant="gold">{t('Coming soon')}</Chip>
      <p>{t(copy.text)}</p>
      <BlueButton variant="ghost" icon={ChevronLeft} onClick={() => setPage('dashboard')}>{t('Dashboard')}</BlueButton>
    </GlassCard>
  </div>;
}
