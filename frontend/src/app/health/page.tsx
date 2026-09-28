export default function HealthPage() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-2xl font-bold">System Health</h1>
      <div className="mt-6 space-y-4">
        <HealthRow label="Frontend" status="running" />
      </div>
      <p className="mt-8 text-sm text-gray-400">
        Backend health available at{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">
          /health
        </code>{" "}
        on the API server.
      </p>
    </main>
  );
}

function HealthRow({ label, status }: { label: string; status: string }) {
  const isUp = status === "running" || status === "connected";
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
      <span className="font-medium">{label}</span>
      <span
        className={`rounded-full px-3 py-1 text-sm font-medium ${
          isUp
            ? "bg-green-100 text-green-700"
            : "bg-red-100 text-red-700"
        }`}
      >
        {status}
      </span>
    </div>
  );
}
