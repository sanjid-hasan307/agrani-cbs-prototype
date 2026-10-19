<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../services/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const verifying = ref(true)
const authorized = ref(false)
const username = ref('')
const branch = ref('')
const loadingHistory = ref(false)
const historyError = ref('')
const transactions = ref([])
const pagination = ref({
  page: 1,
  totalPages: 1,
  totalItems: 0,
  hasPrevious: false,
  hasNext: false
})
const filters = reactive({
  account_number: '',
  transaction_type: '',
  status: ''
})
const activeRequest = ref('')
const operationMessage = ref('')
const operationError = ref('')
const forms = reactive({
  deposit: { account_number: '', amount: '', description: '' },
  withdrawal: { account_number: '', amount: '', description: '' },
  transfer: {
    from_account_number: '',
    to_account_number: '',
    amount: '',
    description: ''
  }
})

const dateFormatter = new Intl.DateTimeFormat('en-BD', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Dhaka'
})

const amountFormatter = new Intl.NumberFormat('en-BD', {
  style: 'currency',
  currency: 'BDT',
  currencyDisplay: 'code',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})

function formatAmount(amount) {
  return amountFormatter.format(Number(amount))
}

function formatDate(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateFormatter.format(date)
}

function flattenErrors(value) {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(flattenErrors)
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, messages]) =>
      flattenErrors(messages).map(message => `${key}: ${message}`)
    )
  }
  return []
}

function getErrorMessage(error, fallback) {
  const data = error.response?.data
  const messages = [
    ...flattenErrors(data?.message),
    ...flattenErrors(data?.errors),
    ...flattenErrors(data?.detail)
  ]
  return messages.length ? messages.join(' ') : fallback
}

function clearSensitiveData() {
  authorized.value = false
  username.value = ''
  branch.value = ''
  transactions.value = []
  filters.account_number = ''
  filters.transaction_type = ''
  filters.status = ''
  clearForm(forms.deposit)
  clearForm(forms.withdrawal)
  clearForm(forms.transfer)
  pagination.value = {
    page: 1,
    totalPages: 1,
    totalItems: 0,
    hasPrevious: false,
    hasNext: false
  }
  operationMessage.value = ''
  operationError.value = ''
  historyError.value = ''
  authStore.logout()
}

function handleAuthorizationError(status) {
  if (status !== 401 && status !== 403) return false

  clearSensitiveData()
  router.replace('/login')
  return true
}

async function loadTransactions(page = 1) {
  loadingHistory.value = true
  historyError.value = ''
  const params = { page }

  for (const [key, value] of Object.entries(filters)) {
    const trimmedValue = value.trim()
    if (trimmedValue) params[key] = trimmedValue
  }

  try {
    const response = await api.get('/teller/transactions/', { params })
    transactions.value = response.data.transactions
    pagination.value = {
      page: response.data.pagination.page,
      totalPages: response.data.pagination.total_pages,
      totalItems: response.data.pagination.total_items,
      hasPrevious: response.data.pagination.has_previous,
      hasNext: response.data.pagination.has_next
    }
  } catch (error) {
    transactions.value = []
    if (!handleAuthorizationError(error.response?.status)) {
      historyError.value = getErrorMessage(
        error,
        'Unable to load transaction history. Please try again.'
      )
    }
  } finally {
    loadingHistory.value = false
  }
}

function applyFilters() {
  operationMessage.value = ''
  loadTransactions(1)
}

function clearFilters() {
  filters.account_number = ''
  filters.transaction_type = ''
  filters.status = ''
  applyFilters()
}

function clearForm(form) {
  for (const key of Object.keys(form)) form[key] = ''
}

