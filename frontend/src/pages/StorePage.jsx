import { locale, t, formatCurrencyLocale } from '../i18n';
import { matchesQuery } from '../lib/searchIndex';
import { ShoppingCart } from 'lucide-react';
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
    {!items.length && <EmptyState icon={ShoppingCart} title={t('No information available yet.')} />}
  </div>;
}
