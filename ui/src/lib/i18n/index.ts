/**
 * Locale registry.
 *
 * To add a language (say Spanish):
 *   1. copy `locales/en.ts` to `locales/es.ts` and translate the values (keep the keys);
 *   2. import it below and append an entry to `LOCALES`.
 * The language menu, the cookie, `<html lang>`, date formatting and the Accept-Language
 * detection all read this list — nothing else needs to change. Keys a locale leaves out fall
 * back to English.
 */
import { en, type Dictionary, type TKey } from './locales/en';
import { es } from './locales/es';
import { pt } from './locales/pt';

export type { Dictionary, TKey };

export interface LocaleDefinition {
  /** Short, stable code — stored in the cookie and exposed by `useLocale()`. */
  code: string;
  /** Name shown in the language menu, written in its own language. */
  label: string;
  /** BCP-47 tag used for `<html lang>` and `Intl` date formatting. */
  tag: string;
  /** Accept-Language primary subtags that select this locale on a first visit. */
  matches: string[];
  dictionary: Partial<Dictionary>;
}

export const LOCALES: LocaleDefinition[] = [
  { code: 'en', label: 'English', tag: 'en', matches: ['en'], dictionary: en },
  { code: 'pt', label: 'Português (Brasil)', tag: 'pt-BR', matches: ['pt'], dictionary: pt },
  { code: 'es', label: 'Español', tag: 'es', matches: ['es'], dictionary: es },
];

export const DEFAULT_LOCALE = 'en';
export const LOCALE_COOKIE = 'unbubble_locale';

/** A registered locale code (one of `LOCALES[].code`). */
export type Locale = string;

export function isLocale(code: unknown): code is Locale {
  return typeof code === 'string' && LOCALES.some((l) => l.code === code);
}

export function getLocale(code: string | undefined | null): LocaleDefinition {
  return LOCALES.find((l) => l.code === code) ?? LOCALES.find((l) => l.code === DEFAULT_LOCALE) ?? LOCALES[0];
}

/** Fills `{name}` placeholders. */
function interpolate(text: string, vars?: Record<string, string | number>): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

export function translate(locale: Locale, key: TKey, vars?: Record<string, string | number>): string {
  const def = getLocale(locale);
  const text = def.dictionary[key] ?? en[key] ?? key;
  return interpolate(text, vars);
}

/**
 * Picks the locale for a request: the cookie if it names a registered locale, otherwise the
 * first Accept-Language entry that matches a registered locale, otherwise the default.
 */
export function resolveLocale(cookieValue?: string | null, acceptLanguage?: string | null): Locale {
  if (isLocale(cookieValue)) return cookieValue;
  const wanted = (acceptLanguage ?? '')
    .split(',')
    .map((part) => part.split(';')[0].trim().toLowerCase())
    .filter(Boolean);
  for (const tag of wanted) {
    const primary = tag.split('-')[0];
    const hit = LOCALES.find((l) => l.tag.toLowerCase() === tag || l.matches.includes(primary));
    if (hit) return hit.code;
  }
  return DEFAULT_LOCALE;
}