async function submitOperation(type, endpoint, form, payload) {
  if (activeRequest.value) return

  activeRequest.value = type
  operationMessage.value = ''
  operationError.value = ''
  historyError.value = ''

  try {
    const response = await api.post(endpoint, payload)
    if (!response.data.success) {
      operationError.value = response.data.message || `${type} request could not be submitted.`
      return
    }

    operationMessage.value = `${response.data.message} Transaction ${response.data.transaction_id} is PENDING. Account balances are unchanged until Manager approval.`
    clearForm(form)
    await loadTransactions(1)
  } catch (error) {
    if (!handleAuthorizationError(error.response?.status)) {
      operationError.value = getErrorMessage(
        error,
        `Unable to submit ${type.toLowerCase()} request. Please try again.`
      )
    }
  } finally {
    activeRequest.value = ''
  }
}

function submitDeposit() {
  return submitOperation(
    'Deposit',
    '/transactions/deposit/',
    forms.deposit,
    { ...forms.deposit }
  )
}

function submitWithdrawal() {
  return submitOperation(
    'Withdrawal',
    '/transactions/withdraw/',
    forms.withdrawal,
    { ...forms.withdrawal }
  )
}

function submitTransfer() {
  return submitOperation(
    'Transfer',
    '/transactions/transfer/',
    forms.transfer,
    { ...forms.transfer }
  )
}

onMounted(async () => {
  try {
    const response = await api.get('/teller/session/')
    if (!response.data.success || response.data.role !== 'Teller') {
      clearSensitiveData()
      await router.replace('/login')
      return
    }

    authorized.value = true
    username.value = response.data.username
    branch.value = response.data.branch || ''
    await loadTransactions(1)
  } catch (error) {
    if (!handleAuthorizationError(error.response?.status)) {
      historyError.value = getErrorMessage(
        error,
        'Unable to verify your Teller session. Please try again.'
      )
    }
  } finally {
    verifying.value = false
  }
})
</script>

