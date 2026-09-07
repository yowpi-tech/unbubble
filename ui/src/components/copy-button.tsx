'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useT } from '@/components/locale-provider';
import { cn } from '@/lib/utils';

export function CopyButton({ text, className, label }: { text: string; className?: string; label?: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <Button variant="outline" size="sm" onClick={copy} className={cn('shrink-0', className)} aria-label={t('common.copy')}>
      {copied ? <Check className="size-3.5 text-green-600" /> : <Copy className="size-3.5" />}
      {label ?? (copied ? t('common.copied') : t('common.copy'))}
    </Button>
  );
}

/** A command line with a copy button — used for install commands and agent prompts. */
export function CommandBlock({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn('flex items-start gap-2 rounded-lg border bg-zinc-50 dark:bg-zinc-900 p-3', className)}>
      <pre className="flex-1 min-w-0 whitespace-pre-wrap break-all font-mono text-xs leading-relaxed">{text}</pre>
      <CopyButton text={text} />
    </div>
  );
}
