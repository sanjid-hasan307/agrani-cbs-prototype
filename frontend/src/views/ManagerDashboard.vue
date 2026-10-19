<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../services/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const verifying = ref(true)
const authorized = ref(false)
const username = ref('')
const branchName = ref('')
const loading = ref(false)
const error = ref('')
const actionError = ref('')
const actionMessage = ref('')
const actionDialog = ref(null)
const actionInProgress = ref(false)
const transactions = ref([])
const pendingCount = ref(0)
const pagination = ref({
  page: 1,
  totalPages: 1,
  hasPrevious: false,
  hasNext: false
})
const accountNumberFilter = ref('')
const transactionTypeFilter = ref('')

const amountFormatter = new Intl.NumberFormat('en-BD', {
  style: 'currency',
  currency: 'BDT',
  currencyDisplay: 'code',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})

const dateFormatter = new Intl.DateTimeFormat('en-BD', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Dhaka'
})

function formatAmount(amount) {
  return amountFormatter.format(Number(amount))
}

function formatDate(date) {
  return dateFormatter.format(new Date(date))
}

function handleAuthorizationError(status) {
  if (status === 401 || status === 403) {
    authorized.value = false
    transactions.value = []
    pendingCount.value = 0
    username.value = ''
    actionDialog.value = null
    actionError.value = ''
    actionMessage.value = ''
    router.replace('/login')
    return true
  }

  return false
}

