from django.urls import path
from users.views import login_view, logout_view
from users.dashboard_views import manager_dashboard, teller_dashboard, auditor_dashboard

urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/manager/', manager_dashboard, name='dashboard_manager'),
    path('dashboard/teller/', teller_dashboard, name='dashboard_teller'),
    path('dashboard/auditor/', auditor_dashboard, name='dashboard_auditor'),
]
