import type { Metadata } from 'next';
import { cookies, headers } from 'next/headers';
import { ThemeProvider } from 'next-themes';
import { LocaleProvider, LOCALE_COOKIE } from '@/components/locale-provider';
import { AppShell } from '@/components/layout/app-shell';
import { listProjects } from '@/lib/scan/project';
import { projectsDir, prettyPath, repoDir, repoVersion } from '@/lib/paths';
import type { Locale } from '@/lib/i18n';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'UnBubble', template: '%s · UnBubble' },
  description: 'Local console for the UnBubble pipeline: audit, clone docs and level-up progress per project.',
};

export const dynamic = 'force-dynamic';

async function resolveLocale(): Promise<Locale> {
  const c = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (c === 'pt' || c === 'en') return c;
  const accept = (await headers()).get('accept-language') ?? '';
  return /^pt|,pt/i.test(accept) ? 'pt' : 'en';
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await resolveLocale();
  const projects = listProjects().map((p) => ({ id: p.id, name: p.name, nextStep: p.nextStep }));
  const version = repoVersion(repoDir());

  return (
    <html lang={locale === 'pt' ? 'pt-BR' : 'en'} className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
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
