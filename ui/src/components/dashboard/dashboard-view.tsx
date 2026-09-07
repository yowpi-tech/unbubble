'use client';

import { useSyncExternalStore } from 'react';
import Link from 'next/link';
import { ArrowRight, CheckCircle2, FolderOpen, Rocket, SearchCheck, Sparkles, Wrench, X } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ProgressBar, StatusBadge, stageHref } from '@/components/stage-badge';
import { formatDate, useLocale } from '@/components/locale-provider';
import type { HostInstall, ProjectSummary, StageKey } from '@/lib/types';

const STAGES: StageKey[] = ['audit', 'clone', 'levelup_docs', 'levelup_impl'];
const ONBOARDING_KEY = 'unbubble.onboarding.dismissed';
const listeners = new Set<() => void>();
function subscribeDismissed(cb: () => void) {
  listeners.add(cb);
  window.addEventListener('storage', cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener('storage', cb);
  };
}
function readDismissed(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_KEY) === '1';
  } catch {
    return false;
  }
}

export function DashboardView({ projects, hosts }: { projects: ProjectSummary[]; hosts: HostInstall[] }) {
  const { t, locale } = useLocale();
  // Per-viewer convenience flag; hidden during SSR, resolved from localStorage on the client.
  const dismissed = useSyncExternalStore(subscribeDismissed, readDismissed, () => true);
  const showOnboarding = !dismissed;

  function dismiss() {
    try {
      localStorage.setItem(ONBOARDING_KEY, '1');
    } catch {
      /* ignore */
    }
    listeners.forEach((cb) => cb());
  }

  const stats = [
    { label: t('dash.projects'), value: projects.length, icon: FolderOpen },
    { label: t('dash.audits'), value: projects.filter((p) => p.stages.audit.status === 'done').length, icon: SearchCheck },
    { label: t('dash.clones'), value: projects.filter((p) => p.stages.clone.status === 'done').length, icon: CheckCircle2 },
    { label: t('dash.levelups'), value: projects.filter((p) => p.stages.levelup_docs.status === 'done').length, icon: Rocket },
  ];

  const installed = hosts.filter((h) => h.status === 'installed');
  const present = hosts.filter((h) => h.detectedOnMachine);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{t('dash.title')}</h1>
        <p className="text-zinc-500 mt-1">{t('dash.subtitle')}</p>
      </div>

      {showOnboarding && (
        <Card className="border-zinc-900/10 dark:border-zinc-100/10 bg-gradient-to-r from-zinc-50 to-white dark:from-zinc-900 dark:to-zinc-950">
          <CardContent className="pt-6 flex items-start gap-4">
            <div className="rounded-lg p-3 bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 shrink-0">
              <Sparkles className="size-6" />
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="font-semibold">{t('dash.onboardingTitle')}</h2>
              <p className="text-sm text-zinc-500 mt-1">{t('dash.onboardingBody')}</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" nativeButton={false} render={<Link href="/setup" />}>
                  {t('dash.onboardingCta')}
                  <ArrowRight className="size-3.5" />
                </Button>
                <Button size="sm" variant="ghost" onClick={dismiss}>
                  <X className="size-3.5" />
                  {t('dash.onboardingDismiss')}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <s.icon className="h-5 w-5 text-zinc-400" />
                <div>
                  <p className="text-2xl font-bold tabular-nums">{s.value}</p>
                  <p className="text-sm text-zinc-500">{s.label}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div>
          <h2 className="text-lg font-semibold mb-4">{t('dash.pipeline')}</h2>
          {projects.length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-sm text-zinc-500">{t('dash.noProjects')}</CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="pt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-zinc-500">
                      <th className="py-2 pr-3 font-medium">{t('dash.projects')}</th>
                      {STAGES.map((k) => (
                        <th key={k} className="py-2 px-2 font-medium whitespace-nowrap">
                          {t(`stage.${k}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {projects.map((p) => (
                      <tr key={p.id} className="border-t border-zinc-100 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-900/40">
                        <td className="py-3 pr-3 min-w-44">
                          <Link href={`/projects/${p.id}`} className="font-medium hover:underline">
                            {p.name}
                          </Link>
                          <p className="text-[11px] text-zinc-400">{formatDate(p.updatedAt, locale)}</p>
                        </td>
                        {STAGES.map((k) => (
                          <td key={k} className="p-0 min-w-36 align-top">
                            {/* The whole cell is a link to that stage's section of the project. */}
                            <Link
                              href={stageHref(p.id, k)}
                              title={`${t(`stage.${k}`)} · ${p.name}`}
                              className="block h-full rounded-md px-2 py-3 transition-colors hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:hover:bg-zinc-800/70"
                            >
                              <StatusBadge status={p.stages[k].status} />
                              <ProgressBar value={p.stages[k].progress} stage={k} className="mt-1.5 w-28" />
                              <p className="text-[11px] text-zinc-400 mt-1 whitespace-nowrap">{p.stages[k].detail}</p>
                            </Link>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4">{t('dash.installCard')}</h2>
          <Card>
            <CardContent className="pt-6 space-y-3">
              {present.length === 0 && <p className="text-sm text-zinc-500">{t('dash.installAbsent')}</p>}
              {present.map((h) => (
                <div key={h.host} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-700 dark:text-zinc-300">{h.label}</span>
                  <span
                    className={
                      h.status === 'installed'
                        ? 'text-xs font-medium text-green-700 dark:text-green-400'
                        : h.status === 'partial'
                          ? 'text-xs font-medium text-amber-700 dark:text-amber-400'
                          : 'text-xs text-zinc-400'
                    }
                  >
                    {h.status === 'installed' ? t('dash.installOk') : h.status === 'partial' ? t('setup.status.partial') : t('dash.installMissing')}
                  </span>
                </div>
              ))}
              <div className="pt-2 border-t">
                <Link href="/setup" className="text-sm inline-flex items-center gap-1 text-zinc-600 dark:text-zinc-300 hover:underline">
                  <Wrench className="size-3.5" />
                  {t('dash.seeSetup')}
                  <span className="text-xs text-zinc-400">
                    ({installed.length}/{present.length})
                  </span>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
