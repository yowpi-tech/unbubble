import type { Metadata } from 'next';
import { cookies, headers } from 'next/headers';
import { ThemeProvider } from 'next-themes';
import { LocaleProvider } from '@/components/locale-provider';
import { AppShell } from '@/components/layout/app-shell';
import { listProjects } from '@/lib/scan/project';
import { projectsDir, prettyPath, repoDir, repoVersion } from '@/lib/paths';
import { getLocale, resolveLocale, LOCALE_COOKIE } from '@/lib/i18n';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'UnBubble', template: '%s · UnBubble' },
  description: 'Local console for the UnBubble pipeline: audit, clone docs and level-up progress per project.',
};

export const dynamic = 'force-dynamic';

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Cookie set by the language menu wins; a first visit follows Accept-Language (see lib/i18n).
  const locale = resolveLocale((await cookies()).get(LOCALE_COOKIE)?.value, (await headers()).get('accept-language'));
  const projects = listProjects().map((p) => ({ id: p.id, name: p.name, nextStep: p.nextStep }));
  const version = repoVersion(repoDir());

  return (
    <html lang={getLocale(locale).tag} className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col">
        {/* next-themes persists the choice in localStorage under storageKey and restores it before paint */}
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange storageKey="unbubble.theme">
          <LocaleProvider initialLocale={locale}>
            <AppShell projects={projects} version={version} projectsRoot={prettyPath(projectsDir())}>
              {children}
            </AppShell>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
