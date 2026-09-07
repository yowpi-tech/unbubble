'use client';

import { useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle2, CircleDashed, CircleOff, FolderOpen, GitBranch, RefreshCw } from 'lucide-react';
import { Breadcrumbs } from '@/components/breadcrumbs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CommandBlock } from '@/components/copy-button';
import { useLocale } from '@/components/locale-provider';
import { cn } from '@/lib/utils';
import type { HostInstall, HostKey, SetupInfo } from '@/lib/types';
import type { TKey } from '@/lib/i18n';

const HOST_SKILL_ROOT: Record<HostKey, string> = {
  claude: '~/.claude/skills',
  codex: '~/.codex/skills',
  agents: '~/.agents/skills',
  cursor: '~/.cursor/skills',
  gemini: '~/.gemini/skills',
  copilot: '~/.copilot/skills',
  opencode: '~/.config/opencode/skills',
  windsurf: '~/.codeium/windsurf/skills',
};

function installCommand(host: HostKey, repo: string): string {
  const q = `"${repo}"`;
  if (host === 'claude') return `mkdir -p ~/.claude/skills && ln -sfn ${q} ~/.claude/skills/unbubble`;
  const root = HOST_SKILL_ROOT[host];
  return `mkdir -p ${root} && for s in audit clone level-up; do ln -sfn ${q}/skills/$s ${root}/unbubble-$s; done`;
}

function StatusIcon({ status }: { status: HostInstall['status'] }) {
  if (status === 'installed') return <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />;
  if (status === 'partial') return <CircleDashed className="size-4 text-amber-600 dark:text-amber-400" />;
  if (status === 'host_absent') return <CircleOff className="size-4 text-zinc-300 dark:text-zinc-600" />;
  return <AlertTriangle className="size-4 text-zinc-400" />;
}