<template>
  <section class="teller-dashboard">
    <div v-if="verifying" class="state-card" role="status">
      <span class="spinner" aria-hidden="true"></span>
      Verifying your Teller session...
    </div>

    <div v-else-if="authorized" class="dashboard-content">
      <header class="page-heading">
        <div>
          <h1>Welcome, {{ username }}</h1>
          <p class="welcome">
            Role: <strong>Teller</strong>
          </p>
        </div>
      </header>

      <section class="branch-card" aria-labelledby="branch-heading">
        <h2 id="branch-heading" class="card-heading">Branch Information</h2>
        <div v-if="branch" class="branch-details">
          <div>
            <span>Branch Code</span>
            <strong>Not provided</strong>
          </div>
          <div>
            <span>Branch Name</span>
            <strong>{{ branch }}</strong>
          </div>
          <div>
            <span>District</span>
            <strong>Not provided</strong>
          </div>
        </div>
        <p v-else class="branch-unavailable">No branch information available.</p>
        <p v-if="branch" class="branch-note">
          Branch code and district are not included in the current Teller session data.
        </p>
      </section>

      <div class="notice" role="note">
        <strong>Maker-checker notice:</strong> Successful requests create transactions in
        <strong>PENDING</strong> status. Account balances do not change until a Manager approves
        the request.
      </div>

      <section class="operations-section" aria-labelledby="operations-heading">
        <div class="section-heading">
          <div>
            <h2 id="operations-heading">Available Transaction Actions</h2>
          </div>
        </div>

        <div v-if="operationMessage" class="alert success" role="status" aria-live="polite">
          {{ operationMessage }}
        </div>
        <div v-if="operationError" class="alert failure" role="alert" aria-live="assertive">
          {{ operationError }}
        </div>

        <div class="form-grid">
          <form class="operation-card deposit-card" @submit.prevent="submitDeposit">
            <h3><span aria-hidden="true">▣</span> Cash Deposit</h3>
            <p class="action-description">Deposit funds into an account</p>
            <label>
              Account number
              <input
                v-model="forms.deposit.account_number"
                name="deposit-account-number"
                maxlength="20"
                required
                autocomplete="off"
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <label>
              Amount (BDT)
              <input
                v-model="forms.deposit.amount"
                name="deposit-amount"
                type="number"
                min="0.01"
                step="0.01"
                required
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <label>
              Description <span class="optional">(optional)</span>
              <input
                v-model="forms.deposit.description"
                name="deposit-description"
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <button class="button primary" type="submit" :disabled="Boolean(activeRequest)">
              {{ activeRequest === 'Deposit' ? 'Submitting...' : 'Submit deposit request' }}
            </button>
          </form>

          <form class="operation-card withdrawal-card" @submit.prevent="submitWithdrawal">
            <h3><span aria-hidden="true">↗</span> Cash Withdrawal</h3>
            <p class="action-description">Withdraw funds from an account</p>
            <label>
              Account number
              <input
                v-model="forms.withdrawal.account_number"
                name="withdraw-account-number"
                maxlength="20"
                required
                autocomplete="off"
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <label>
              Amount (BDT)
              <input
                v-model="forms.withdrawal.amount"
                name="withdraw-amount"
                type="number"
                min="0.01"
                step="0.01"
                required
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <label>
              Description <span class="optional">(optional)</span>
              <input
                v-model="forms.withdrawal.description"
                name="withdraw-description"
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <button class="button primary" type="submit" :disabled="Boolean(activeRequest)">
              {{ activeRequest === 'Withdrawal' ? 'Submitting...' : 'Submit withdrawal request' }}
            </button>
          </form>

          <form class="operation-card transfer-card" @submit.prevent="submitTransfer">
            <h3><span aria-hidden="true">⇄</span> Fund Transfer</h3>
            <p class="action-description">Transfer between accounts</p>
            <label>
              From account number
              <input
                v-model="forms.transfer.from_account_number"
                name="transfer-from-account-number"
                maxlength="20"
                required
                autocomplete="off"
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <label>
              To account number
              <input
                v-model="forms.transfer.to_account_number"
                name="transfer-to-account-number"
                maxlength="20"
                required
                autocomplete="off"
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <label>
              Amount (BDT)
              <input
                v-model="forms.transfer.amount"
                name="transfer-amount"
                type="number"
                min="0.01"
                step="0.01"
                required
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <label>
              Description <span class="optional">(optional)</span>
              <input
                v-model="forms.transfer.description"
                name="transfer-description"
                :disabled="Boolean(activeRequest)"
              />
            </label>
            <button class="button primary" type="submit" :disabled="Boolean(activeRequest)">
              {{ activeRequest === 'Transfer' ? 'Submitting...' : 'Submit transfer request' }}
            </button>
          </form>
        </div>
      </section>

      <section class="transactions-card" aria-labelledby="history-heading">
        <div class="section-heading">
          <div>
            <h2 id="history-heading">Recent Transaction History</h2>
            <p class="section-caption">{{ pagination.totalItems }} transaction(s)</p>
          </div>
          <button
            class="button secondary"
            type="button"
            :disabled="loadingHistory"
            @click="loadTransactions(pagination.page)"
          >
            {{ loadingHistory ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <form class="filter-form" @submit.prevent="applyFilters">
          <label>
            Account number
            <input v-model="filters.account_number" placeholder="Search account" />
          </label>
          <label>
            Transaction type
            <select v-model="filters.transaction_type">
              <option value="">All types</option>
              <option value="DEPOSIT">Deposit</option>
              <option value="WITHDRAWAL">Withdrawal</option>
              <option value="TRANSFER">Transfer</option>
            </select>
          </label>
          <label>
            Status
            <select v-model="filters.status">
              <option value="">All statuses</option>
              <option value="PENDING">Pending</option>
              <option value="POSTED">Posted</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
              <option value="REVERSED">Reversed</option>
            </select>
          </label>
          <div class="filter-actions">
            <button class="button primary" type="submit" :disabled="loadingHistory">
              Apply filters
            </button>
            <button class="button secondary" type="button" :disabled="loadingHistory" @click="clearFilters">
              Clear
            </button>
          </div>
        </form>

        <div v-if="historyError" class="alert failure" role="alert">
          {{ historyError }}
        </div>
        <div v-if="loadingHistory" class="state-card compact" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading transaction history...
        </div>
        <div v-else-if="transactions.length === 0" class="empty-state">
          No transactions match the selected filters.
        </div>
        <div v-else class="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Transaction ID</th>
                <th>Account number</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Authorization</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="transaction in transactions" :key="transaction.id">
                <td class="transaction-id">{{ transaction.transaction_id }}</td>
                <td>{{ transaction.account_number }}</td>
                <td>{{ transaction.transaction_type }}</td>
                <td class="amount">{{ formatAmount(transaction.amount) }}</td>
                <td><span class="badge" :class="`status-${transaction.status.toLowerCase()}`">{{ transaction.status }}</span></td>
                <td><span class="badge" :class="`status-${transaction.authorization_status.toLowerCase()}`">{{ transaction.authorization_status }}</span></td>
                <td>{{ formatDate(transaction.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <footer class="pagination">
          <span>Page {{ pagination.page }} of {{ pagination.totalPages }}</span>
          <div>
            <button
              class="button secondary"
              type="button"
              :disabled="loadingHistory || !pagination.hasPrevious"
              @click="loadTransactions(pagination.page - 1)"
            >
              Previous
            </button>
            <button
              class="button secondary"
              type="button"
              :disabled="loadingHistory || !pagination.hasNext"
              @click="loadTransactions(pagination.page + 1)"
            >
              Next
            </button>
          </div>
        </footer>
      </section>
    </div>
    <div v-else-if="historyError" class="state-card error-state" role="alert">
      {{ historyError }}
    </div>
  </section>
</template>

<style scoped>
.teller-dashboard {
  width: min(1440px, 100%);
  margin: 0 auto;
  padding: 24px clamp(16px, 4vw, 40px) 40px;
  color: #243449;
}

.dashboard-content {
  display: grid;
  gap: 16px;
}

.page-heading,
.section-heading,
.pagination,
.pagination > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-heading h1,
.section-heading h2 {
  margin: 0;
  color: #212529;
}

.page-heading h1 {
  font-size: clamp(1.25rem, 2vw, 1.5rem);
}

.section-heading h2 {
  font-size: .98rem;
  font-weight: 600;
}

.page-heading {
  margin-bottom: 2px;
}

.welcome {
  margin: 4px 0 0;
  color: #64748b;
  font-size: .85rem;
}

.branch-card,
.operations-section,
.transactions-card {
  border: 0;
  border-radius: 12px;
  padding: 18px;
  background: #fff;
  box-shadow: 0 4px 16px rgb(0 0 0 / 7%);
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

.notice {
  border: 1px solid #ffe69c;
  border-radius: 8px;
  padding: 11px 14px;
  background: #fff3cd;
  color: #664d03;
  font-size: .84rem;
  line-height: 1.5;
}

.operations-section > .section-heading,
.transactions-card > .section-heading {
  margin-bottom: 14px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-caption {
  margin: 5px 0 0;
  color: #64748b;
  font-size: .78rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.operation-card {
  display: grid;
  align-content: start;
  gap: 9px;
  border: 0;
  border-top: 4px solid #0d6efd;
  border-radius: 12px;
  padding: 16px;
  background: #fff;
  box-shadow: 0 4px 16px rgb(0 0 0 / 7%);
}

.operation-card h3 {
  margin: 0;
  color: #212529;
  font-size: .95rem;
}

.operation-card h3 span {
  margin-right: 5px;
  color: #0d6efd;
}

.deposit-card {
  border-top-color: #22c55e;
}

.deposit-card h3 span {
  color: #198754;
}

.withdrawal-card {
  border-top-color: #ef4444;
}

.withdrawal-card h3 span {
  color: #dc3545;
}

.transfer-card {
  border-top-color: #3b82f6;
}

.action-description {
  margin: -5px 0 4px;
  color: #6c757d;
  font-size: .76rem;
}

label {
  display: grid;
  gap: 4px;
  color: #53657b;
  font-size: .75rem;
  font-weight: 600;
}

input,
select {
  width: 100%;
  min-height: 34px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  padding: 6px 9px;
  background: #fff;
  color: #25364a;
  font: inherit;
  font-weight: 400;
}

input:focus,
select:focus {
  border-color: #86b7fe;
  outline: 3px solid rgb(13 110 253 / 15%);
}

input:disabled,
button:disabled {
  cursor: not-allowed;
  opacity: .65;
}

.optional {
  color: #64748b;
  font-weight: 400;
}

.button {
  min-height: 34px;
  border: 0;
  border-radius: 6px;
  padding: 6px 11px;
  font: inherit;
  font-size: .78rem;
  font-weight: 600;
  cursor: pointer;
}

.button.primary {
  background: #0d6efd;
  color: #fff;
}

.button.primary:hover:not(:disabled) {
  background: #0a58ca;
}

.button.secondary {
  border: 1px solid #ced4da;
  background: #fff;
  color: #3c5068;
}

.button.secondary:hover:not(:disabled) {
  background: #f1f3f5;
}

.alert {
  margin: 0 0 14px;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: .84rem;
  line-height: 1.5;
}

.alert.success {
  border: 1px solid #a7f3d0;
  background: #ecfdf5;
  color: #065f46;
}

.alert.failure,
.error-state {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #991b1b;
}

.filter-form {
  display: grid;
  grid-template-columns: minmax(160px, 1.2fr) repeat(2, minmax(130px, .8fr)) auto;
  align-items: end;
  gap: 9px;
  margin-bottom: 14px;
  padding: 12px;
  border-radius: 7px;
  background: #f8f9fb;
}

.filter-actions {
  display: flex;
  gap: 8px;
}

.table-wrapper {
  overflow-x: auto;
  border: 1px solid #dee2e6;
  border-radius: 7px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: .76rem;
  text-align: left;
}

th,
td {
  border-bottom: 1px solid #e2e8f0;
  padding: 8px 9px;
  white-space: nowrap;
}

th {
  background: #f1f3f5;
  color: #53657b;
  font-size: .68rem;
  font-weight: 700;
  text-transform: uppercase;
}

.transaction-id {
  color: #003b7a;
  font-weight: 700;
}

.amount {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 4px 7px;
  background: #e9ecef;
  color: #475569;
  font-size: .66rem;
  font-weight: 700;
}

.status-pending {
  background: #fef3c7;
  color: #92400e;
}

.status-posted,
.status-approved {
  background: #dcfce7;
  color: #166534;
}

.status-rejected {
  background: #fee2e2;
  color: #991b1b;
}

.status-reversed {
  background: #e2e8f0;
  color: #334155;
}

.empty-state {
  padding: 26px 12px;
  color: #64748b;
  text-align: center;
  font-size: .85rem;
}

.pagination {
  margin-top: 12px;
  color: #64748b;
  font-size: .78rem;
}

.pagination > div {
  justify-content: flex-end;
}

.state-card {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 120px;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 20px;
  background: #fff;
  color: #475569;
  text-align: center;
}

.state-card.compact {
  min-height: 70px;
  border: 0;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #cbd5e1;
  border-top-color: #0d6efd;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .transfer-card {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .transfer-card h3,
  .transfer-card button {
    grid-column: 1 / -1;
  }

  .filter-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .teller-dashboard {
    padding-top: 22px;
  }

  .page-heading,
  .transactions-card > .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .branch-card,
  .operations-section,
  .transactions-card {
    padding: 14px;
  }

  .branch-details {
    grid-template-columns: 1fr;
  }

  .form-grid,
  .transfer-card,
  .filter-form {
    grid-template-columns: 1fr;
  }

  .transfer-card h3,
  .transfer-card button {
    grid-column: auto;
  }

  .pagination {
    align-items: flex-start;
    flex-direction: column;
  }

  .pagination > div {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
