'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { getLocale, isLocale, translate, LOCALE_COOKIE, type Locale, type LocaleDefinition, type TKey } from '@/lib/i18n';

type Vars = Record<string, string | number>;

interface LocaleContextValue {
  locale: Locale;
  definition: LocaleDefinition;
  setLocale: (l: Locale) => void;
  t: (key: TKey, vars?: Vars) => string;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: 'en',
  definition: getLocale('en'),
  setLocale: () => {},
  t: (k, vars) => translate('en', k, vars),
});

export function LocaleProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const setLocale = useCallback((l: Locale) => {
    if (!isLocale(l)) return;
    setLocaleState(l);
    try {
      document.cookie = `${LOCALE_COOKIE}=${l}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
      document.documentElement.lang = getLocale(l).tag;
    } catch {
      /* ignore */
    }
  }, []);
  const value = useMemo<LocaleContextValue>(
    () => ({ locale, definition: getLocale(locale), setLocale, t: (k: TKey, vars?: Vars) => translate(locale, k, vars) }),
    [locale, setLocale],
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  return useContext(LocaleContext);
}

export function useT() {
  return useContext(LocaleContext).t;
}

export function formatDate(iso: string | undefined, locale: Locale, withTime = false): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(getLocale(locale).tag, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}
