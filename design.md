# Django Backend Technical Design — Mobile App (Auth + Wallet + Accounts)

> Purpose: Technical design for a Django backend that supports mobile authentication (phone + OTP), roles (driver/rider), account setup, referral tracking, and a full-featured in-app wallet (user↔user, user↔driver transfers, beneficiaries, bank accounts, transactions, and payouts).

---

# 1. High-level overview

**Goals**

* Secure phone-based authentication with OTP and optional password flows.
* Role selection and per-role profile data (driver, rider).
* Referral tracking: every user gets a referral code; new signup may attribute a referrer.
* Wallet: on-platform balance, internal transfers, saving beneficiaries, bank account linking, top-ups, withdrawals, transaction history, fees, and reconciliations.
* Strong transactional integrity and anti-fraud controls (rate limits, PINs, 2FA where needed).

**Primary components**

* Django + Django REST Framework (DRF) API
* sqlite for now, postgres later
* Celery (async tasks: SMS, email, payout processing, reconciliation)
* Payment gateway(s) (for card/bank top-ups and driver payouts) - Paystack
* SMS provider (Twilio, Africa-focused providers like Termii, or gateway adapter)

---

# 2. Tech stack & libraries

* **Backend framework**: Django (>=4.x), Django REST Framework
* **Auth/JWT**: djangorestframework-simplejwt (or custom token if required)
* **OTP & phone utilities**: django-phonenumber-field, python-phonenumbers
* **Async**: Celery + Redis broker, django-celery-beat
* **DB**: sqlite for now, postgres later
* **Rate limiting**: django-ratelimit or DRF throttling
* **Security**: django-axes (login throttling) or similar
* **Payments**: provider SDK(s) (Paystack)
* **Monitoring**: Sentry, Prometheus + Grafana (optional)
* **API docs**: drf-yasg or drf-spectacular (OpenAPI)

---

# 3. Data model (core tables)

> All `id` fields use UUID (recommended) for security and sharding friendliness. Use `created_at`, `updated_at` timestamps on all entities.

## User (extends AbstractBaseUser)

* id: UUID (PK)
* phone\_number: E.164 string (unique, indexed)
* email: optional
* first\_name, last\_name
* is\_active, is\_staff
* role: ENUM('rider','driver','admin') or ManyToMany for future roles
* referral\_code: CHAR(8) (unique) — generated on create (e.g., base36 of id or random)
* referred\_by: FK(User) nullable
* password: Django hashed password
* transaction\_pin\_hash: securely hashed/encrypted (see security section)
* kyc\_status: ENUM('none','pending','approved','rejected')
* verified\_phone: bool
* last\_login, created\_at, updated\_at

Indexes: phone\_number unique, referral\_code unique

## Profile / DriverProfile / RiderProfile

* driver-specific: vehicle number, plate\_number, status (available/unavailable), payout\_account\_id
* rider-specific: preferences, saved\_addresses

## Wallet

* id: UUID
* user\_id: FK(User) unique
* balance\_minor: BIGINT (store cents/kobo to avoid float)
* currency: ISO code
* reserved\_balance: BIGINT (for locked funds, e.g., pending rides)
* ledger\_version: integer (optimistic concurrency)

Indexes: user\_id unique

## Transaction (ledger)

* id: UUID
* wallet\_id: FK(Wallet)
* type: ENUM('credit','debit')
* kind: ENUM('topup','transfer','payout','refund','fee','adjustment')
* amount\_minor: BIGINT
* currency
* counterparty\_user\_id: FK(User) nullable
* reference: string (external ID or payment gateway id)
* status: ENUM('pending','completed','failed','reversed')
* metadata: JSONB
* created\_at

Index on reference for idempotency

## Beneficiary

* id
* owner\_user\_id
* beneficiary\_user\_id (optional if internal)
* external\_account: JSONB (bank\_code, account\_number, bank\_name)
* name
* is\_verified: bool
* created\_at

## OTP (short-lived)

* id
* phone\_number
* code (hash optional)
* purpose: ENUM('login','reset\_password','transfer\_confirm')
* attempts
* expires\_at


## BankAccount / PayoutAccount

* id
* user\_id
* bank\_name
* account\_number (store masked in DB; full stored encrypted, should be the 10 nmbers of the phone number)
* bank\_code
* verification\_status
* external\_payout\_id (id at payment provider)

## AuditLog / Activity

* id
* user\_id
* action (string)
* ip\_address
* user\_agent
* data JSONB
* created\_at