async function loadTransactions(page = 1) {
  loading.value = true
  error.value = ''

  const params = { page }
  const accountNumber = accountNumberFilter.value.trim()

  if (accountNumber) {
    params.account_number = accountNumber
  }
  if (transactionTypeFilter.value) {
    params.transaction_type = transactionTypeFilter.value
  }

  try {
    const response = await api.get('/manager/pending-transactions/', { params })
    transactions.value = response.data.transactions
    pendingCount.value = response.data.pending_count
    pagination.value = {
      page: response.data.pagination.page,
      totalPages: response.data.pagination.total_pages,
      hasPrevious: response.data.pagination.has_previous,
      hasNext: response.data.pagination.has_next
    }
  } catch (requestError) {
    transactions.value = []
    pendingCount.value = 0

    const status = requestError.response?.status
    if (!handleAuthorizationError(status)) {
      error.value = 'Unable to load pending transactions. Please try again.'
    }
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  actionMessage.value = ''
  loadTransactions(1)
}

function clearFilters() {
  accountNumberFilter.value = ''
  transactionTypeFilter.value = ''
  actionMessage.value = ''
  loadTransactions(1)
}

function openActionDialog(transaction, action) {
  if (actionInProgress.value || transaction.created_by === username.value) {
    return
  }

  actionError.value = ''
  actionMessage.value = ''
  actionDialog.value = {
    transaction,
    action,
    reason: ''
  }
}

async function submitTransactionAction() {
  const pendingAction = actionDialog.value
  if (!pendingAction || actionInProgress.value) {
    return
  }

  actionInProgress.value = true
  actionError.value = ''
  const endpoint = `/manager/transactions/${pendingAction.transaction.id}/${pendingAction.action}/`

  try {
    const response = pendingAction.action === 'reject'
      ? await api.post(endpoint, { reason: pendingAction.reason.trim() })
      : await api.post(endpoint)

    if (!response.data.success) {
      actionError.value = response.data.message || 'The transaction action could not be completed.'
      return
    }

    const pastAction = pendingAction.action === 'approve' ? 'approved' : 'rejected'
    actionMessage.value = response.data.message || `Transaction ${pastAction} successfully.`
    actionDialog.value = null
    await loadTransactions(pagination.value.page)
  } catch (requestError) {
    const status = requestError.response?.status
    if (handleAuthorizationError(status)) {
      return
    }

    const responseMessage = requestError.response?.data?.message
    actionError.value = typeof responseMessage === 'string'
      ? responseMessage
      : `Unable to ${pendingAction.action} this transaction. Please try again.`
  } finally {
    actionInProgress.value = false
  }
}

onMounted(async () => {
  try {
    const response = await api.get('/manager/session/')

    if (response.data.success && response.data.role === 'Manager') {
      authorized.value = true
      username.value = response.data.username
      branchName.value = authStore.branch || ''
      await loadTransactions(1)
    } else {
      router.replace('/login')
    }
  } catch (sessionError) {
    const status = sessionError.response?.status
    if (!handleAuthorizationError(status)) {
      error.value = 'Unable to verify your session. Please try again.'
    }
  } finally {
    verifying.value = false
  }
})
</script>

<template>
  <section class="manager-dashboard">
    <div v-if="verifying" class="state-card" role="status">
      <span class="spinner" aria-hidden="true"></span>
      Verifying your Manager session...
    </div>

    <div v-else-if="authorized" class="dashboard-content">
      <div class="page-heading">
        <div>
          <h1>Welcome, {{ username }}</h1>
          <p class="welcome">Role: <strong>Branch Manager</strong></p>
        </div>
      </div>

      <div class="overview-grid">
        <section class="branch-card" aria-labelledby="branch-heading">
          <h2 id="branch-heading" class="card-heading">Branch Information</h2>
          <div v-if="branchName" class="branch-details">
            <div>
              <span>Branch Code</span>
              <strong>Not provided</strong>
            </div>
            <div>
              <span>Branch Name</span>
              <strong>{{ branchName }}</strong>
            </div>
            <div>
              <span>District</span>
              <strong>Not provided</strong>
            </div>
          </div>
          <p v-else class="branch-unavailable">
            No branch assigned or branch information is unavailable.
          </p>
          <p v-if="branchName" class="branch-note">
            Branch code and district are not included in the current Manager session data.
          </p>
        </section>

        <div class="summary-card" aria-live="polite">
          <div class="summary-icon" aria-hidden="true">⌛</div>
          <div>
            <p class="summary-label">Pending Authorizations</p>
            <p class="summary-count">{{ pendingCount }}</p>
          </div>
          <span class="summary-caption">Awaiting review</span>
        </div>
      </div>

      <section class="transactions-card" aria-labelledby="pending-heading">
        <div class="section-heading">
          <div>
            <h2 id="pending-heading">Pending Transactions for Approval</h2>
          </div>
          <span class="queue-count">{{ pendingCount }} pending</span>
        </div>

        <form class="filters" @submit.prevent="applyFilters">
          <label class="filter-field">
            <span>Account number</span>
            <input
              v-model="accountNumberFilter"
              type="search"
              name="account_number"
              placeholder="Search account number"
              autocomplete="off"
            >
          </label>

          <label class="filter-field">
            <span>Transaction type</span>
            <select v-model="transactionTypeFilter" name="transaction_type">
              <option value="">All transaction types</option>
              <option value="DEPOSIT">Deposit</option>
              <option value="WITHDRAWAL">Withdrawal</option>
              <option value="TRANSFER">Transfer</option>
            </select>
          </label>

          <div class="filter-actions">
            <button class="button button-primary" type="submit" :disabled="loading">
              Apply filters
            </button>
            <button class="button button-secondary" type="button" :disabled="loading" @click="clearFilters">
              Clear
            </button>
          </div>
        </form>

        <div v-if="actionMessage" class="state-card success-card" role="status">
          {{ actionMessage }}
        </div>
        <div v-if="actionError && !actionDialog" class="state-card error-card action-error" role="alert">
          {{ actionError }}
        </div>
        <div v-if="error" class="state-card error-card" role="alert">
          <p>{{ error }}</p>
          <button
            v-if="authorized"
            class="button button-secondary"
            type="button"
            :disabled="loading"
            @click="loadTransactions(pagination.page)"
          >
            Try again
          </button>
        </div>
        <div v-else-if="loading" class="state-card" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading pending transactions...
        </div>
        <div v-else-if="transactions.length === 0" class="state-card empty-card">
          <strong>No pending transactions found</strong>
          <span>Try changing or clearing your search filters.</span>
        </div>
        <template v-else>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Transaction ID</th>
                  <th scope="col">Transaction Type</th>
                  <th scope="col">Account Number</th>
                  <th scope="col" class="amount-cell">Amount (BDT)</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created By</th>
                  <th scope="col">Created At</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="transaction in transactions" :key="transaction.transaction_id">
                  <td class="transaction-id">{{ transaction.transaction_id }}</td>
                  <td>{{ transaction.transaction_type }}</td>
                  <td class="account-number">{{ transaction.account_number }}</td>
                  <td class="amount-cell">{{ formatAmount(transaction.amount) }}</td>
                  <td>
                    <span class="status-badge">{{ transaction.status }}</span>
                  </td>
                  <td>{{ transaction.created_by }}</td>
                  <td class="date-cell">{{ formatDate(transaction.created_at) }}</td>
                  <td class="action-cell">
                    <div class="row-actions">
                      <button
                        class="button button-primary action-button"
                        type="button"
                        :disabled="actionInProgress || transaction.created_by === username"
                        :title="transaction.created_by === username ? 'Makers cannot authorize their own transactions.' : 'Approve transaction'"
                        @click="openActionDialog(transaction, 'approve')"
                      >
                        Approve
                      </button>
                      <button
                        class="button button-danger action-button"
                        type="button"
                        :disabled="actionInProgress || transaction.created_by === username"
                        :title="transaction.created_by === username ? 'Makers cannot authorize their own transactions.' : 'Reject transaction'"
                        @click="openActionDialog(transaction, 'reject')"
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <nav class="pagination" aria-label="Pending transaction pages">
            <span class="page-summary">
              Page {{ pagination.page }} of {{ pagination.totalPages }}
            </span>
            <div class="page-controls">
              <button
                class="button button-secondary"
                type="button"
                :disabled="loading || !pagination.hasPrevious"
                @click="loadTransactions(pagination.page - 1)"
              >
                Previous
              </button>
              <button
                class="button button-secondary"
                type="button"
                :disabled="loading || !pagination.hasNext"
                @click="loadTransactions(pagination.page + 1)"
              >
                Next
              </button>
            </div>
          </nav>
        </template>
      </section>
    </div>

    <div
      v-if="actionDialog"
      class="dialog-backdrop"
      role="presentation"
      @click.self="!actionInProgress && (actionDialog = null)"
    >
      <section
        class="action-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="action-dialog-heading"
        :aria-busy="actionInProgress"
      >
        <p class="eyebrow">Transaction Authorization</p>
        <h2 id="action-dialog-heading">
          {{ actionDialog.action === 'approve' ? 'Confirm approval' : 'Confirm rejection' }}
        </h2>
        <p class="dialog-description">
          Are you sure you want to {{ actionDialog.action }} this transaction?
        </p>
        <div v-if="actionError" class="state-card error-card dialog-error" role="alert">
          {{ actionError }}
        </div>
        <dl class="transaction-summary">
          <div>
            <dt>Transaction ID</dt>
            <dd>{{ actionDialog.transaction.transaction_id }}</dd>
          </div>
          <div>
            <dt>Type</dt>
            <dd>{{ actionDialog.transaction.transaction_type }}</dd>
          </div>
          <div>
            <dt>Amount</dt>
            <dd>{{ formatAmount(actionDialog.transaction.amount) }}</dd>
          </div>
        </dl>
        <label v-if="actionDialog.action === 'reject'" class="filter-field reason-field">
          <span>Reason (optional)</span>
          <textarea
            v-model="actionDialog.reason"
            name="rejection_reason"
            maxlength="500"
            rows="3"
            placeholder="Enter a reason for rejecting this transaction"
            :disabled="actionInProgress"
          ></textarea>
        </label>
        <div class="dialog-actions">
          <button
            class="button button-secondary"
            type="button"
            :disabled="actionInProgress"
            @click="actionDialog = null"
          >
            Cancel
          </button>
          <button
            class="button"
            :class="actionDialog.action === 'approve' ? 'button-primary' : 'button-danger'"
            type="button"
            :disabled="actionInProgress"
            @click="submitTransactionAction"
          >
            {{ actionInProgress ? 'Submitting...' : actionDialog.action === 'approve' ? 'Confirm approval' : 'Confirm rejection' }}
          </button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.manager-dashboard {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 24px clamp(16px, 4vw, 40px) 40px;
  color: #243449;
}

.dashboard-content {
  display: grid;
  gap: 16px;
}

.page-heading,
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.page-heading h1,
.section-heading h2 {
  margin: 0;
  color: #123b68;
  font-weight: 700;
  letter-spacing: -0.025em;
}

.page-heading h1 {
  font-size: clamp(1.25rem, 2vw, 1.5rem);
}

.page-heading {
  margin-bottom: 2px;
}

.welcome {
  margin: 4px 0 0;
  color: #62738a;
  font-size: .85rem;
}

.welcome strong {
  color: #243449;
}

.eyebrow {
  margin: 0 0 5px;
  color: #708198;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
  gap: 16px;
}

.branch-card,
.summary-card,
.transactions-card {
  border-radius: 12px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 7%);
}

