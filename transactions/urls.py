from django.urls import path
from transactions.views import (
    DepositAPIView,
    WithdrawAPIView,
    TransferAPIView,
    ApproveTransactionAPIView,
    RejectTransactionAPIView,
)

app_name = 'transactions'

urlpatterns = [
    path('deposit/', DepositAPIView.as_view(), name='deposit-api'),
    path('withdraw/', WithdrawAPIView.as_view(), name='withdraw-api'),
    path('transfer/', TransferAPIView.as_view(), name='transfer-api'),
    path('<int:pk>/approve/', ApproveTransactionAPIView.as_view(), name='approve-api'),
    path('<int:pk>/reject/', RejectTransactionAPIView.as_view(), name='reject-api'),
]
