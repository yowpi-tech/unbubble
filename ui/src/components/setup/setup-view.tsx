'use client';

import { useRouter } from 'next/navigation';
import { AlertTriangle, CheckCircle2, CircleDashed, CircleOff, FolderOpen, GitBranch, PlugZap, RefreshCw, XCircle } from 'lucide-react';
import { Breadcrumbs } from '@/components/breadcrumbs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CommandBlock } from '@/components/copy-button';
import { formatDate, useLocale } from '@/components/locale-provider';
import { cn } from '@/lib/utils';
import type { ConnectedModeInfo, HostInstall, HostKey, SetupInfo } from '@/lib/types';
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

/** A path for a shell command: `~` is not expanded inside quotes, `$HOME` is. */
function shellPath(p: string): string {
  return `"${p.replace(/^~(?=\/|$)/, '$HOME')}"`;
}

function installCommand(host: HostKey, repo: string): string {
  const q = shellPath(repo);
  if (host === 'claude') return `mkdir -p ~/.claude/skills && ln -sfn ${q} ~/.claude/skills/unbubble`;
  const root = HOST_SKILL_ROOT[host];
  return `mkdir -p ${root} && for s in audit clone level-up; do ln -sfn ${q}/skills/$s ${root}/unbubble-$s; done`;
}

/** The optional unbubble:connect skill on hosts that link one folder per skill. */
function connectSkillCommand(host: HostKey, repo: string): string | null {
  if (host === 'claude') return null; // the plugin folder already carries every skill
  return `ln -sfn ${shellPath(repo)}/skills/connect ${HOST_SKILL_ROOT[host]}/unbubble-connect`;
}

function StatusIcon({ status }: { status: HostInstall['status'] }) {
  if (status === 'installed') return <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />;
  if (status === 'partial') return <CircleDashed className="size-4 text-amber-600 dark:text-amber-400" />;
  if (status === 'host_absent') return <CircleOff className="size-4 text-zinc-300 dark:text-zinc-600" />;
  return <AlertTriangle className="size-4 text-zinc-400" />;
}

