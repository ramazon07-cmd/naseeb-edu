import { locale, t, formatCurrencyLocale } from '../i18n';
import { Empty } from '../components/ui';
import { matchesQuery } from '../lib/searchIndex';

export function StorePage({ data, query, setPage }) {
  const items = data.storeItems.filter((item) => matchesQuery(item, query, locale()));
  const price = (item) => item.price_label ? t(item.price_label)
    : item.price_amount != null ? formatCurrencyLocale(Number(item.price_amount), item.currency || 'UZS')
    : t("Ask your counselor");
  return <div className="section-stack student-portal">
    <div className="store-grid">{items.map((item) => <article key={item.id} className={item.is_featured ? "featured" : ''}><span>{t(item.category)}</span><h3>{t(item.title)}</h3><p>{t(item.description)}</p><footer><b>{price(item)}</b><button className="button quiet small" onClick={() => setPage('messages')}>{t("Ask your team")}</button></footer></article>)}{!items.length && <Empty />}</div>
  </div>;
}
