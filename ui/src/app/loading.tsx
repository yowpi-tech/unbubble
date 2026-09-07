export default function Loading() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-8 bg-zinc-200 dark:bg-zinc-800 rounded w-1/3" />
      <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-2/3" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4 mt-6">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-40 bg-zinc-100 dark:bg-zinc-900 rounded-xl" />
        ))}
      </div>
    </div>
  );
}