export function SetupView({ info }: { info: SetupInfo }) {
  const { t } = useLocale();
  const router = useRouter();
  const present = info.hosts.filter((h) => h.detectedOnMachine);
  const absent = info.hosts.filter((h) => !h.detectedOnMachine);

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: t('nav.setup') }]} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{t('setup.title')}</h1>
          <p className="text-zinc-500 mt-1">{t('setup.subtitle')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => router.refresh()}>
          <RefreshCw className="size-3.5" />
          {t('setup.rescan')}
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <GitBranch className="size-5 text-zinc-400 mt-0.5" />
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {t('setup.repo')}{' '}
                  {info.repoVersion && (
                    <Badge variant="outline" className="ml-1">
                      {t('setup.version')} {info.repoVersion}
                    </Badge>
                  )}
                </p>
                <p className="font-mono text-sm break-all">{info.repoDir}</p>
                {!info.repoIsValid && <p className="text-xs text-red-600 mt-1">{t('setup.repoInvalid')}</p>}
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <FolderOpen className="size-5 text-zinc-400 mt-0.5" />
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {t('setup.projectsDir')} <Badge variant="outline" className="ml-1">{info.projectCount}</Badge>
                </p>
                <p className="font-mono text-sm break-all">{info.projectsDir}</p>
                {!info.projectsDirExists && <p className="text-xs text-zinc-500 mt-1">{t('setup.projectsDirMissing')}</p>}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold">{t('setup.hosts')}</h2>
          <p className="text-sm text-zinc-500">{t('setup.hostsHint')}</p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {present.map((h) => (
            <HostCard key={h.host} host={h} repo={info.repoDir} />
          ))}
        </div>
        {absent.length > 0 && (
          <details className="rounded-lg border p-3">
            <summary className="text-sm cursor-pointer text-zinc-600 dark:text-zinc-300">
              {t('setup.status.host_absent')} · {absent.map((h) => h.label).join(', ')}
            </summary>
            <div className="grid gap-4 lg:grid-cols-2 mt-3">
              {absent.map((h) => (
                <HostCard key={h.host} host={h} repo={info.repoDir} />
              ))}
            </div>
          </details>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">{t('setup.onboarding')}</h2>
        <ol className="space-y-4">
          {(
            [
              { n: 1, title: 'setup.step1', body: 'setup.step1.body' },
              { n: 2, title: 'setup.step2', body: 'setup.step2.body' },
              { n: 3, title: 'setup.step3', body: 'setup.step3.body', prompt: 'setup.prompt.audit' },
              { n: 4, title: 'setup.step4', body: 'setup.step4.body' },
            ] as { n: number; title: TKey; body: TKey; prompt?: TKey }[]
          ).map((s) => (
            <li key={s.n} className="flex gap-4">
              <div className="size-8 shrink-0 rounded-full bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 flex items-center justify-center text-sm font-semibold">
                {s.n}
              </div>
              <div className="flex-1 min-w-0 space-y-2">
                <p className="font-medium">{t(s.title)}</p>
                <p className="text-sm text-zinc-500">{t(s.body)}</p>
                {s.prompt && <CommandBlock text={t(s.prompt)} />}
                {s.n === 4 && (
                  <div className="grid gap-2 md:grid-cols-2">
                    <CommandBlock text={t('setup.prompt.clone')} />
                    <CommandBlock text={t('setup.prompt.levelup')} />
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function HostCard({ host, repo }: { host: HostInstall; repo: string }) {
  const { t } = useLocale();
  const note: TKey = host.host === 'claude' ? 'setup.claude.note' : host.host === 'codex' ? 'setup.codex.note' : host.host === 'agents' ? 'setup.agents.note' : 'setup.generic.note';
  return (
    <Card className={cn(host.status === 'host_absent' && 'opacity-70')}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base flex items-center gap-2">
            <StatusIcon status={host.status} />
            {host.label}
            <span className="text-xs font-normal text-zinc-400">{host.vendor}</span>
          </CardTitle>
          <Badge variant={host.status === 'installed' ? 'default' : 'secondary'}>{t(`setup.status.${host.status}` as TKey)}</Badge>
        </div>
        <p className="text-xs text-zinc-500">
          {t('setup.lookedAt')}: <span className="font-mono">{host.roots.join(', ')}</span>
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {host.locations.length > 0 && (
          <ul className="space-y-2">
            {host.locations.map((loc) => (
              <li key={loc.path} className="rounded-md border p-2 text-xs space-y-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline">{t(`setup.kind.${loc.kind}` as TKey)}</Badge>
                  {loc.version && <Badge variant="outline">v{loc.version}</Badge>}
                  <span className="font-mono break-all">{loc.path}</span>
                </div>
                {loc.target && <p className="font-mono text-zinc-500 break-all">→ {loc.target}</p>}
                <p className="flex flex-wrap gap-1 items-center">
                  <span className="text-zinc-500">{t('setup.skills')}:</span>
                  {(['audit', 'clone', 'level-up'] as const).map((s) => {
                    const found = loc.skills.find((x) => x.skill === s);
                    return (
                      <span
                        key={s}
                        className={cn(
                          'rounded-full px-1.5 py-0.5 font-mono',
                          found ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' : 'bg-zinc-100 text-zinc-500 line-through dark:bg-zinc-800 dark:text-zinc-500',
                        )}
                      >
                        {s}
                      </span>
                    );
                  })}
                  <span className={cn('ml-auto', loc.inSync === true ? 'text-green-700 dark:text-green-400' : loc.inSync === false ? 'text-amber-700 dark:text-amber-400' : 'text-zinc-400')}>
                    {loc.inSync === true ? t('setup.inSync') : loc.inSync === false ? t('setup.outOfSync') : t('setup.unknownSync')}
                  </span>
                </p>
              </li>
            ))}
          </ul>
        )}
        <div>
          <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300 mb-1">{t('setup.howTo')}</p>
          <CommandBlock text={installCommand(host.host, repo)} />
          <p className="text-xs text-zinc-500 mt-1">{t(note)}</p>
          {host.host === 'claude' && (
            <div className="mt-2">
              <p className="text-xs text-zinc-500 mb-1">
                {t('setup.alt')}: {t('setup.altClaude')}
              </p>
              <CommandBlock text={`claude --plugin-dir "${repo}"`} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