.branch-card {
  min-width: 0;
  padding: 18px 20px;
  background: #fff;
}

.card-heading {
  margin: 0 0 14px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e2e8f0;
  color: #334155;
  font-size: .95rem;
  font-weight: 600;
}

.branch-details {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.branch-details div {
  display: grid;
  gap: 3px;
}

.branch-details span,
.branch-note,
.branch-unavailable {
  color: #64748b;
  font-size: .76rem;
}

.branch-details strong {
  color: #26364a;
  font-size: .88rem;
  overflow-wrap: anywhere;
}

.branch-note {
  margin: 10px 0 0;
}

.branch-unavailable {
  margin: 0;
}

.summary-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 112px;
  padding: 18px;
  overflow: hidden;
  border-radius: 12px;
  background: linear-gradient(135deg, #f59e0b, #d97706);
  box-shadow: 0 4px 16px rgb(0 0 0 / 7%);
  color: #fff;
}

.summary-icon {
  display: grid;
  width: 46px;
  height: 46px;
  flex-shrink: 0;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 25%);
  border-radius: 12px;
  background: rgb(255 255 255 / 12%);
  font-size: 1.45rem;
  font-weight: 700;
}

.summary-label {
  margin: 0;
  color: rgb(255 255 255 / 80%);
  font-size: 0.78rem;
}

