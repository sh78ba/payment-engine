import axios from 'axios';

const API_BASE = '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const fetchMerchants = () => api.get('/merchants/');

export const fetchDashboard = (merchantId) =>
  api.get(`/merchants/${merchantId}/dashboard/`);

export const fetchLedger = (merchantId) =>
  api.get(`/merchants/${merchantId}/ledger/`);

export const fetchPayouts = (merchantId) =>
  api.get(`/merchants/${merchantId}/payouts/list/`);

export const fetchPayoutDetail = (merchantId, payoutId) =>
  api.get(`/merchants/${merchantId}/payouts/${payoutId}/`);

export const createPayout = (merchantId, data, idempotencyKey) =>
  api.post(`/merchants/${merchantId}/payouts/`, data, {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });

export default api;
