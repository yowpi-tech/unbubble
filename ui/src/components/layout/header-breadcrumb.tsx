'use client';

import { createContext, useContext, useState, ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ChevronRight } from 'lucide-react';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface HeaderBreadcrumbContextValue {
  items: BreadcrumbItem[];
  setItems: (items: BreadcrumbItem[]) => void;
}

const HeaderBreadcrumbContext = createContext<HeaderBreadcrumbContextValue>({
  items: [],
  setItems: () => {},
});

export function HeaderBreadcrumbProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<BreadcrumbItem[]>([]);
  return (
    <HeaderBreadcrumbContext.Provider value={{ items, setItems }}>
      {children}
    </HeaderBreadcrumbContext.Provider>
  );
}

export function useHeaderBreadcrumb() {
  return useContext(HeaderBreadcrumbContext);
}

export function HeaderBreadcrumb() {
  const { items } = useContext(HeaderBreadcrumbContext);
  const router = useRouter();

  if (items.length === 0) return null;

  // Back button goes to the previous level (last item with href)
  const itemsWithHref = items.filter((item) => item.href);
  const backTarget = itemsWithHref.length > 0 ? itemsWithHref[itemsWithHref.length - 1] : null;

  return (
    <div className="flex items-center gap-2">
      {backTarget && (
        <button
          onClick={() => router.push(backTarget.href!)}
          className="shrink-0 p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      )}
      <nav className="flex items-center gap-1 text-sm text-zinc-400 min-w-0">
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <span key={i} className="flex items-center gap-1 min-w-0">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
              {isLast || !item.href ? (
                <span
                  className={
                    isLast
                      ? 'text-zinc-700 dark:text-zinc-200 font-medium truncate'
                      : 'truncate'
                  }
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  href={item.href}
                  className="hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors truncate"
                >
                  {item.label}
                </Link>
              )}
            </span>
          );
        })}
      </nav>
    </div>
  );
}
