'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useT } from '@/components/locale-provider';
import type { StageKey, StageOverride, StageStatus } from '@/lib/types';

/**
 * Manual override for one stage: pick a status (or go back to the derived one) and leave a
 * note. Persists to <project>/unbubble.json through PATCH /api/projects/:id/state.
 */
export function StageControl({
  projectId,
  stage,
  derived,
  override,
}: {
  projectId: string;
  stage: StageKey;
  derived: StageStatus;
  override?: StageOverride;
}) {
  const t = useT();
  const router = useRouter();
  const [status, setStatus] = useState<StageStatus | ''>(override?.status ?? '');
  const [note, setNote] = useState(override?.note ?? '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/state`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage: { key: stage, status: status || null, note: note.trim() || null } }),
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

  const selectCls =
    'h-8 rounded-md border bg-transparent px-2 text-sm text-foreground dark:bg-zinc-900 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring';

  return (
    <div className="space-y-3 rounded-lg border border-dashed p-3">
      <div>
        <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">{t('project.override')}</p>
        <p className="text-xs text-zinc-500">{t('project.overrideHint')}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-[auto_1fr_auto] sm:items-end">
        <div className="space-y-1">
          <Label htmlFor={`status-${stage}`} className="text-xs">
            Status
          </Label>
          <select id={`status-${stage}`} className={selectCls} value={status} onChange={(e) => setStatus(e.target.value as StageStatus | '')}>
            <option value="">
              {t('project.overrideReset')} ({t(`status.${derived}`)})
            </option>
            <option value="not_started">{t('status.not_started')}</option>
            <option value="in_progress">{t('status.in_progress')}</option>
            <option value="done">{t('status.done')}</option>
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor={`note-${stage}`} className="text-xs">
            {t('project.note')}
          </Label>
          <Input id={`note-${stage}`} className="h-8 text-sm" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('project.notePlaceholder')} />
        </div>
        <Button size="sm" onClick={save} disabled={saving}>
          {saving ? <Loader2 className="size-3.5 animate-spin" /> : null}
          {saved ? t('common.copied').replace(t('common.copied'), t('project.saved')) : t('common.save')}
        </Button>
      </div>
    </div>
  );
}
