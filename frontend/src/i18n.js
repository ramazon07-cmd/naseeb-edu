/* global __I18N_SPLIT__ -- defined by Vite for browser builds; absent in Node */

const LANGUAGE_KEY = "naseeb-edu-language-v1";

export const LANGUAGE_OPTIONS = [
  { value: "uz", label: "O‘zbekcha", short: "UZ" },
  { value: "ru", label: "Русский", short: "RU" },
  { value: "en", label: "English", short: "EN" },
];

const LOCALES = { uz: "uz-UZ", ru: "ru-RU", en: "en-GB" };

// Language dictionaries are generated at build time (see i18nDictionaries in
// vite.config.js) and loaded per language by loadLanguage(); English is the key.
// In Node (tests, scripts) there is no bundler, so every dictionary is built
// from the source tables instead.
export const TRANSLATIONS = { uz: {}, ru: {}, en: {} };

if (typeof __I18N_SPLIT__ === "undefined") {
  const all = await import("./translations/all.js");
  for (const language of Object.keys(all.TRANSLATIONS)) Object.assign(TRANSLATIONS[language], all.TRANSLATIONS[language]);
}

const LOADERS = {
  uz: () => import("virtual:i18n/uz"),
  ru: () => import("virtual:i18n/ru"),
  en: () => import("virtual:i18n/en"),
};
const loading = {};

// Fetches the dictionary for `language` (a retry on failure) so t() can stay
// synchronous. Resolves true when it is ready, false when it could not be
// loaded; the caller then keeps showing English, which is the key text.
export function loadLanguage(language) {
  if (!isSupported(language)) return Promise.resolve(true);
  const dictionary = TRANSLATIONS[language];
  if (typeof __I18N_SPLIT__ === "undefined" || Object.keys(dictionary).length) return Promise.resolve(true);
  loading[language] ??= (async () => {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        Object.assign(dictionary, (await LOADERS[language]()).default);
        return true;
      } catch {
        if (attempt === 0) await new Promise((resolve) => setTimeout(resolve, 400));
      }
    }
    delete loading[language];
    return false;
  })();
  return loading[language];
}

let activeLanguage = "en";

const isSupported = (value) => LANGUAGE_OPTIONS.some((option) => option.value === value);

// ?lang=uz|ru|en makes each language addressable (hreflang alternates).
function urlLanguage() {
  try {
    const value = new URLSearchParams(window.location.search).get("lang");
    return isSupported(value) ? value : null;
  } catch {
    return null;
  }
}

const DOCUMENT_META = {
  uz: {
    title: "Naseeb Edu - Universitetga qabul uchun AI platforma",
    description: "Naseeb Edu — sun’iy intellektga asoslangan SaaS platforma: psixometrik profil, universitet va grantlar reytingi, insho tahlili va shaxsiy qabul traektoriyasi.",
  },
  ru: {
    title: "Naseeb Edu — AI-платформа для поступления в университет",
    description: "Naseeb Edu — SaaS-платформа на основе искусственного интеллекта: психометрический профиль, рейтинг университетов и грантов, анализ эссе и персональная дорожная карта поступления.",
  },
  en: {
    title: "Naseeb Edu - AI platform for university admission",
    description: "Naseeb Edu is an AI-powered SaaS platform: psychometric profiling, university and scholarship matching, essay analysis and a personalized admission roadmap.",
  },
};

function applyDocumentLanguage(language) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = language;
  const meta = DOCUMENT_META[language] || DOCUMENT_META.en;
  document.title = meta.title;
  document.querySelector('meta[name="description"]')?.setAttribute("content", meta.description);
  if (urlLanguage()) {
    document.querySelector('link[rel="canonical"]')?.setAttribute("href", `https://naseebedu.com/?lang=${language}`);
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("lang", language);
      window.history.replaceState(window.history.state, "", url);
    } catch {
      /* URL stays as it is. */
    }
  }
}

// The public (landing/sign-in) tab title; workspace pages set their own.
export function siteTitle() {
  return (DOCUMENT_META[activeLanguage] || DOCUMENT_META.en).title;
}

export function getLanguage() {
  if (typeof window === "undefined") return activeLanguage;
  const fromUrl = urlLanguage();
  if (fromUrl) return fromUrl;
  try {
    const stored = window.localStorage.getItem(LANGUAGE_KEY);
    if (LANGUAGE_OPTIONS.some((option) => option.value === stored))
      return stored;
  } catch {
    /* Use browser preference. */
  }
  const browserLanguage = window.navigator.language?.split("-")[0];
  return LANGUAGE_OPTIONS.some((option) => option.value === browserLanguage)
    ? browserLanguage
    : "en";
}

export function setLanguage(language) {
  activeLanguage = isSupported(language) ? language : "en";
  applyDocumentLanguage(activeLanguage);
  try {
    window.localStorage.setItem(LANGUAGE_KEY, activeLanguage);
  } catch {
    /* Keep session language. */
  }
  return activeLanguage;
}

activeLanguage = getLanguage();
applyDocumentLanguage(activeLanguage);

