'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, BookOpen, ExternalLink, FolderOpen, Globe, Loader2, Rocket, SearchCheck, Wrench } from 'lucide-react';
import { Breadcrumbs } from '@/components/breadcrumbs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { CommandBlock } from '@/components/copy-button';
import { ProgressBar, STAGE_TINT, StatusBadge, StatusIcon, stageHref } from '@/components/stage-badge';
import { StageControl } from './stage-control';
import { ProjectNav } from './project-nav';
import { formatDate, useLocale } from '@/components/locale-provider';
import { cn } from '@/lib/utils';
import type { ProjectDetail, StageKey } from '@/lib/types';
import type { TKey } from '@/lib/i18n';

const STAGES: StageKey[] = ['audit', 'clone', 'levelup_docs', 'levelup_impl'];
const STAGE_ICON: Record<StageKey, React.ComponentType<{ className?: string }>> = {
  audit: SearchCheck,
  clone: BookOpen,
  levelup_docs: Rocket,
  levelup_impl: Wrench,
};
export function ProjectOverview({ project }: { project: ProjectDetail }) {
  const { t, locale } = useLocale();
  const p = project;
  const [openControl, setOpenControl] = useState<StageKey | null>(null);

  // The suggested prompt comes from the dictionary, so every locale can word it its own way.
  const prompt = t(`project.prompt.${p.nextStep}` as TKey, {
    export: p.state.links?.bubble_export ?? '~/Downloads/<app>.bubble',
    id: p.id,
    round: (p.audit.latest?.version ?? 0) + 1,
  });

  const overrideFor = (k: StageKey) =>
    k === 'audit' ? p.audit.override : k === 'clone' ? p.clone.override : k === 'levelup_docs' ? p.levelup.docsOverride : p.levelup.implOverride;
  const derivedFor = (k: StageKey) =>
    k === 'audit'
      ? p.audit.derivedStatus
      : k === 'clone'
        ? p.clone.derivedStatus
        : k === 'levelup_docs'
          ? p.levelup.docsDerivedStatus
          : p.levelup.implDerivedStatus;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: t('nav.projects'), href: '/projects' }, { label: p.name }]} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold">{p.name}</h1>
          <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-zinc-500">
            <span className="font-mono">{p.id}</span>
            {p.domain && (
              <Badge variant="secondary" className="gap-1">
                <Globe className="size-3" />
                {p.domain}
              </Badge>
            )}
            <span className="inline-flex items-center gap-1 text-xs">
              <FolderOpen className="size-3" />
              <span className="font-mono">{p.dir.replace(/^\/Users\/[^/]+/, '~')}</span>
            </span>
          </div>
        </div>
        <div className="text-right text-xs text-zinc-400">
          {t('common.updated')} {formatDate(p.updatedAt, locale, true)}
        </div>
      </div>

      <ProjectNav id={p.id} />

      {/* Pipeline stepper */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {STAGES.map((k) => {
          const s = p.stages[k];
          const Icon = STAGE_ICON[k];
          const tint = STAGE_TINT[k];
          const isNext = p.nextStep === k;
          const override = overrideFor(k);
          return (
            <Card key={k} className={cn('relative', isNext && 'ring-2', isNext && tint.ring)}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div className={cn('rounded-lg p-2', tint.bg, tint.fg)}>
                    <Icon className="size-5" />
                  </div>
                  <StatusBadge status={s.status} manual={!!override?.status} />
                </div>
                <CardTitle className="text-base mt-2">{t(`stage.${k}`)}</CardTitle>
                <p className="text-xs text-zinc-500">{t(`stage.${k}.desc` as TKey)}</p>
              </CardHeader>
              <CardContent className="space-y-3">
                <ProgressBar value={s.progress} stage={k} />
                <p className="text-xs text-zinc-500 tabular-nums min-h-4">{s.detail}</p>
                {override?.note && <p className="text-xs italic text-zinc-500 border-l-2 pl-2">{override.note}</p>}
                <div className="flex items-center justify-between">
                  <Button variant="outline" size="xs" nativeButton={false} render={<Link href={stageHref(p.id, k)} />}>
                    {t('common.details')}
                    <ArrowRight className="size-3" />
                  </Button>
                  <Button variant="ghost" size="xs" onClick={() => setOpenControl(openControl === k ? null : k)}>
                    ✎ {t('project.override')}
                  </Button>
                </div>
                {openControl === k && <StageControl projectId={p.id} stage={k} derived={derivedFor(k)} override={override} />}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Next step */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <StatusIcon status={p.nextStep === 'rebuild_done' ? 'done' : 'in_progress'} />
            {t('common.nextStep')}: {t(`stage.${p.nextStep}`)}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-zinc-600 dark:text-zinc-300">{t(`project.nextStep.${p.nextStep}` as TKey)}</p>
          {prompt && (
            <div>
              <p className="text-xs text-zinc-500 mb-1">{t('project.promptHint')}</p>
              <CommandBlock text={prompt} />
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <LinksForm project={p} />
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('project.files')}</CardTitle>
          </CardHeader>
          <CardContent>
            <FileTree files={p.files} projectId={p.id} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function LinksForm({ project }: { project: ProjectDetail }) {
  const { t } = useLocale();
  const router = useRouter();
  const [links, setLinks] = useState({ ...project.state.links });
  const [notes, setNotes] = useState(project.state.notes ?? '');
  const [name, setName] = useState(project.state.name ?? '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const res = await fetch(`/api/projects/${project.id}/state`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ links, notes: notes || null, name: name || null }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 1500);
        router.refresh();
      }
    } finally {
      setSaving(false);
    }
  }

  const fields: { key: keyof NonNullable<ProjectDetail['state']['links']>; label: TKey; mono?: boolean }[] = [
    { key: 'bubble_export', label: 'project.links.bubble_export', mono: true },
    { key: 'rebuild_repo', label: 'project.links.rebuild_repo', mono: true },
    { key: 'github', label: 'project.links.github' },
    { key: 'tracker', label: 'project.links.tracker' },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('project.links')}</CardTitle>
        <p className="text-xs text-zinc-500">
          {t('project.stateFile')}: <span className="font-mono">unbubble.json</span>
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="name" className="text-xs">
            {t('nav.projects')} · {t('common.details')}
          </Label>
          <Input id="name" className="h-8 text-sm" value={name} onChange={(e) => setName(e.target.value)} placeholder={project.name} />
        </div>
        {fields.map((f) => (
          <div key={f.key} className="space-y-1">
            <Label htmlFor={`link-${f.key}`} className="text-xs">
              {t(f.label)}
            </Label>
            <div className="flex gap-2">
              <Input
                id={`link-${f.key}`}
                className={cn('h-8 text-sm', f.mono && 'font-mono')}
                value={links[f.key] ?? ''}
                onChange={(e) => setLinks({ ...links, [f.key]: e.target.value })}
              />
              {links[f.key] && /^https?:/i.test(links[f.key] ?? '') && (
                <Button variant="outline" size="icon-sm" nativeButton={false} render={<a href={links[f.key]} target="_blank" rel="noreferrer" />}>
                  <ExternalLink className="size-3.5" />
                </Button>
              )}
            </div>
          </div>
        ))}
        <div className="space-y-1">
          <Label htmlFor="notes" className="text-xs">
            {t('project.notes')}
          </Label>
          <textarea
            id="notes"
            className="w-full min-h-20 rounded-md border bg-transparent px-3 py-2 text-sm dark:bg-zinc-900 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <Button size="sm" onClick={save} disabled={saving}>
          {saving && <Loader2 className="size-3.5 animate-spin" />}
          {saved ? t('project.saved') : t('common.save')}
        </Button>
      </CardContent>
    </Card>
  );
}

function FileTree({ files, projectId }: { files: ProjectDetail['files']; projectId: string }) {
  const { t, locale } = useLocale();
  const byDir = new Map<string, ProjectDetail['files']>();
  for (const f of files) {
    const dir = f.path.includes('/') ? f.path.slice(0, f.path.lastIndexOf('/')) : '.';
    if (!byDir.has(dir)) byDir.set(dir, []);
    byDir.get(dir)!.push(f);
  }
  const dirs = Array.from(byDir.keys()).sort((a, b) => (a === '.' ? -1 : b === '.' ? 1 : a.localeCompare(b)));
  return (
    <div className="max-h-96 overflow-auto text-sm">
      {dirs.map((dir) => (
        <details key={dir} open={dir === '.' || dir === 'levelup' || dir === 'docs'} className="mb-1">
          <summary className="cursor-pointer text-xs font-semibold text-zinc-500 py-1">
            {dir === '.' ? '/' : dir + '/'} <span className="font-normal">({byDir.get(dir)!.length} {t('common.files')})</span>
          </summary>
          <ul className="pl-3">
            {byDir.get(dir)!.map((f) => {
              const base = f.path.slice(f.path.lastIndexOf('/') + 1);
              const viewable = /\.(md|json|html|txt|csv|py|example)$/i.test(base) || base === '.env.example';
              return (
                <li key={f.path} className="flex items-center justify-between gap-2 py-0.5 text-xs">
                  {viewable ? (
                    <a
                      href={`/api/projects/${projectId}/file?path=${encodeURIComponent(f.path)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono truncate text-zinc-700 dark:text-zinc-300 hover:underline"
                    >
                      {base}
                    </a>
                  ) : (
                    <span className="font-mono truncate text-zinc-500">{base}</span>
                  )}
                  <span className="text-zinc-400 whitespace-nowrap tabular-nums">
                    {(f.size / 1024).toFixed(0)} KB · {formatDate(f.mtime, locale)}
                  </span>
                </li>
              );
            })}
          </ul>
        </details>
      ))}
    </div>
  );
}
