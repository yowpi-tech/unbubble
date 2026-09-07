import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="py-16 text-center space-y-3">
      <p className="text-4xl font-bold">404</p>
      <p className="text-zinc-500 text-sm">Not found / Não encontrado.</p>
      <Link href="/" className="text-sm underline">
        ← Dashboard
      </Link>
    </div>
  );
}
