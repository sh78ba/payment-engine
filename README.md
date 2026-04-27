# Playto Payout Engine

A production-grade payout engine for handling international payment collections and merchant INR payouts. Built with Django + DRF, React + Tailwind, PostgreSQL, and Celery.

## Architecture

```
┌────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  React + TW    │────▶│  Django + DRF    │────▶│ PostgreSQL  │
│  Dashboard     │◀────│  REST API        │◀────│             │
└────────────────┘     └──────┬───────────┘     └─────────────┘
                              │
                       ┌──────▼───────────┐     ┌─────────────┐
                       │  Celery Workers  │────▶│   Redis     │
                       │  (Payout Proc.)  │◀────│  (Broker)   │
                       └──────────────────┘     └─────────────┘
```

## Quick Start (Docker)

```bash
# Clone the repository
git clone <repo-url> && cd payment-engine

# Start everything
docker-compose up --build

# Access:
# - Frontend:  http://localhost:3000
# - Backend:   http://localhost:8000/api/v1/
# - Admin:     http://localhost:8000/admin/
```

The seed script runs automatically on startup, creating 3 merchants with credit histories.

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 15+
- Redis 7+

### Backend Setup

```bash
# Create and activate virtual environment
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (or use defaults for local dev)
export DATABASE_URL=postgres://payto:payto_secret@localhost:5432/payto_engine
export REDIS_URL=redis://localhost:6379/0

# Create the database
createdb payto_engine  # Or via psql: CREATE DATABASE payto_engine;

# Run migrations
python manage.py migrate

# Seed test data
python manage.py seed_merchants

# Start the dev server
python manage.py runserver
```

### Celery Workers

```bash
# In a separate terminal (with venv activated)
cd backend

# Start the worker
celery -A config worker -l info -c 4

# In another terminal, start the beat scheduler
celery -A config beat -l info
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
cd backend

# Run all tests
python manage.py test tests

# Run specific test suites
python manage.py test tests.test_concurrency
python manage.py test tests.test_idempotency
python manage.py test tests.test_state_machine
```

## Production Deployment (Render / Railway)

This project is configured to run smoothly on free-tier PaaS providers like [Render](https://render.com) or [Railway](https://railway.app).

### Backend (Django + Celery)
When deploying the `backend` directory as a Docker web service:
1. The `backend/Dockerfile` is automatically configured to use `backend/start.sh` as the `CMD`.
2. `start.sh` runs migrations, seeds the database, starts the Celery worker, starts the Celery beat scheduler, and serves the Django app via Gunicorn **all in a single container**.
3. You must set the following environment variables on your provider:
   - `DATABASE_URL`: Your PostgreSQL connection string
   - `REDIS_URL`: Your Redis connection string
   - `ALLOWED_HOSTS`: `*` (or your specific frontend domain)

### Frontend (React)
When deploying the `frontend` directory as a Static Site:
1. Build command: `npm install && npm run build`
2. Publish directory: `dist`
3. You must set the following environment variable:
   - `VITE_API_URL`: Your deployed backend URL (e.g., `https://your-backend.onrender.com/api/v1`)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/merchants/` | List all merchants |
| GET | `/api/v1/merchants/<id>/dashboard/` | Merchant dashboard data |
| GET | `/api/v1/merchants/<id>/ledger/` | Merchant ledger entries |
| POST | `/api/v1/merchants/<id>/payouts/` | Create a payout (requires `Idempotency-Key` header) |
| GET | `/api/v1/merchants/<id>/payouts/list/` | List merchant payouts |
| GET | `/api/v1/merchants/<id>/payouts/<payout_id>/` | Get payout details |

### Create Payout Example

```bash
curl -X POST http://localhost:8000/api/v1/merchants/<merchant-id>/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"amount_paise": 500000, "bank_account_id": "<bank-account-id>"}'
```

## Seeded Test Data

| Merchant | Balance | Bank |
|----------|---------|------|
| Arjun's Design Studio | ₹1,50,000 | HDFC Bank |
| Priya's Content Agency | ₹85,000 | ICICI Bank |
| Rahul's Dev Shop | ₹2,25,000 | State Bank of India |

## Project Structure

```
payment-engine/
├── docker-compose.yml          # Full stack orchestration
├── backend/
│   ├── config/                 # Django settings, URLs, Celery config
│   ├── payouts/
│   │   ├── models.py           # Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey
│   │   ├── services/
│   │   │   ├── ledger.py       # Balance calculations (DB-level aggregation)
│   │   │   └── payout.py       # Payout creation with locking + idempotency
│   │   ├── views.py            # DRF API views
│   │   ├── tasks.py            # Celery tasks (processor, retry, cleanup)
│   │   ├── serializers.py      # DRF serializers
│   │   └── management/commands/seed_merchants.py
│   └── tests/
│       ├── test_concurrency.py  # Thread-based concurrency tests
│       ├── test_idempotency.py  # Idempotency key tests
│       └── test_state_machine.py # State transition tests
├── frontend/
│   └── src/
│       ├── App.jsx             # Main dashboard with auto-refresh
│       ├── components/         # Balance cards, payout form, tables
│       └── api/client.js       # Axios API client
├── README.md
└── EXPLAINER.md
```

## Key Technical Decisions

- **All amounts in paise (BigIntegerField)** — no floating point, no rounding errors
- **Balance derived from ledger** — never cached, always computed via DB aggregation
- **SELECT FOR UPDATE** on merchant row — serializes concurrent payout requests at the DB level
- **Idempotency via unique constraint** — race conditions handled by IntegrityError catch
- **Atomic state transitions + refunds** — FAILED state and REFUND entry in same transaction
- **Exponential backoff retries** — stuck payouts retried with backoff, max 3 attempts
