from django.urls import path

from .views import (
    login_api,
    csrf_api,
    manager_session_api,
    manager_pending_transactions_api,
    manager_approve_transaction_api,
    manager_reject_transaction_api,
)

urlpatterns = [
    path(
        'login/',
        login_api,
        name='login_api'
    ),

    path(
        'csrf/',
        csrf_api,
        name='csrf_api'
    ),

    path(
        'manager/session/',
        manager_session_api,
        name='manager_session_api'
    ),
    path(
        'manager/pending-transactions/',
        manager_pending_transactions_api,
        name='manager_pending_transactions_api'
    ),
    path(
        'manager/transactions/<int:transaction_id>/approve/',
        manager_approve_transaction_api,
        name='manager_approve_transaction_api'
    ),
    path(
        'manager/transactions/<int:transaction_id>/reject/',
        manager_reject_transaction_api,
        name='manager_reject_transaction_api'
    ),
]