---

# 4. Key API endpoints (versioned `/api/v1/`)

> For each endpoint we provide method, path, auth, brief request + response. Use HTTPS for all.

## Authentication & Account Setup

1. `POST /api/v1/auth/phone/submit` — Submit phone to receive OTP

* Auth: none
* Body: `{ "phone": "+2348012345678", "purpose": "login" }`
* Response: `{ "detail": "otp_sent" }`
* Notes: generate OTP, push SMS via Celery task.

2. `POST /api/v1/auth/otp/verify` — Verify OTP and issue token

* Auth: none
* Body: `{ "phone": "+2348012345678", "otp": "123456", "role": "rider" }`
* Response (if new user requires setup): `{ "requires_setup": true, "temp_token": "short_lived_token" }` OR JWT if account exists
* Notes: allow role selection at first verification; if user is new, create user record with `verified_phone=true` and return `temp_token` for account setup.

3. `POST /api/v1/auth/register` — Complete account setup

* Auth: temp token (short-lived) or OTP-verified session
* Body: `{ "first_name":"Aisha","last_name":"Ali","password":"...","referral_code":"AB12CD34" }`
* Response: `{ "access":"...", "refresh":"...", "user": { ... } }`
* Notes: attribute `referred_by` if valid referral\_code exists and not self-referral. Password is 6 digit number.

4. `POST /api/v1/auth/login` — Password login (optional)

* Auth: none
* Body: `{ "phone":"+...","password":"..." }`
* Response: JWT tokens

5. `POST /api/v1/auth/forgot-password` & `POST /api/v1/auth/reset-password` — standard flows with OTP

6. `POST /api/v1/auth/set-transaction-pin` — set or update the 4 digit PIN

* Auth: JWT
* Body: `{ "pin": "1234" }` (pin must be validated and stored as hash)

7. `POST /api/v1/auth/verify-pin` — verify PIN (used before sensitive operations)

* Auth: JWT
* Body: `{ "pin": "1234" }`

8. `GET /api/v1/auth/me` — get profile

* Auth: JWT

## Wallet & Payments

1. `GET /api/v1/wallet/balance` — get balance

* Auth: JWT
* Response: `{ "balance": 12345, "currency":"NGN" }` (balance in minor units)

2. `POST /api/v1/wallet/topup/initiate` — initiate top-up (card/bank)

* Auth: JWT
* Body: `{ "amount": 50000, "currency":"NGN", "payment_method":"card" }`
* Response: `{ "payment_url": "...", "reference": "gw_ref" }`
* Notes: create pending Transaction and wait for webhook from gateway.

3. `POST /api/v1/wallet/topup/webhook` — payment gateway webhook

* Auth: webhook signature verification
* Body: gateway payload
* Action: idempotent update transaction to `completed` and credit wallet in DB transaction.

4. `POST /api/v1/wallet/transfer` — internal transfer (user→user or user→driver)

* Auth: JWT
* Body: `{ "to_user": "user_uuid", "amount": 1000, "currency":"NGN", "pin": "1234", "reference":"optional" }`
* Response: `{ "status": "pending", "transaction_id": "..." }`
* Flow: verify PIN, run atomic DB transaction:

  * Lock both wallets (`SELECT FOR UPDATE`), verify sufficient balance, debit sender, credit recipient, insert ledger Transaction rows, emit notifications, mark completed.
* Anti-fraud: daily limits, throttle, AML checks for large transfers.

5. `POST /api/v1/wallet/transfer/beneficiary` — add beneficiary

* Body: `{ "name":"Ali","account_number":"0112345678","bank_code":"044" }`

6. `GET /api/v1/wallet/beneficiaries` — list

7. `POST /api/v1/wallet/withdraw` — request withdrawal to external bank (uses payouts)

* Auth: JWT
* Body: `{ "beneficiary_id": "...", "amount": 100000, "pin":"1234" }`
* Flow: create payout transaction (pending), call payment provider, update status via webhook/callback.

8. `GET /api/v1/wallet/transactions` — list transactions (filter by type/status), pagination

9. `POST /api/v1/wallet/resolve-account` — resolve bank account (using provider) to fetch recipient name and validate

## Account & Admin

* `GET /api/v1/users/<id>/` - user detail (admin or owner)
* Admin endpoints for adjusting balances, reversing transactions, and running reconciliation jobs (protected by role-based permissions).

---

# 5. Transaction guarantees & concurrency