export function SetupView({ info, connected }: { info: SetupInfo; connected: ConnectedModeInfo }) {
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

      <ConnectedCard connected={connected} repo={info.repoDir} />

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
  const optional = connectSkillCommand(host.host, repo);
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
                  <span
                    title={t('setup.connect.optional')}
                    className={cn(
                      'rounded-full px-1.5 py-0.5 font-mono border border-dashed',
                      loc.skills.some((x) => x.skill === 'connect')
                        ? 'border-green-300 text-green-800 dark:border-green-800 dark:text-green-300'
                        : 'border-zinc-300 text-zinc-400 dark:border-zinc-700 dark:text-zinc-500',
                    )}
                  >
                    connect
                  </span>
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
          {optional && (
            <div className="mt-2">
              <p className="text-xs text-zinc-500 mb-1">{t('setup.connect.skillCmd')}</p>
              <CommandBlock text={optional} />
            </div>
          )}
          {host.host === 'claude' && (
            <div className="mt-2">
              <p className="text-xs text-zinc-500 mb-1">
                {t('setup.alt')}: {t('setup.altClaude')}
              </p>
              <CommandBlock text={`claude --plugin-dir ${shellPath(repo)}`} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

const HOST_NAMES: Record<string, string> = { 'claude-code': 'Claude Code', codex: 'Codex', cursor: 'Cursor' };

function ConnectedCard({ connected: c, repo }: { connected: ConnectedModeInfo; repo: string }) {
  const { t, locale } = useLocale();
  const launcher = `python3 ${shellPath(repo)}/mcp/launch.py`;
  const status: { key: TKey; cls: string } = !c.available
    ? { key: 'setup.connect.status.unavailable', cls: 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400' }
    : c.installed
      ? { key: 'setup.connect.status.ready', cls: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' }
      : c.checks.length
        ? { key: 'setup.connect.status.incomplete', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300' }
        : { key: 'setup.connect.status.notInstalled', cls: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300' };
  const registered = Object.entries(c.hosts);
  const exportApps = Object.entries(c.exports);

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <PlugZap className="size-5 text-zinc-400" />
          {t('setup.connect.title')}
          <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', status.cls)}>{t(status.key)}</span>
        </h2>
        <p className="text-sm text-zinc-500">{t('setup.connect.hint')}</p>
      </div>
      {c.available && (
        <Card>
          <CardContent className="pt-6 space-y-5">
            {c.error && <p className="text-sm text-red-600">{t('setup.connect.error')}: <span className="font-mono text-xs">{c.error}</span></p>}
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="space-y-2 min-w-0">
                <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">{t('setup.connect.checks')}</p>
                {c.vendored && (
                  <p className="text-xs text-zinc-500">
                    befree-bubble-mcp <span className="font-mono">{c.vendored.commit.slice(0, 12)}</span> · {c.vendored.ref} · {c.vendored.files} {t('common.files')}
                  </p>
                )}
                <ul className="space-y-1">
                  {c.checks.map((check) => (
                    <li key={check.name} className="flex items-start gap-2 text-xs min-w-0">
                      {check.ok ? <CheckCircle2 className="size-3.5 shrink-0 mt-0.5 text-green-600 dark:text-green-400" /> : <XCircle className="size-3.5 shrink-0 mt-0.5 text-red-500" />}
                      <span className="shrink-0">{check.name}</span>
                      <span className="font-mono text-zinc-400 truncate" title={check.detail}>
                        {check.detail}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-zinc-500 flex flex-wrap items-center gap-1.5 pt-1">
                  {t('setup.connect.registered')}:
                  {registered.map(([host, on]) => (
                    <span
                      key={host}
                      className={cn(
                        'rounded-full px-1.5 py-0.5',
                        on ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' : 'bg-zinc-100 text-zinc-400 line-through dark:bg-zinc-800 dark:text-zinc-500',
                      )}
                    >
                      {HOST_NAMES[host] ?? host}
                    </span>
                  ))}
                </p>
                <p className="text-xs text-zinc-400">
                  {t('setup.connect.home')}: <span className="font-mono">{c.home}</span>
                </p>
              </div>
              <div className="space-y-2 min-w-0">
                <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">{t('setup.connect.profiles')}</p>
                {c.profiles.length === 0 ? (
                  <p className="text-xs text-zinc-500">{t('setup.connect.noProfiles')}</p>
                ) : (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-zinc-500">
                        <th className="py-1 pr-2 font-medium">{t('setup.connect.profile')}</th>
                        <th className="py-1 pr-2 font-medium">{t('setup.connect.version')}</th>
                        <th className="py-1 pr-2 font-medium">{t('setup.connect.session')}</th>
                        <th className="py-1 font-medium">{t('setup.connect.roles')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.profiles.map((p) => (
                        <tr key={p.name} className="border-t border-zinc-100 dark:border-zinc-800 align-top">
                          <td className="py-1.5 pr-2">
                            <span className="font-mono break-all">{p.name}</span>
                            {p.appId && p.appId !== p.name && <span className="block text-zinc-400 font-mono">{p.appId}</span>}
                          </td>
                          <td className="py-1.5 pr-2 font-mono">{p.appVersion ?? 'test'}</td>
                          <td className="py-1.5 pr-2">
                            {p.sessionCaptured ? (
                              <span className="text-green-700 dark:text-green-400">
                                ✓ {p.sessionUpdated ? formatDate(p.sessionUpdated, locale, true) : ''}
                                {p.sessionProfile && <span className="block text-zinc-400">{t('setup.connect.sessionOf', { profile: p.sessionProfile })}</span>}
                              </span>
                            ) : (
                              <span className="text-zinc-400">{t('setup.connect.noSession')}</span>
                            )}
                          </td>
                          <td className="py-1.5 font-mono text-zinc-500">
                            {[...p.appSessions, ...p.rebuildSessions.map((r) => `rebuild:${r}`)].join(', ') || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {exportApps.length > 0 && (
                  <div className="pt-2">
                    <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300 mb-1">{t('setup.connect.exports')}</p>
                    <ul className="space-y-0.5 text-xs text-zinc-500">
                      {exportApps.map(([app, e]) => (
                        <li key={app}>
                          <span className="font-mono">{app}</span> · {e.count} · {t('setup.connect.latest')} {e.latest.appVersion ?? '?'}
                          {e.latest.fetchedAt ? ` · ${formatDate(e.latest.fetchedAt, locale, true)}` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-xs text-zinc-400 pt-1">{t('setup.connect.privacy')}</p>
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-2 border-t pt-4">
              <div className="space-y-1">
                <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">{c.installed ? t('setup.connect.cmd.check') : t('setup.connect.cmd.install')}</p>
                <CommandBlock text={c.installed ? `${launcher} doctor` : `python3 ${shellPath(repo)}/mcp/install.py`} />
                {!c.installed && <p className="text-xs text-zinc-500">{t('setup.connect.cmd.installNote')}</p>}
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">{t('setup.connect.cmd.login')}</p>
                <CommandBlock text={`${launcher} cli profile add <app-id> --app-id <app-id> --app-version test\n${launcher} cli session login --profile <app-id> --app-id <app-id>`} />
                <p className="text-xs text-zinc-500">{t('setup.connect.cmd.loginNote')}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