.summary-count {
  margin: 2px 0 0;
  font-size: 1.8rem;
  font-weight: 700;
  line-height: 1.15;
}

.summary-caption {
  margin-left: auto;
  align-self: center;
  color: rgb(255 255 255 / 76%);
  font-size: 0.72rem;
  text-align: right;
}

.transactions-card {
  min-width: 0;
  padding: 18px;
  border: 0;
  border-radius: 12px;
  background: #fff;
}

.section-heading {
  margin-bottom: 14px;
}

.section-heading h2 {
  color: #334155;
  font-size: .98rem;
  font-weight: 600;
}

.queue-count {
  padding: 7px 11px;
  border-radius: 999px;
  background: #fff5df;
  color: #875900;
  font-size: 0.78rem;
  font-weight: 700;
  white-space: nowrap;
}

.filters {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px;
  border: 0;
  border-radius: 7px;
  background: #f8f9fb;
}

.filter-field {
  display: grid;
  flex: 1 1 230px;
  gap: 4px;
  color: #53657b;
  font-size: 0.75rem;
  font-weight: 600;
}

.filter-field input,
.filter-field select {
  width: 100%;
  min-height: 34px;
  padding: 6px 9px;
  border: 1px solid #cfd8e3;
  border-radius: 6px;
  background: #fff;
  color: #25364a;
  font: inherit;
}

.filter-field input:focus,
.filter-field select:focus {
  border-color: #2874b9;
  outline: 3px solid rgb(40 116 185 / 15%);
}

.filter-actions,
.page-controls {
  display: flex;
  gap: 8px;
}

