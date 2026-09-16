'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react';
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

/**
 * Persistence. localStorage is the user's stored preference (it survives reopening the UI);
 * the cookie mirrors it so the server can render the right language on the first paint,
 * without a flash of the default language. Both are written together by `setLocale`.
 */
export const LOCALE_STORAGE_KEY = 'unbubble.locale';

const listeners = new Set<() => void>();
function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener('storage', cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener('storage', cb);
  };
}
function readStoredLocale(): Locale | null {
  try {
    const v = localStorage.getItem(LOCALE_STORAGE_KEY);
    return isLocale(v) ? v : null;
  } catch {
    return null;
  }
}
function writeCookie(l: Locale) {
  try {
    document.cookie = `${LOCALE_COOKIE}=${l}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
  } catch {
    /* ignore */
  }
}

export function LocaleProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  // Server snapshot is "nothing stored" so hydration matches the SSR output; the client
  // snapshot then applies the stored preference if it differs from what the server chose.
  const stored = useSyncExternalStore(subscribe, readStoredLocale, () => null);
  const locale = stored ?? initialLocale;

  // Keep the cookie and <html lang> aligned with the stored preference (e.g. cookie cleared).
  useEffect(() => {
    if (stored && stored !== initialLocale) writeCookie(stored);
    document.documentElement.lang = getLocale(locale).tag;
  }, [stored, initialLocale, locale]);

  const setLocale = useCallback((l: Locale) => {
    if (!isLocale(l)) return;
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, l);
    } catch {
      /* private mode etc. — the cookie still carries the choice for this session */
    }
    writeCookie(l);
    listeners.forEach((cb) => cb());
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
