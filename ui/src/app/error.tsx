'use client';

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="py-16 text-center space-y-3">
      <p className="text-lg font-semibold">Something went wrong</p>
      <pre className="text-xs text-red-600 whitespace-pre-wrap">{error.message}</pre>
      <button onClick={reset} className="text-sm underline">
        Retry
      </button>
    </div>
  );
}
