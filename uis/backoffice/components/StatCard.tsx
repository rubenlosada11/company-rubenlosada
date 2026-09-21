interface StatCardProps {
  label: string;
  value: string | number;
  detail?: string;
}

export function StatCard({ label, value, detail }: StatCardProps) {
  return (
    <div className="flex flex-col-reverse rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <dt className="mt-1 text-sm font-semibold text-slate-600">
        {label}
        {detail ? <span className="mt-0.5 block text-xs font-normal text-slate-500">{detail}</span> : null}
      </dt>
      <dd className="font-heading text-3xl text-blue-800">{value}</dd>
    </div>
  );
}
