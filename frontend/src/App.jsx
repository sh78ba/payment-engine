import { useState, useEffect, useCallback } from 'react';
import MerchantSelector from './components/MerchantSelector';
import BalanceCards from './components/BalanceCards';
import PayoutForm from './components/PayoutForm';
import PayoutHistory from './components/PayoutHistory';
import LedgerTable from './components/LedgerTable';
import { fetchMerchants, fetchDashboard, fetchLedger, fetchPayouts } from './api/client';

function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedMerchant, setSelectedMerchant] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load merchants on mount
  useEffect(() => {
    loadMerchants();
  }, []);

  // Load merchant data when selection changes
  useEffect(() => {
    if (selectedMerchant) {
      loadMerchantData(selectedMerchant);
    }
  }, [selectedMerchant]);

  // Auto-refresh every 5 seconds for live status updates
  useEffect(() => {
    if (!selectedMerchant) return;
    const interval = setInterval(() => {
      loadMerchantData(selectedMerchant, true);
    }, 5000);
    return () => clearInterval(interval);
  }, [selectedMerchant]);

  const loadMerchants = async () => {
    try {
      const { data } = await fetchMerchants();
      setMerchants(data);
      if (data.length > 0) {
        setSelectedMerchant(data[0].id);
      }
      setLoading(false);
    } catch (err) {
      setError('Failed to load merchants. Is the backend running?');
      setLoading(false);
    }
  };

  const loadMerchantData = useCallback(async (merchantId, silent = false) => {
    try {
      if (!silent) setLoading(true);
      const [dashRes, ledgerRes, payoutsRes] = await Promise.all([
        fetchDashboard(merchantId),
        fetchLedger(merchantId),
        fetchPayouts(merchantId),
      ]);
      setDashboard(dashRes.data);
      setLedger(ledgerRes.data);
      setPayouts(payoutsRes.data);
      setError(null);
    } catch (err) {
      if (!silent) setError('Failed to load merchant data');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  const handlePayoutCreated = () => {
    if (selectedMerchant) {
      loadMerchantData(selectedMerchant);
    }
  };

  if (loading && !dashboard) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center animate-fade-in">
          <div className="w-12 h-12 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-surface-300 text-sm">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-white/5">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">Playto Pay</h1>
              <p className="text-xs text-surface-300/60">Payout Engine</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs text-surface-300/60">
              <span className="w-2 h-2 rounded-full bg-success-500 animate-pulse-soft"></span>
              Live
            </div>
            <MerchantSelector
              merchants={merchants}
              selected={selectedMerchant}
              onSelect={setSelectedMerchant}
            />
          </div>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="max-w-7xl mx-auto px-6 mt-4">
          <div className="glass-card px-4 py-3 border-danger-500/30 bg-danger-500/10 rounded-xl animate-fade-in">
            <p className="text-danger-500 text-sm flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.07 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              {error}
            </p>
          </div>
        </div>
      )}

      {/* Main Content */}
      {dashboard && (
        <main className="max-w-7xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
          {/* Balance Overview */}
          <BalanceCards dashboard={dashboard} />

          {/* Payout Form + Recent Payouts */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-2">
              <PayoutForm
                merchantId={selectedMerchant}
                bankAccounts={dashboard.bank_accounts || []}
                availableBalance={dashboard.available_balance}
                onPayoutCreated={handlePayoutCreated}
              />
            </div>
            <div className="lg:col-span-3">
              <PayoutHistory payouts={payouts} />
            </div>
          </div>

          {/* Ledger */}
          <LedgerTable entries={ledger} />
        </main>
      )}
    </div>
  );
}

export default App;