.button {
  min-height: 34px;
  padding: 6px 11px;
  border: 1px solid transparent;
  border-radius: 6px;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.button-primary {
  background: #0d6efd;
  color: #fff;
}

.button-primary:hover:not(:disabled) {
  background: #0a58ca;
}

.button-secondary {
  border-color: #cfd8e3;
  background: #fff;
  color: #3c5068;
}

.button-secondary:hover:not(:disabled) {
  background: #f1f5f9;
}

.button-danger {
  background: #dc3545;
  color: #fff;
}

.button-danger:hover:not(:disabled) {
  background: #bb2d3b;
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
  border: 0;
  border-radius: 8px;
}

table {
  width: 100%;
  min-width: 980px;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.78rem;
}

th {
  padding: 9px 10px;
  background: #f1f3f5;
  color: #53657b;
  font-size: 0.7rem;
  font-weight: 700;
  white-space: nowrap;
}

td {
  padding: 9px 10px;
  border-top: 1px solid #edf0f4;
  color: #33465d;
  white-space: nowrap;
}

tbody tr:hover {
  background: #f9fbfd;
}

.transaction-id {
  color: #173f6d;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 600;
}

.account-number {
  font-weight: 600;
}

.amount-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.status-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 999px;
  background: #fff5df;
  color: #875900;
  font-size: 0.68rem;
  font-weight: 700;
}

.date-cell {
  color: #5e7086;
}

.action-cell {
  white-space: normal;
}

.row-actions {
  display: flex;
  gap: 7px;
}

.action-button {
  min-height: 34px;
  padding: 6px 10px;
  font-size: 0.75rem;
}

.action-error {
  margin-bottom: 16px;
}

.dialog-error {
  min-height: 0;
  justify-content: flex-start;
  margin-bottom: 14px;
  text-align: left;
}

.success-card {
  margin-bottom: 16px;
  border-color: #cfe5d8;
  background: #f3faf6;
  color: #28734c;
}

.dialog-backdrop {
  position: fixed;
  z-index: 10;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgb(15 31 49 / 52%);
}

.action-dialog {
  width: min(100%, 480px);
  padding: 26px;
  border: 1px solid #e5eaf0;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 18px 55px rgb(10 30 52 / 25%);
}

.action-dialog h2 {
  margin: 0;
  color: #123b68;
  font-size: 1.3rem;
}

.dialog-description {
  margin: 10px 0 18px;
  color: #62738a;
}

.transaction-summary {
  display: grid;
  gap: 10px;
  margin: 0 0 18px;
  padding: 14px;
  border: 1px solid #e8edf2;
  border-radius: 8px;
  background: #f8fafc;
}

.transaction-summary div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.transaction-summary dt {
  color: #64758b;
  font-size: 0.82rem;
}

.transaction-summary dd {
  margin: 0;
  color: #243449;
  font-size: 0.84rem;
  font-weight: 600;
  text-align: right;
}

.reason-field {
  margin-bottom: 18px;
}

.reason-field textarea {
  width: 100%;
  min-height: 84px;
  padding: 9px 11px;
  border: 1px solid #cfd8e3;
  border-radius: 6px;
  color: #25364a;
  font: inherit;
  resize: vertical;
}

.reason-field textarea:focus {
  border-color: #2874b9;
  outline: 3px solid rgb(40 116 185 / 15%);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 9px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 12px;
}

.page-summary {
  color: #64758b;
  font-size: 0.82rem;
}

.state-card {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 11px;
  min-height: 104px;
  padding: 20px;
  border: 1px dashed #d7e0e9;
  border-radius: 8px;
  color: #53657b;
  text-align: center;
}

.empty-card {
  flex-direction: column;
  gap: 5px;
  border-style: solid;
  background: #fbfcfd;
}

.empty-card strong {
  color: #344961;
}

.empty-card span {
  font-size: 0.85rem;
}

.error-card {
  flex-wrap: wrap;
  border-color: #f0c8c4;
  background: #fff8f7;
  color: #a12e24;
}

.error-card p {
  margin: 0;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #d5e2ef;
  border-top-color: #07509a;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 700px) {
  .manager-dashboard {
    padding-top: 18px;
  }

  .page-heading,
  .section-heading {
    align-items: flex-start;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .summary-card {
    min-height: 92px;
  }

  .filters {
    align-items: stretch;
    flex-direction: column;
  }

  .filter-actions {
    width: 100%;
  }

  .filter-actions .button {
    flex: 1;
  }
}

@media (max-width: 420px) {
  .branch-card,
  .transactions-card {
    padding: 14px;
  }

  .branch-details {
    grid-template-columns: 1fr;
  }

  .summary-card {
    padding: 14px;
  }

  .summary-caption {
    display: none;
  }

  .queue-count {
    font-size: 0.7rem;
  }

  .pagination {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
