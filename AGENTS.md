# Core Banking System Project Rules

## Project
Core Banking System Prototype for Internship Project

## Technology Stack
- Python
- Django
- Django REST Framework
- PostgreSQL
- HTML
- CSS
- Bootstrap
- JavaScript

## Architecture Rules
- Use modular Django apps.
- Keep business logic separate from views where practical.
- Use PostgreSQL as the database.
- Never use Python float for monetary values.
- Always use Decimal for money.
- Financial operations must use database transactions.
- Do not update account balances without recording a transaction.
- Use atomic transactions for deposit, withdrawal, and fund transfer.
- Use select_for_update() where concurrent balance updates are possible.
- Implement maker-checker authorization.
- Maintain audit logs for sensitive actions.
- Use role-based access control.
- Never store passwords in plain text.
- Never hard-code secrets or database passwords.
- Use environment variables for secrets.
- Posted financial transactions must never be deleted.
- Wrong posted transactions must be reversed using reversal entries.
- Debit and credit entries must always balance.

## Development Rules
- Build one module at a time.
- Do not modify unrelated working modules.
- Add tests for every major feature.
- Run tests after each major change.
- Run Django system checks after configuration changes.
- Explain major architectural assumptions.
- Keep the project simple, clean, and maintainable.
- Do not add unnecessary technologies without approval.