* Use `SERIALIZABLE` or at minimum `REPEATABLE READ` with `SELECT FOR UPDATE` on Wallet rows when performing multi-row updates.
* Wrap ledger updates + wallet balance changes in a DB transaction so they either commit together or roll back.
* Use idempotency keys for external webhooks and payment gateway callbacks (store `reference` with unique constraint).
* For high throughput, partition ledger table by time or implement read replicas; still keep single source of truth in primary for writes.

---

# 6. Security & compliance

* **Transport**: enforce HTTPS everywhere, HSTS.
* **Auth**: use JWT with short access token and refresh token. Revoke refresh on suspicious events.
* **PIN storage**: do NOT store PIN in plaintext. Use a slow KDF like Argon2 or PBKDF2 with high iterations and unique salt. Optionally encrypt the hash using KMS.
* **Sensitive fields (bank account numbers)**: store encrypted at rest using field-level encryption.
* **Audit**: every sensitive action (transfer, top-up, withdraw) must produce an immutable audit log entry.
* **Rate limiting & brute force protection**: throttle OTP attempts, login attempts, transfer attempts. Use device & IP fingerprinting.
* **Fraud**: implement velocity checks (per-minute, per-hour, per-day limits), AML thresholds for large transfers (flag for manual review).
* **Backups**: nightly DB backups, encrypted at rest. Test restores regularly.
* **PCI/Payments**: do not store raw card data unless certified. Use tokenized methods from payment gateway.

---

# 7. Operational concerns

**Logging**

* Structured logs with correlation IDs. Include request\_id propagated from mobile client.

**Deployment**

* Containerize with Docker; run in Kubernetes or managed container service.
* Use separate environments: staging, prod. Use feature flags for risky flows.


---

# 8. Testing strategy

* Unit tests for models & utils.
* Integration tests covering transfers (multi-wallet), idempotent webhook handling, OTP flows.
* Load tests for top-up/webhook and transfer endpoint concurrency to ensure correct locking.
* Security tests: PIN cracking attempts, rate-limit tests.

---

# 9. OpenAPI / Examples (sample payloads)

**Transfer request**

```json
POST /api/v1/wallet/transfer
Authorization: Bearer <access>
{
  "to_user": "b7f2a8d1-...",
  "amount": 15000,
  "currency": "NGN",
  "pin": "1234",
  "reference": "ride_12345"
}
```

**Response**

```json
{ "status": "completed", "transaction": { "id": "...", "amount": 15000 } }
```

**Top-up webhook** (idempotent handling)

```json
POST /api/v1/wallet/topup/webhook
{
  "event": "payment.success",
  "reference": "gw_ref_123",
  "amount": 50000,
  "currency": "NGN",
  "metadata": { "user_id":"..." }
}
```

---

# 10. Implementation milestones (recommended)

1. Project skeleton: Django + DRF, Docker, CI, basic User model with phone field.
2. OTP flow (Redis-backed), phone verification, basic login.
3. Account setup, referral code generation + attribution.
4. Wallet model + single-endpoint balance check.
5. Internal transfer flow with DB transactions and PIN verification.
6. Beneficiaries & bank account resolution.
7. Payment gateway integration for top-ups and withdrawals.
8. Admin tools, reconciliation jobs, monitoring, and security hardening.

---

# 11. Appendix: sample Django model snippets (schema sketch)

> The full code is not included in this document, but the structure below is recommended as starting point.

```python
class User(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = PhoneNumberField(unique=True)
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    referral_code = models.CharField(max_length=12, unique=True)
    referred_by = models.ForeignKey('self', null=True, on_delete=models.SET_NULL)
    transaction_pin_hash = models.CharField(max_length=255, null=True)

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance_minor = models.BigIntegerField(default=0)
    reserved_balance = models.BigIntegerField(default=0)

class Transaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    type = models.CharField(choices=..., max_length=8)
    amount_minor = models.BigIntegerField()
    status = models.CharField(choices=..., max_length=16)
    reference = models.CharField(max_length=128, db_index=True)
    metadata = JSONField(null=True)
```

---

# 13. Next steps (what I can deliver next)

* Generate detailed Django model + serializer + view code for the auth and wallet flows.
* Produce OpenAPI schema (YAML/JSON) for all endpoints.
* Create migration-ready SQL schema for PostgreSQL.

---

*Document prepared for engineering use — adjust choices (e.g., payment provider, OTP provider) to region and compliance requirements.*
