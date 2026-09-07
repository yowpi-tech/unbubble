'use client';

import { CheckCircle2, Circle, CircleDashed, PartyPopper } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useT } from '@/components/locale-provider';
import type { StageKey, StageStatus } from '@/lib/types';

/** One color per pipeline stage — the same tints BubbleDocs uses for its quick actions. */
export const STAGE_TINT: Record<StageKey, { bg: string; fg: string; bar: string; ring: string }> = {
  audit: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    fg: 'text-amber-700 dark:text-amber-400',
    bar: 'bg-amber-500',
    ring: 'ring-amber-500/40',
  },
  clone: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    fg: 'text-blue-700 dark:text-blue-400',
    bar: 'bg-blue-500',
    ring: 'ring-blue-500/40',
  },
  levelup_docs: {
    bg: 'bg-purple-100 dark:bg-purple-900/30',
    fg: 'text-purple-700 dark:text-purple-400',
    bar: 'bg-purple-500',
    ring: 'ring-purple-500/40',
  },
  levelup_impl: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    fg: 'text-green-700 dark:text-green-400',
    bar: 'bg-green-500',
    ring: 'ring-green-500/40',
  },
};

/** Where each stage lives inside a project: audit report, clone docs, level-up pack, backlog stories. */
export function stageHref(projectId: string, stage: StageKey | 'rebuild_done'): string {
  const base = `/projects/${projectId}`;
  switch (stage) {
    case 'audit':
      return `${base}/audit`;
    case 'clone':
      return `${base}/docs`;
    case 'levelup_docs':
      return `${base}/levelup`;
    case 'levelup_impl':
      return `${base}/levelup#implementation`;
    default:
      return base;
  }
}

export function StatusIcon({ status, className }: { status: StageStatus; className?: string }) {
  if (status === 'done') return <CheckCircle2 className={cn('size-4 text-green-600 dark:text-green-400', className)} />;
  if (status === 'in_progress') return <CircleDashed className={cn('size-4 text-amber-600 dark:text-amber-400', className)} />;
  return <Circle className={cn('size-4 text-zinc-300 dark:text-zinc-600', className)} />;
}

export function StatusBadge({ status, manual }: { status: StageStatus; manual?: boolean }) {
  const t = useT();
  const cls =
    status === 'done'
      ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
      : status === 'in_progress'
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
        : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400';
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium', cls)} title={manual ? t('status.manual') : undefined}>
      <StatusIcon status={status} className="size-3" />
      {t(`status.${status}`)}
      {manual && <span className="opacity-70">·✎</span>}
    </span>
  );
}

/** Small dot used in the sidebar: which stage the project is waiting on. */
export function StageDot({ step }: { step: StageKey | 'rebuild_done' }) {
  if (step === 'rebuild_done') return <PartyPopper className="size-3 text-green-600 dark:text-green-400 shrink-0" />;
  return <span className={cn('size-2 rounded-full shrink-0', STAGE_TINT[step].bar)} />;
}

export function ProgressBar({ value, stage, className }: { value: number; stage: StageKey; className?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className={cn('h-1.5 w-full rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden', className)} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className={cn('h-full rounded-full transition-all', STAGE_TINT[stage].bar)} style={{ width: `${pct}%` }} />
    </div>
  );
}
