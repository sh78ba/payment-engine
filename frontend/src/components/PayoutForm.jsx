import { useState } from 'react';
import { createPayout } from '../api/client';

function generateUUID() {
  return crypto.randomUUID();
}

const formatINR = (paise) => {
  const rupees = paise / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(rupees);
};

export default function PayoutForm({ merchantId, bankAccounts, availableBalance, onPayoutCreated }) {
  const [amountRupees, setAmountRupees] = useState('');
  const [bankAccountId, setBankAccountId] = useState(bankAccounts[0]?.id || '');
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFeedback(null);

    const amountPaise = Math.round(parseFloat(amountRupees) * 100);
    if (isNaN(amountPaise) || amountPaise <= 0) {
      setFeedback({ type: 'error', message: 'Enter a valid amount' });
      return;
    }

    if (amountPaise > availableBalance) {
      setFeedback({
        type: 'error',
        message: `Insufficient balance. Available: ${formatINR(availableBalance)}`,
      });
      return;
    }

    if (!bankAccountId) {
      setFeedback({ type: 'error', message: 'Select a bank account' });
      return;
    }

    setSubmitting(true);
    const idempotencyKey = generateUUID();

    try {
      const { data } = await createPayout(
        merchantId,
        { amount_paise: amountPaise, bank_account_id: bankAccountId },
        idempotencyKey
      );
      setFeedback({
        type: 'success',
        message: `Payout of ${formatINR(amountPaise)} created successfully!`,
      });
      setAmountRupees('');
      onPayoutCreated?.();
    } catch (err) {
      const msg = err.response?.data?.error || err.message || 'Payout failed';
      setFeedback({ type: 'error', message: msg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="glass-card p-6 animate-slide-up" style={{ animationDelay: '200ms' }}>
      <div className="flex items-center gap-2 mb-5">
        <div className="bg-brand-500/15 p-2 rounded-lg">
          <svg className="w-5 h-5 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </div>
        <h2 className="text-base font-semibold text-white">Request Payout</h2>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Amount Input */}
        <div>
          <label htmlFor="payout-amount" className="block text-xs font-medium text-surface-300/70 mb-1.5">
            Amount (₹)
          </label>
          <div className="relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-300/40 font-mono text-sm">₹</span>
            <input
              id="payout-amount"
              type="number"
              min="0.01"
              step="0.01"
              value={amountRupees}
              onChange={(e) => setAmountRupees(e.target.value)}
              placeholder="0.00"
              className="input-field pl-8 font-mono"
              disabled={submitting}
            />
          </div>
          <p className="text-[11px] text-surface-300/40 mt-1">
            Available: {formatINR(availableBalance)}
          </p>
        </div>

        {/* Bank Account Selector */}
        <div>
          <label htmlFor="bank-account" className="block text-xs font-medium text-surface-300/70 mb-1.5">
            Bank Account
          </label>
          <select
            id="bank-account"
            value={bankAccountId}
            onChange={(e) => setBankAccountId(e.target.value)}
            className="input-field cursor-pointer"
            disabled={submitting}
          >
            {bankAccounts.map((ba) => (
              <option key={ba.id} value={ba.id} className="bg-surface-900">
                {ba.bank_name} — ****{ba.account_number.slice(-4)}
              </option>
            ))}
          </select>
        </div>

        {/* Submit */}
        <button
          type="submit"
          id="submit-payout"
          disabled={submitting || !amountRupees}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {submitting ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              Processing...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
              Submit Payout Request
            </>
          )}
        </button>
      </form>

      {/* Feedback */}
      {feedback && (
        <div
          className={`mt-4 px-4 py-3 rounded-xl text-sm animate-fade-in ${
            feedback.type === 'success'
              ? 'bg-success-500/10 text-success-500 border border-success-500/20'
              : 'bg-danger-500/10 text-danger-500 border border-danger-500/20'
          }`}
        >
          {feedback.message}
        </div>
      )}
    </div>
  );
}
