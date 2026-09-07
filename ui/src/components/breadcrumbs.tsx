'use client';

import { useEffect } from 'react';
import { useHeaderBreadcrumb, type BreadcrumbItem } from '@/components/layout/header-breadcrumb';

/** Server pages render this to publish their breadcrumb into the shell header. */
export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  const { setItems } = useHeaderBreadcrumb();
  const key = JSON.stringify(items);
  useEffect(() => {
    setItems(JSON.parse(key) as BreadcrumbItem[]);
    return () => setItems([]);
  }, [key, setItems]);
  return null;
}
