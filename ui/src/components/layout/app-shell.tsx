'use client';

import { useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import { Languages, MoonIcon, RefreshCw, SunIcon } from 'lucide-react';
import { AppSidebar, type SidebarProject } from '@/components/layout/app-sidebar';
import { HeaderBreadcrumb, HeaderBreadcrumbProvider } from '@/components/layout/header-breadcrumb';
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';
import { Button } from '@/components/ui/button';
import { TooltipProvider, Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useLocale } from '@/components/locale-provider';

export function AppShell({
  children,
  projects,
  version,
  projectsRoot,
}: {
  children: React.ReactNode;
  projects: SidebarProject[];
  version?: string;
  projectsRoot: string;
}) {
  const router = useRouter();
  const { locale, setLocale, t } = useLocale();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <TooltipProvider>
      <HeaderBreadcrumbProvider>
        <SidebarProvider>
          <AppSidebar projects={projects} version={version} projectsRoot={projectsRoot} />
          <SidebarInset>
            <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
              <SidebarTrigger className="-ml-1" />
              <Separator orientation="vertical" className="mr-2 h-4" />
              <HeaderBreadcrumb />
              <div className="ml-auto flex items-center gap-1">
                <Tooltip>
                  <TooltipTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t('nav.rescan')} />} onClick={() => router.refresh()}>
                    <RefreshCw className="size-4" />
                  </TooltipTrigger>
                  <TooltipContent>{t('nav.rescan')}</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger render={<Button variant="ghost" size="sm" aria-label={t('nav.language')} />} onClick={() => setLocale(locale === 'pt' ? 'en' : 'pt')}>
                    <Languages className="size-4" />
                    <span className="text-xs font-medium uppercase">{locale}</span>
                  </TooltipTrigger>
                  <TooltipContent>{t('nav.language')}</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={<Button variant="ghost" size="icon-sm" aria-label={t('nav.theme')} />}
                    onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
                  >
                    {/* Both icons are rendered; CSS picks one, so no mount-state is needed. */}
                    <SunIcon className="size-4 hidden dark:block" />
                    <MoonIcon className="size-4 dark:hidden" />
                  </TooltipTrigger>
                  <TooltipContent>{t('nav.theme')}</TooltipContent>
                </Tooltip>
              </div>
            </header>
            <div className="flex-1 overflow-y-auto p-6 md:p-8">{children}</div>
          </SidebarInset>
        </SidebarProvider>
      </HeaderBreadcrumbProvider>
    </TooltipProvider>
  );
}
