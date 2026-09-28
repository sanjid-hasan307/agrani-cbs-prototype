from django.urls import path
from users.views import login_view, logout_view
from users.dashboard_views import (
    manager_dashboard,
    manager_approve_transaction,
    manager_reject_transaction,
    teller_dashboard,
    auditor_dashboard,
)

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/manager/', manager_dashboard, name='dashboard_manager'),
    path('dashboard/manager/approve/<int:transaction_id>/', manager_approve_transaction, name='manager_approve_transaction'),
    path('dashboard/manager/reject/<int:transaction_id>/', manager_reject_transaction, name='manager_reject_transaction'),
    path('dashboard/teller/', teller_dashboard, name='dashboard_teller'),
    path('dashboard/auditor/', auditor_dashboard, name='dashboard_auditor'),
]
