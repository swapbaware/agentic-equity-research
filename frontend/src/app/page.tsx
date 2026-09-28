export default function HomePage() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-16">
      <h1 className="text-3xl font-bold">Agentic Equity Research</h1>
      <p className="mt-4 text-lg text-gray-600">
        Evidence-driven research platform for Indian listed companies (NSE/BSE).
      </p>
      <div className="mt-8 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold">Platform Status</h2>
        <p className="mt-2 text-gray-500">
          Phase 2 — Production skeleton deployed. No research agents active yet.
        </p>
      </div>
    </main>
  );
}
