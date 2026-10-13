<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../services/api'

const router = useRouter()

const verifying = ref(true)
const authorized = ref(false)
const username = ref('')
const loading = ref(false)
const error = ref('')
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
  loadTransactions(1)
}

function clearFilters() {
  accountNumberFilter.value = ''
  transactionTypeFilter.value = ''
  loadTransactions(1)
}

onMounted(async () => {
  try {
    const response = await api.get('/manager/session/')

    if (response.data.success && response.data.role === 'Manager') {
      authorized.value = true
      username.value = response.data.username
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
          <p class="eyebrow">Core Banking System</p>
          <h1>Manager Dashboard</h1>
          <p class="welcome">Welcome, <strong>{{ username }}</strong></p>
        </div>
        <span class="secure-label"><span aria-hidden="true">●</span> Secure Manager Access</span>
      </div>

      <div class="summary-card" aria-live="polite">
        <div class="summary-icon" aria-hidden="true">₳</div>
        <div>
          <p class="summary-label">Pending Authorizations</p>
          <p class="summary-count">{{ pendingCount }}</p>
        </div>
        <span class="summary-caption">Awaiting review</span>
      </div>

      <section class="transactions-card" aria-labelledby="pending-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Authorization Queue</p>
            <h2 id="pending-heading">Pending Transactions</h2>
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
  </section>
</template>

<style scoped>
.manager-dashboard {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 38px clamp(18px, 4vw, 56px) 56px;
  color: #243449;
}

.dashboard-content {
  display: grid;
  gap: 24px;
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
  font-size: clamp(1.65rem, 3vw, 2.1rem);
}

.eyebrow {
  margin: 0 0 6px;
  color: #708198;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.welcome {
  margin: 8px 0 0;
  color: #62738a;
}

.welcome strong {
  color: #243449;
}

.secure-label {
  flex-shrink: 0;
  padding: 9px 14px;
  border: 1px solid #dce8e2;
  border-radius: 999px;
  background: #f3faf6;
  color: #28734c;
  font-size: 0.82rem;
  font-weight: 600;
}

.secure-label span {
  margin-right: 6px;
}

.summary-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 132px;
  padding: 24px;
  overflow: hidden;
  border-radius: 12px;
  background: linear-gradient(115deg, #07509a, #003b7a 72%);
  box-shadow: 0 8px 22px rgb(0 59 122 / 14%);
  color: #fff;
}

.summary-icon {
  display: grid;
  width: 54px;
  height: 54px;
  flex-shrink: 0;
  place-items: center;
  border: 1px solid rgb(255 255 255 / 25%);
  border-radius: 12px;
  background: rgb(255 255 255 / 12%);
  font-size: 1.7rem;
  font-weight: 700;
}

.summary-label {
  margin: 0;
  color: rgb(255 255 255 / 80%);
  font-size: 0.9rem;
}

.summary-count {
  margin: 2px 0 0;
  font-size: 2rem;
  font-weight: 700;
  line-height: 1.15;
}

.summary-caption {
  margin-left: auto;
  align-self: flex-end;
  color: rgb(255 255 255 / 76%);
  font-size: 0.82rem;
}

.transactions-card {
  min-width: 0;
  padding: clamp(18px, 3vw, 28px);
  border: 1px solid #e5eaf0;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 4px 14px rgb(30 52 77 / 5%);
}

.section-heading {
  margin-bottom: 22px;
}

.section-heading h2 {
  font-size: 1.25rem;
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
  gap: 14px;
  margin-bottom: 22px;
  padding: 16px;
  border: 1px solid #e8edf2;
  border-radius: 9px;
  background: #f8fafc;
}

.filter-field {
  display: grid;
  flex: 1 1 230px;
  gap: 6px;
  color: #53657b;
  font-size: 0.78rem;
  font-weight: 600;
}

.filter-field input,
.filter-field select {
  width: 100%;
  min-height: 40px;
  padding: 8px 11px;
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
  min-height: 40px;
  padding: 8px 14px;
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
  background: #003b7a;
  color: #fff;
}

.button-primary:hover:not(:disabled) {
  background: #07509a;
}

.button-secondary {
  border-color: #cfd8e3;
  background: #fff;
  color: #3c5068;
}

.button-secondary:hover:not(:disabled) {
  background: #f1f5f9;
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
  border: 1px solid #e5eaf0;
  border-radius: 8px;
}

table {
  width: 100%;
  min-width: 980px;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.83rem;
}

th {
  padding: 13px 14px;
  background: #f2f6fa;
  color: #53657b;
  font-size: 0.73rem;
  font-weight: 700;
  white-space: nowrap;
}

td {
  padding: 14px;
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
  padding: 5px 9px;
  border-radius: 999px;
  background: #fff5df;
  color: #875900;
  font-size: 0.72rem;
  font-weight: 700;
}

.date-cell {
  color: #5e7086;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
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
    padding-top: 26px;
  }

  .page-heading,
  .section-heading {
    align-items: flex-start;
  }

  .secure-label {
    display: none;
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
  .summary-card {
    padding: 18px;
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