export function t(key, variables = {}) {
  const source = String(key ?? "");
  const translated = TRANSLATIONS[activeLanguage]?.[source] || source;
  return Object.entries(variables).reduce((value, [name, replacement]) => {
    const localized =
      typeof replacement === "number"
        ? formatNumberLocale(replacement)
        : String(replacement);
    return value.replaceAll(`{${name}}`, localized);
  }, translated);
}

export function tx(strings, ...values) {
  const variables = Object.fromEntries(
    values.map((value, index) => [String(index), value]),
  );
  const key = strings.reduce(
    (result, part, index) =>
      `${result}${part}${index < values.length ? `{${index}}` : ""}`,
    "",
  );
  return t(key, variables);
}

// Plural-aware t(): a translation may hold "one|few|many" forms (Russian),
// picked for `count` by the active language's plural rules.
export function tp(key, count, variables = {}) {
  const text = t(key, variables);
  if (!text.includes("|")) return text;
  const forms = text.split("|");
  const rule = new Intl.PluralRules(locale()).select(Number(count) || 0);
  const index = { one: 0, few: 1, many: 2 }[rule] ?? forms.length - 1;
  return forms[Math.min(index, forms.length - 1)];
}

export const locale = () => LOCALES[activeLanguage] || LOCALES.en;
const UZ_MONTHS = [
  "yanvar", "fevral", "mart", "aprel", "may", "iyun",
  "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
];

// Sunday first, as Date#getDay() counts.
const UZ_WEEKDAYS = {
  long: ["yakshanba", "dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba"],
  short: ["Yak", "Dush", "Sesh", "Chor", "Pay", "Jum", "Shan"],
  narrow: ["Y", "D", "S", "C", "P", "J", "S"],
};

// Some Chromium builds ship without Uzbek month names (they fall back to "M09")
// or weekday names (English "Mon"). Uzbek is the default language here, so
// compose the date ourselves when that happens.
const formatUzbekDate = (date, options) => {
  const pad = (part) => String(part).padStart(2, "0");
  const pieces = [];
  if (options.day && options.month) pieces.push(`${date.getDate()}-${UZ_MONTHS[date.getMonth()]}`);
  else if (options.month) pieces.push(UZ_MONTHS[date.getMonth()]);
  else if (options.day) pieces.push(String(date.getDate()));
  if (options.year) pieces.push(String(date.getFullYear()));
  const weekday = options.weekday ? (UZ_WEEKDAYS[options.weekday] || UZ_WEEKDAYS.long)[date.getDay()] : "";
  const stamp = [weekday, pieces.join(" ")].filter(Boolean).join(", ");
  if (!options.hour && !options.minute) return stamp;
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  return stamp ? `${stamp}, ${time}` : time;
};

// A calendar date ("2026-09-25", e.g. a due date) is a day, not an instant:
// new Date() would read it as UTC midnight and show the previous day west of UTC.
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
export const parseDateValue = (value) => {
  const match = typeof value === "string" && DATE_ONLY.exec(value);
  return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : new Date(value);
};

export const formatDateLocale = (
  value,
  options = { day: "2-digit", month: "short", year: "numeric" },
) => {
  if (!value) return "—";
  const date = parseDateValue(value);
  const formatted = new Intl.DateTimeFormat(locale(), options).format(date);
  const missingWeekday = activeLanguage === "uz" && options.weekday
    && !formatted.includes((UZ_WEEKDAYS[options.weekday] || UZ_WEEKDAYS.long)[date.getDay()]);
  return missingWeekday || /\bM\d{2}\b/.test(formatted) ? formatUzbekDate(date, options) : formatted;
};
export const formatNumberLocale = (value, options = {}) =>
  new Intl.NumberFormat(locale(), options).format(Number(value) || 0);
export const formatPercentLocale = (value, options = {}) =>
  new Intl.NumberFormat(locale(), {
    style: "percent",
    maximumFractionDigits: 0,
    ...options,
  }).format((Number(value) || 0) / 100);
export const formatCurrencyLocale = (value, currency = "USD") =>
  value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat(locale(), {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(Number(value));

// "1 h 5 min" in the active language (keys "h"/"min" are translated).
export const formatDurationLocale = (seconds = 0) => {
  const totalMinutes = Math.round(Number(seconds) / 60);
  if (!(totalMinutes >= 1)) return `< ${formatNumberLocale(1)} ${t("min")}`;
  if (totalMinutes < 60) return `${formatNumberLocale(totalMinutes)} ${t("min")}`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${formatNumberLocale(hours)} ${t("h")}${minutes ? ` ${formatNumberLocale(minutes)} ${t("min")}` : ""}`;
};

// Hours and minutes only, e.g. for a live counter: "0 min", "2 h 5 min".
export const formatClockDurationLocale = (seconds = 0) => {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return hours ? `${formatNumberLocale(hours)} ${t("h")} ${formatNumberLocale(minutes)} ${t("min")}` : `${formatNumberLocale(minutes)} ${t("min")}`;
};
