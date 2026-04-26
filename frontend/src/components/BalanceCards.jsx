/**
 * Format paise to INR display string.
 * 1500000 paise -> ₹15,000.00
 */
const formatINR = (paise) => {
  const rupees = paise / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(rupees);
};

const formatCompact = (paise) => {
  const rupees = paise / 100;
  if (rupees >= 100000) return `₹${(rupees / 100000).toFixed(1)}L`;
  if (rupees >= 1000) return `₹${(rupees / 1000).toFixed(1)}K`;
  return formatINR(paise);
};

export default function BalanceCards({ dashboard }) {
  const { available_balance, held_balance, total_credits, total_debits } = dashboard;

  const cards = [
    {
      label: 'Available Balance',
      value: available_balance,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
      gradient: 'from-emerald-500/20 to-emerald-600/5',
      accent: 'text-emerald-400',
      iconBg: 'bg-emerald-500/15',
      isPrimary: true,
    },
    {
      label: 'Held Balance',
      value: held_balance,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
      ),
      gradient: 'from-amber-500/20 to-amber-600/5',
      accent: 'text-amber-400',
      iconBg: 'bg-amber-500/15',
    },
    {
      label: 'Total Credits',
      value: total_credits,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M7 11l5-5m0 0l5 5m-5-5v12" />
        </svg>
      ),
      gradient: 'from-brand-500/20 to-brand-600/5',
      accent: 'text-brand-400',
      iconBg: 'bg-brand-500/15',
    },
    {
      label: 'Total Debits',
      value: total_debits,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17 13l-5 5m0 0l-5-5m5 5V6" />
        </svg>
      ),
      gradient: 'from-rose-500/20 to-rose-600/5',
      accent: 'text-rose-400',
      iconBg: 'bg-rose-500/15',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, i) => (
        <div
          key={card.label}
          className={`glass-card p-5 bg-gradient-to-br ${card.gradient} animate-slide-up`}
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-surface-300/70 uppercase tracking-wider">
              {card.label}
            </span>
            <div className={`${card.iconBg} p-2 rounded-lg ${card.accent}`}>
              {card.icon}
            </div>
          </div>
          <div className={`${card.isPrimary ? 'text-2xl' : 'text-xl'} font-bold ${card.accent} font-mono tracking-tight`}>
            {formatINR(card.value)}
          </div>
          <div className="text-[10px] text-surface-300/40 mt-1 font-mono">
            {card.value.toLocaleString('en-IN')} paise
          </div>
        </div>
      ))}
    </div>
  );
}
