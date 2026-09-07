'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Image from 'next/image';
import { ChevronRightIcon, FolderOpenIcon, LayoutDashboard, Wrench } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from '@/components/ui/sidebar';
import { useT } from '@/components/locale-provider';
import { StageDot } from '@/components/stage-badge';
import type { StageKey } from '@/lib/types';

export interface SidebarProject {
  id: string;
  name: string;
  nextStep: StageKey | 'rebuild_done';
}

export function AppSidebar({
  projects,
  version,
  projectsRoot,
  ...props
}: React.ComponentProps<typeof Sidebar> & { projects: SidebarProject[]; version?: string; projectsRoot: string }) {
  const t = useT();
  const pathname = usePathname();
  const isProjectsActive = pathname.startsWith('/projects');
  const [open, setOpen] = useState(true);

  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" className="h-16" render={<Link href="/" />}>
              {/* Logo: a soap bubble grows, pops and frees the cube inside (scripts/make-logo.py).
                  The tile bakes its own dark background so it reads the same in both themes;
                  users who prefer reduced motion get the static last frame. 48px in the full
                  sidebar, 32px in the collapsed icon rail. */}
              <div className="flex aspect-square size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-zinc-900 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:rounded-lg">
                <Image src="/brand/unbubble.gif" alt="" width={48} height={48} unoptimized className="size-12 motion-reduce:hidden group-data-[collapsible=icon]:size-8" />
                <Image src="/brand/unbubble.png" alt="" width={48} height={48} unoptimized className="hidden size-12 motion-reduce:block group-data-[collapsible=icon]:size-8" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">{t('app.name')}</span>
                <span className="truncate text-xs text-muted-foreground">{t('app.tagline')}</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton isActive={pathname === '/'} render={<Link href="/" />} tooltip={t('nav.dashboard')}>
                <LayoutDashboard />
                <span>{t('nav.dashboard')}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <Collapsible open={open} onOpenChange={setOpen} render={<SidebarMenuItem />}>
              <SidebarMenuButton isActive={isProjectsActive} tooltip={t('nav.projects')} render={<Link href="/projects" />}>
                <FolderOpenIcon />
                <span>{t('nav.projects')}</span>
                <span className="ml-auto text-[10px] font-medium bg-sidebar-accent text-muted-foreground rounded-full px-1.5 py-0.5 tabular-nums">
                  {projects.length}
                </span>
              </SidebarMenuButton>
              {projects.length > 0 && (
                <>
                  <CollapsibleTrigger render={<SidebarMenuAction className="aria-expanded:rotate-90" />}>
                    <ChevronRightIcon />
                    <span className="sr-only">Toggle</span>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <SidebarMenuSub>
                      {projects.map((p) => {
                        const href = `/projects/${p.id}`;
                        const active = pathname === href || pathname.startsWith(href + '/');
                        return (
                          <SidebarMenuSubItem key={p.id}>
                            <SidebarMenuSubButton
                              isActive={active}
                              className={active ? '!bg-zinc-200/70 !font-medium dark:!bg-zinc-800' : ''}
                              render={<Link href={href} />}
                            >
                              <StageDot step={p.nextStep} />
                              <span className="truncate">{p.name}</span>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        );
                      })}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </>
              )}
            </Collapsible>
            <SidebarMenuItem>
              <SidebarMenuButton isActive={pathname.startsWith('/setup')} render={<Link href="/setup" />} tooltip={t('nav.setup')}>
                <Wrench />
                <span>{t('nav.setup')}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
        <SidebarGroup className="mt-auto group-data-[collapsible=icon]:hidden">
          <SidebarGroupLabel>{t('nav.projectsRoot')}</SidebarGroupLabel>
          <p className="px-2 text-xs text-muted-foreground font-mono break-all">{projectsRoot}</p>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <p className="px-2 py-1 text-[11px] text-muted-foreground group-data-[collapsible=icon]:hidden">
          UnBubble {version ? `v${version}` : ''} · audit → clone → level-up
        </p>
      </SidebarFooter>
    </Sidebar>
  );
}
