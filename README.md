# Agrani Bank PLC Core Banking System (CBS) — Internship Prototype

[![GitHub repository](https://img.shields.io/badge/GitHub-agrani--cbs--prototype-181717?logo=github)](https://github.com/sanjid-hasan307/agrani-cbs-prototype)

> **Development prototype only.** This internship project demonstrates selected core-banking workflows. It is not an official Agrani Bank system, a complete banking platform, or suitable for production. Use only locally prepared demonstration data; never enter real customer or banking data.

## Project overview

The project is a modular Django application with a separate Vue 3 web client. It models branches, staff, customers, account products, accounts, transactions, transaction entries, and audit records. Its scope is a learning prototype for staff sign-in and selected Teller and Manager transaction workflows—not a complete Core Banking System.

## Implemented and verified

- Staff sign-in uses Django authentication and sessions. Django Groups are used to identify roles such as Teller, Manager, and Auditor.
- Tellers can submit deposit, withdrawal, and internal transfer **requests** through the Django dashboard and the Vue client.
- Requests are initially pending. Account balances are not changed when a Teller submits a request.
- Managers can review pending requests and approve or reject them. The approval service prevents a maker from approving or rejecting their own request. An approved request is posted; a rejected request does not change balances.
- Posting uses `Decimal` amounts, atomic database transactions, row locks on affected accounts, and debit/credit entry balance validation. It updates the account's available and ledger balances.
- Tellers can view and filter their own transaction history. Manager pending requests can be filtered and paginated.
- Audit records are created for transaction initiation and Manager approval or rejection.
- The Vue application has login, Teller, and Manager screens connected to Django APIs. Django-rendered Teller, Manager, and Auditor dashboards are also present.

Here, “ledger balance” refers to a balance field on the account model. The code does not establish a complete general-ledger accounting subsystem.

## Technology

| Area | Technologies |
| --- | --- |
| Backend | Python, Django 6.1.1, Django REST Framework 3.18.1 |
| Database | PostgreSQL, using `psycopg2-binary` |
| Frontend | Vue 3, Vite, Vue Router, Pinia, Axios |
| Other interface | Django templates, HTML, CSS, Bootstrap |
| Authentication | Django authentication with session-based sign-in |

The repository does not pin a Python version. The frontend package requires Node.js `^22.18.0` or `>=24.12.0`.

## Application routes

The Vue client uses the following Django API routes:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/login/` | Sign in and establish a Django session |
| `GET` | `/api/csrf/` | Obtain the CSRF cookie used by the client |
| `GET` | `/api/teller/session/` | Check the signed-in Teller session |
| `GET` | `/api/teller/transactions/` | Get the Teller's transaction history |
| `GET` | `/api/admin/session/` | Check the signed-in Admin session |
| `GET` | `/api/admin/customers/` | Get a paginated, searchable customer list |
| `POST` | `/api/admin/customers/` | Register a customer |
| `GET` | `/api/admin/branches/options/` | Get active branches for Admin forms |
| `POST` | `/api/transactions/deposit/` | Submit a deposit request |
| `POST` | `/api/transactions/withdraw/` | Submit a withdrawal request |
| `POST` | `/api/transactions/transfer/` | Submit a transfer request |
| `GET` | `/api/manager/session/` | Check the signed-in Manager session |
| `GET` | `/api/manager/pending-transactions/` | Get pending requests for the Manager view |
| `POST` | `/api/manager/transactions/<id>/approve/` | Approve a pending request |
| `POST` | `/api/manager/transactions/<id>/reject/` | Reject a pending request |

The Django URL configuration also includes `/api/transactions/<id>/approve/` and `/api/transactions/<id>/reject/` endpoints.

The Admin customer-list endpoint accepts optional `page` and `search` query parameters. Search is case-insensitive across customer name, CIF number, district, and home branch, and is limited to 100 characters. Invalid page values fall back to the first page, while pages beyond the result range return the last page. The endpoint returns only the internal customer ID, name, customer type, KYC status, customer status, home branch name, and creation timestamp; contact and government identity details are not included.

Example response:

```json
{
  "success": true,
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_pages": 1,
    "total_items": 1,
    "has_next": false,
    "has_previous": false
  },
  "customers": [
    {
      "id": 42,
      "full_name": "Example Customer",
      "customer_type": "INDIVIDUAL",
      "kyc_status": "VERIFIED",
      "status": "ACTIVE",
      "home_branch": "Dhaka Main Branch",
      "created_at": "2026-10-21T12:00:00+00:00"
    }
  ]
}
```

Customer registration requires an active session belonging directly to the Admin group, with no conflicting banking-role group membership, and a valid CSRF token. Send `Content-Type: application/json`. Only the fields below are accepted; CIF, creator, KYC/risk/customer status, and timestamps are assigned by the server.

```json
{
  "customer_type": "INDIVIDUAL",
  "full_name": "Example Individual",
  "phone": "DEMO-PHONE",
  "email": "example@example.invalid",
  "date_of_birth": "1990-01-15",
  "gender": "OTHER",
  "nid_number": "DEMO-NID-001",
  "passport_number": "",
  "present_address": "Example address",
  "permanent_address": "",
  "district": "Example District",
  "home_branch": 1,
  "nominee_name": "",
  "nominee_relationship": "",
  "nominee_phone": ""
}
```

`customer_type` may be `INDIVIDUAL` or `ORGANIZATION`; gender may be `MALE`, `FEMALE`, or `OTHER`. An individual must provide a unique NID or passport number; an organization may omit both. The branch must exist and be active. Optional identity strings that are empty are normalized to null. The API returns `201 Created` with only a safe confirmation:

```json
{
  "success": true,
  "customer": {
    "id": 42,
    "cif_number": "CIF00000042",
    "full_name": "Example Individual",
    "home_branch": "Example Branch",
    "kyc_status": "PENDING"
  }
}
```

Validation failures return `400` with `success: false`, a safe message, and optional field-keyed generic errors. Duplicate-record conflicts return `409`; oversized bodies return `413`; audit-write failures return a generic `500`. Error responses and audit descriptions do not include submitted identity-document values.

The branch-options endpoint uses the same Admin authorization policy and returns only active branches, ordered by branch code:

```json
{
  "success": true,
  "branches": [
    {
      "id": 1,
      "branch_code": "BR001",
      "branch_name": "Example Branch"
    }
  ]
}
```

## Local setup on Windows

### Prerequisites

- Python and pip, with a Python version compatible with the pinned Django release.
- PostgreSQL installed and running locally.
- Node.js and npm meeting the frontend version requirement above.

### 1. Configure PostgreSQL and the backend

From the repository root, open PowerShell and create a Python virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a local PostgreSQL database using pgAdmin or another PostgreSQL administration tool. Copy the environment template and edit the local copy:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set the database name, username, password, host, and port in `.env` to match your local PostgreSQL setup. Set a local Django `SECRET_KEY` as well. The settings read these values from the environment; `.env` is ignored by Git. Never put actual credentials or secrets in this README or commit them.

Apply the database migrations:

```powershell
python manage.py migrate
```

Optionally create a local Django administrator account:

```powershell
python manage.py createsuperuser
```

There are no shared demo credentials. To exercise the role workflows, prepare local users, role groups, staff profiles, branches, and account data in the application.

Start the backend from the repository root:

```powershell
python manage.py runserver
```

The Django development server is available at <http://localhost:8000/>.

### 2. Install and start the Vue client

In a second PowerShell terminal, from the repository root:

```powershell
Set-Location .\frontend
npm ci
npm run dev
```

Vite serves the client at <http://localhost:5173/>. The client is configured to call the Django API at `http://localhost:8000/api`.

## Tests and production build

With the virtual environment activated and PostgreSQL running, run the backend test suite from the repository root:

```powershell
python manage.py test
```

The frontend package does not define a test script. To build its production assets, run from `frontend`:

```powershell
npm run build
```

## Known limitations and security precautions

- This is an internship prototype, not a production banking system. Do not process real funds or use real customer, account, or credential data.
- The checked-in Django settings default to `DEBUG=True` and a permissive `ALLOWED_HOSTS` value. These are development defaults, not production safeguards. No production deployment configuration or security certification is provided.
- Keep `.env` and all other secret-bearing files out of Git. Do not hard-code credentials, passwords, or secret keys. Use local demonstration credentials only.
- Audit records cover the implemented transaction initiation and Manager decision actions; this is not a claim of comprehensive audit coverage.
- The Auditor dashboard's reporting options are placeholders. Full Auditor transaction review, activity reporting, and reconciliation workflows are not implemented.
- The code does not provide a complete general ledger or a verified transaction reversal workflow. A `REVERSED` status value exists, but that alone does not implement reversal processing.
- The Vue client and Django-rendered dashboards are prototype interfaces. Their presence does not imply complete banking operations, deployment hardening, or regulatory compliance.

## Screenshots

### Landing page

![Agrani CBS landing page](docs/screenshots/landing-page.png)

### Login modal

![Agrani CBS login modal](docs/screenshots/login-modal.png)

### Manager dashboard

![Agrani CBS Manager dashboard](docs/screenshots/manager-dashboard.png)

### Teller dashboard

![Agrani CBS Teller dashboard](docs/screenshots/teller-dashboard.png)
