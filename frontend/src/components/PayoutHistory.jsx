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

const statusConfig = {
  PENDING: { class: 'status-pending', label: 'Pending', icon: '⏳' },
  PROCESSING: { class: 'status-processing', label: 'Processing', icon: '⚙️' },
  COMPLETED: { class: 'status-completed', label: 'Completed', icon: '✓' },
  FAILED: { class: 'status-failed', label: 'Failed', icon: '✕' },
};

export default function PayoutHistory({ payouts }) {
  if (!payouts || payouts.length === 0) {
    return (
      <div className="glass-card p-6 animate-slide-up" style={{ animationDelay: '280ms' }}>
        <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <div className="bg-brand-500/15 p-2 rounded-lg">
            <svg className="w-5 h-5 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          Payout History
        </h2>
        <div className="text-center py-10">
          <p className="text-surface-300/40 text-sm">No payouts yet</p>
          <p className="text-surface-300/25 text-xs mt-1">Submit your first payout request</p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-6 animate-slide-up" style={{ animationDelay: '280ms' }}>
      <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
        <div className="bg-brand-500/15 p-2 rounded-lg">
          <svg className="w-5 h-5 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        Payout History
        <span className="text-xs text-surface-300/40 font-normal ml-auto">{payouts.length} payouts</span>
      </h2>

      <div className="overflow-x-auto -mx-6 px-6">
        <table className="w-full text-sm" id="payout-history-table">
          <thead>
            <tr className="text-xs text-surface-300/50 uppercase tracking-wider border-b border-white/5">
              <th className="text-left pb-3 pr-4 font-medium">Amount</th>
              <th className="text-left pb-3 pr-4 font-medium">Status</th>
              <th className="text-left pb-3 pr-4 font-medium">Bank</th>
              <th className="text-left pb-3 pr-4 font-medium">Attempts</th>
              <th className="text-left pb-3 font-medium">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {payouts.map((p, i) => {
              const status = statusConfig[p.status] || statusConfig.PENDING;
              return (
                <tr
                  key={p.id}
                  className="hover:bg-white/[0.02] transition-colors"
                  style={{ animationDelay: `${i * 50}ms` }}
                >
                  <td className="py-3 pr-4">
                    <span className="font-mono font-semibold text-white">
                      {formatINR(p.amount_paise)}
                    </span>
                  </td>
                  <td className="py-3 pr-4">
                    <span className={`status-badge ${status.class}`}>
                      {status.icon} {status.label}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-surface-300/60">
                    {p.bank_account?.bank_name || '—'}
                    <span className="text-surface-300/30 ml-1">
                      ****{p.bank_account?.account_number?.slice(-4) || ''}
                    </span>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="font-mono text-surface-300/50">{p.attempt_count}</span>
                  </td>
                  <td className="py-3 text-surface-300/50 text-xs">
                    {formatDate(p.created_at)}
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
