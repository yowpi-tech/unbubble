'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BookOpen, LayoutGrid, Rocket, SearchCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useT } from '@/components/locale-provider';

export function ProjectNav({ id }: { id: string }) {
  const t = useT();
  const pathname = usePathname();
  const base = `/projects/${id}`;
  const tabs = [
    { href: base, label: t('project.overview'), icon: LayoutGrid, exact: true },
    { href: `${base}/audit`, label: t('project.audit'), icon: SearchCheck },
    { href: `${base}/docs`, label: t('project.docs'), icon: BookOpen },
    { href: `${base}/levelup`, label: t('project.levelup'), icon: Rocket },
  ];
  return (
    <nav className="flex gap-1 border-b overflow-x-auto" aria-label="project sections">
      {tabs.map((tab) => {
        const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 -mb-px transition-colors whitespace-nowrap',
              active
                ? 'border-zinc-900 dark:border-zinc-100 text-zinc-900 dark:text-zinc-100 font-medium'
                : 'border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200',
            )}
          >
            <tab.icon className="size-4" />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
