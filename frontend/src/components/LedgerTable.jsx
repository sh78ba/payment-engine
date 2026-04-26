const formatINR = (paise) => {
  const rupees = paise / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(rupees);
};

const formatDate = (dateStr) => {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const typeConfig = {
  CREDIT: {
    label: 'Credit',
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/10',
    sign: '+',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7 11l5-5m0 0l5 5m-5-5v12" />
      </svg>
    ),
  },
  DEBIT: {
    label: 'Debit',
    color: 'text-rose-400',
    bg: 'bg-rose-500/10',
    sign: '−',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M17 13l-5 5m0 0l-5-5m5 5V6" />
      </svg>
    ),
  },
  REFUND: {
    label: 'Refund',
    color: 'text-amber-400',
    bg: 'bg-amber-500/10',
    sign: '+',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
      </svg>
    ),
  },
};

export default function LedgerTable({ entries }) {
  if (!entries || entries.length === 0) {
    return null;
  }

  return (
    <div className="glass-card p-6 animate-slide-up" style={{ animationDelay: '360ms' }}>
      <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
        <div className="bg-brand-500/15 p-2 rounded-lg">
          <svg className="w-5 h-5 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        Ledger
        <span className="text-xs text-surface-300/40 font-normal ml-auto">
          {entries.length} entries
        </span>
      </h2>

      <div className="overflow-x-auto -mx-6 px-6">
        <table className="w-full text-sm" id="ledger-table">
          <thead>
            <tr className="text-xs text-surface-300/50 uppercase tracking-wider border-b border-white/5">
              <th className="text-left pb-3 pr-4 font-medium">Type</th>
              <th className="text-left pb-3 pr-4 font-medium">Amount</th>
              <th className="text-left pb-3 pr-4 font-medium">Description</th>
              <th className="text-left pb-3 font-medium">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {entries.map((entry) => {
              const config = typeConfig[entry.entry_type] || typeConfig.CREDIT;
              return (
                <tr key={entry.id} className="hover:bg-white/[0.02] transition-colors">
                  <td className="py-3 pr-4">
                    <div className="flex items-center gap-2">
                      <span className={`${config.bg} ${config.color} p-1.5 rounded-lg`}>
                        {config.icon}
                      </span>
                      <span className={`text-xs font-medium ${config.color}`}>
                        {config.label}
                      </span>
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <span className={`font-mono font-semibold ${config.color}`}>
                      {config.sign}{formatINR(entry.amount_paise)}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-surface-300/60 text-xs max-w-[300px] truncate">
                    {entry.description || '—'}
                  </td>
                  <td className="py-3 text-surface-300/50 text-xs whitespace-nowrap">
                    {formatDate(entry.created_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
