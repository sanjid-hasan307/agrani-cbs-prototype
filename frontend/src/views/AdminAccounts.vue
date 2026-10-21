<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import api from '../services/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const verifying = ref(true)
const authorized = ref(false)
const loading = ref(false)
const error = ref('')
const accounts = ref([])
const pagination = ref({
  page: 1,
  totalPages: 1,
  totalItems: 0,
  hasPrevious: false,
  hasNext: false
})

const formOpen = ref(false)
const optionsLoading = ref(false)
const optionsError = ref('')
const customers = ref([])
const products = ref([])
const branches = ref([])
const form = ref({ customer: '', product: '', branch: '' })
const formError = ref('')
const fieldError = ref('')
const submitting = ref(false)
const confirmation = ref(null)

let active = true
let requestController

function clearAccountData() {
  accounts.value = []
  pagination.value = {
    page: 1,
    totalPages: 1,
    totalItems: 0,
    hasPrevious: false,
    hasNext: false
  }
}

function clearFormData() {
  formOpen.value = false
  optionsLoading.value = false
  optionsError.value = ''
  customers.value = []
  products.value = []
  branches.value = []
  form.value = { customer: '', product: '', branch: '' }
  formError.value = ''
  fieldError.value = ''
  submitting.value = false
  confirmation.value = null
}

async function redirectToLogin() {
  authorized.value = false
  clearAccountData()
  clearFormData()
  authStore.logout()
  await router.replace('/login')
}

async function handleAuthorizationFailure(status) {
  if (status !== 401 && status !== 403) return false
  await redirectToLogin()
  return true
}

async function loadAccounts(page = 1) {
  if (!authorized.value || !active) return

  loading.value = true
  error.value = ''
  clearAccountData()

  try {
    const response = await api.get('/admin/accounts/', {
      params: { page },
      signal: requestController.signal
    })
    if (!active) return

    const data = response.data
    const meta = data?.pagination
    if (
      !data?.success
      || !Array.isArray(data.accounts)
      || !meta
      || !Number.isInteger(meta.page)
      || !Number.isInteger(meta.total_pages)
      || !Number.isInteger(meta.total_items)
    ) {
      error.value = 'Account records could not be loaded. Please try again.'
      return
    }

    accounts.value = data.accounts
    pagination.value = {
      page: meta.page,
      totalPages: Math.max(1, meta.total_pages),
      totalItems: meta.total_items,
      hasPrevious: Boolean(meta.has_previous),
      hasNext: Boolean(meta.has_next)
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return

    clearAccountData()
    if (await handleAuthorizationFailure(requestError.response?.status)) return
    error.value = 'Unable to load account records. Please check your connection and try again.'
  } finally {
    if (active) loading.value = false
  }
}

async function verifyAdminSession() {
  requestController?.abort()
  requestController = new AbortController()
  verifying.value = true
  authorized.value = false
  error.value = ''
  clearAccountData()
  clearFormData()

  try {
    const response = await api.get('/admin/session/', {
      signal: requestController.signal
    })
    if (!active) return

    if (
      !response.data?.success
      || response.data.role !== 'Admin'
      || typeof response.data.username !== 'string'
      || !response.data.username
    ) {
      await redirectToLogin()
      return
    }

    authStore.setUser(response.data)
    authorized.value = true
    await loadAccounts(1)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return

    clearAccountData()
    clearFormData()
    authStore.logout()
    if (requestError.response?.status === 401 || requestError.response?.status === 403) {
      await router.replace('/login')
    } else {
      error.value = 'Unable to verify your Admin session. Please try again.'
    }
  } finally {
    if (active) verifying.value = false
  }
}

async function loadOptions() {
  optionsLoading.value = true
  optionsError.value = ''
  customers.value = []
  products.value = []
  branches.value = []
  try {
    const [customerResponse, productResponse, branchResponse] = await Promise.all([
      api.get('/admin/accounts/customers/options/', {
        signal: requestController.signal
      }),
      api.get('/admin/accounts/products/options/', {
        signal: requestController.signal
      }),
      api.get('/admin/branches/options/', {
        signal: requestController.signal
      })
    ])
    if (!active || !formOpen.value) return

    const customerOptions = customerResponse.data?.customers
    const productOptions = productResponse.data?.products
    const branchOptions = branchResponse.data?.branches
    if (
      !customerResponse.data?.success
      || !productResponse.data?.success
      || !branchResponse.data?.success
      || !Array.isArray(customerOptions)
      || !Array.isArray(productOptions)
      || !Array.isArray(branchOptions)
    ) {
      optionsError.value = 'Account-opening options could not be loaded. Please retry.'
      return
    }

    customers.value = customerOptions.filter(customer => (
      Number.isInteger(customer.id)
      && customer.id > 0
      && typeof customer.cif === 'string'
      && typeof customer.display_name === 'string'
      && Number.isInteger(customer.home_branch?.id)
      && typeof customer.home_branch?.branch_code === 'string'
      && typeof customer.home_branch?.branch_name === 'string'
    ))
    products.value = productOptions.filter(product => (
      Number.isInteger(product.id)
      && product.id > 0
      && typeof product.product_code === 'string'
      && typeof product.product_name === 'string'
      && typeof product.product_type === 'string'
      && typeof product.currency === 'string'
    ))
    branches.value = branchOptions.filter(branch => (
      Number.isInteger(branch.id)
      && branch.id > 0
      && typeof branch.branch_code === 'string'
      && typeof branch.branch_name === 'string'
    ))

    if (!customers.value.length || !products.value.length || !branches.value.length) {
      optionsError.value = 'No eligible customers, active products, or active branches are available.'
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return
    optionsError.value = 'Unable to load account-opening options. Check your connection and retry.'
  } finally {
    if (active) optionsLoading.value = false
  }
}

function openForm() {
  if (!authorized.value || optionsLoading.value || submitting.value) return
  clearFormData()
  formOpen.value = true
  loadOptions()
}

function closeForm() {
  if (submitting.value) return
  clearFormData()
}

function selectedCustomer() {
  return customers.value.find(customer => customer.id === Number(form.value.customer))
}

function selectedBranch() {
  return branches.value.find(branch => branch.id === Number(form.value.branch))
}

function validateForm() {
  const customer = selectedCustomer()
  const product = products.value.find(item => item.id === Number(form.value.product))
  const branch = selectedBranch()
  fieldError.value = ''

  if (!customer || !product || !branch) {
    fieldError.value = 'Select an eligible customer, active product, and active branch.'
    return false
  }
  if (branch.id !== customer.home_branch.id) {
    fieldError.value = 'The account branch must match the selected customer’s home branch.'
    return false
  }
  return true
}

function setCustomer(value) {
  form.value.customer = value
  fieldError.value = ''
  formError.value = ''
  const customer = selectedCustomer()
  if (customer) form.value.branch = String(customer.home_branch.id)
}

function setSelection(field, value) {
  form.value[field] = value
  fieldError.value = ''
  formError.value = ''
}

async function submitForm() {
  if (submitting.value || optionsLoading.value || !validateForm()) return

  const payload = {
    customer: Number(form.value.customer),
    product: Number(form.value.product),
    branch: Number(form.value.branch)
  }
  submitting.value = true
  formError.value = ''

  try {
    const response = await api.post('/admin/accounts/', payload, {
      signal: requestController.signal
    })
    if (!active) return

    const account = response.data?.account
    if (
      response.status !== 201
      || !response.data?.success
      || !Number.isInteger(account?.id)
      || typeof account?.account_number !== 'string'
      || typeof account?.customer_name !== 'string'
      || typeof account?.customer_cif !== 'string'
      || typeof account?.product_code !== 'string'
      || typeof account?.product_name !== 'string'
      || typeof account?.branch_code !== 'string'
      || typeof account?.branch_name !== 'string'
      || typeof account?.currency !== 'string'
      || typeof account?.account_status !== 'string'
      || typeof account?.opening_date !== 'string'
      || account?.available_balance !== '0.00'
      || account?.ledger_balance !== '0.00'
    ) {
      formError.value = 'The account could not be opened. Please try again.'
      return
    }

    const safeConfirmation = {
      account_number: account.account_number,
      customer_name: account.customer_name,
      customer_cif: account.customer_cif,
      product_code: account.product_code,
      product_name: account.product_name,
      branch_code: account.branch_code,
      branch_name: account.branch_name,
      currency: account.currency,
      account_status: account.account_status,
      opening_date: account.opening_date,
      available_balance: account.available_balance,
      ledger_balance: account.ledger_balance
    }
    clearFormData()
    confirmation.value = safeConfirmation
    await loadAccounts(1)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return

    const status = requestError.response?.status
    if (status === 400) {
      formError.value = 'The selected customer, product, or branch was rejected. Confirm the customer’s home branch and try again.'
    } else if (status === 409) {
      formError.value = 'The account opening conflicts with an existing record. Please retry or contact support.'
    } else if (status === 413) {
      formError.value = 'The account-opening request was too large. Please retry.'
    } else {
      formError.value = 'Unable to open the account. Check your connection and try again.'
    }
  } finally {
    if (active) submitting.value = false
  }
}

function changePage(page) {
  if (
    !Number.isInteger(page)
    || page < 1
    || page > pagination.value.totalPages
    || loading.value
  ) return
  loadAccounts(page)
}

function formatDate(value) {
  if (typeof value !== 'string') return '—'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('en-BD', {
    dateStyle: 'medium',
    timeZone: 'Asia/Dhaka'
  }).format(date)
}

onMounted(verifyAdminSession)

onBeforeUnmount(() => {
  active = false
  requestController?.abort()
  clearAccountData()
  clearFormData()
})
</script>

<template>
  <section class="account-page">
    <div v-if="verifying" class="state-card" role="status">
      <span class="spinner" aria-hidden="true"></span>
      Verifying your Admin session...
    </div>

    <div v-else-if="error && !authorized" class="state-card error-card" role="alert">
      <p>{{ error }}</p>
      <button class="primary-button" type="button" @click="verifyAdminSession">
        Retry
      </button>
    </div>

    <div v-else-if="authorized" class="page-content">
      <div class="page-heading">
        <div>
          <p class="eyebrow">CBS Administration</p>
          <h1>Account Management</h1>
        </div>
        <RouterLink class="back-link" to="/dashboard/admin">
          <span aria-hidden="true">←</span>
          Back to Admin Dashboard
        </RouterLink>
      </div>

      <section class="list-card" aria-labelledby="account-list-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Account records</p>
            <h2 id="account-list-heading">Account List</h2>
          </div>
          <div class="list-actions">
            <span class="record-count">{{ pagination.totalItems }} records</span>
            <button
              class="primary-button"
              type="button"
              :disabled="optionsLoading || submitting"
              @click="openForm"
            >
              Open New Account
            </button>
          </div>
        </div>

        <section
          v-if="confirmation"
          class="confirmation-card"
          aria-live="polite"
          aria-labelledby="account-confirmation-heading"
        >
          <div>
            <p class="eyebrow">Account opened</p>
            <h3 id="account-confirmation-heading">
              Account {{ confirmation.account_number }} opened successfully
            </h3>
            <p>
              {{ confirmation.customer_name }} · CIF {{ confirmation.customer_cif }}
              · {{ confirmation.product_code }} — {{ confirmation.product_name }}
            </p>
            <p>
              {{ confirmation.branch_code }} — {{ confirmation.branch_name }}
              · {{ confirmation.currency }} · {{ confirmation.account_status }}
            </p>
            <p>
              Available balance: {{ confirmation.available_balance }} {{ confirmation.currency }}
              · Ledger balance: {{ confirmation.ledger_balance }} {{ confirmation.currency }}
            </p>
          </div>
          <button
            class="dismiss-button"
            type="button"
            aria-label="Dismiss account-opening confirmation"
            @click="confirmation = null"
          >
            ×
          </button>
        </section>

        <div v-if="loading" class="inline-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading account records...
        </div>

        <div v-else-if="error" class="inline-state error-message" role="alert">
          <p>{{ error }}</p>
          <button class="secondary-button" type="button" @click="loadAccounts(pagination.page)">
            Retry
          </button>
        </div>

        <div v-else-if="accounts.length === 0" class="empty-state" role="status">
          <h3>No accounts found</h3>
          <p>There are no account records to display yet.</p>
        </div>

        <template v-else>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Account Number</th>
                  <th scope="col">Customer</th>
                  <th scope="col">Product</th>
                  <th scope="col">Branch</th>
                  <th scope="col">Currency</th>
                  <th scope="col">Account Status</th>
                  <th scope="col">Opening Date</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="account in accounts" :key="account.id">
                  <td class="account-number">{{ account.account_number }}</td>
                  <td>
                    <span class="customer-name">{{ account.customer_name }}</span>
                    <span class="secondary-detail">CIF {{ account.customer_cif }}</span>
                  </td>
                  <td>
                    <span>{{ account.product_code }}</span>
                    <span class="secondary-detail">{{ account.product_name }}</span>
                  </td>
                  <td>
                    <span>{{ account.branch_code }}</span>
                    <span class="secondary-detail">{{ account.branch_name }}</span>
                  </td>
                  <td>{{ account.currency }}</td>
                  <td>
                    <span class="status-badge">{{ account.account_status }}</span>
                  </td>
                  <td>{{ formatDate(account.opening_date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <nav class="pagination" aria-label="Account list pagination">
            <button
              class="secondary-button"
              type="button"
              :disabled="loading || !pagination.hasPrevious"
              @click="changePage(pagination.page - 1)"
            >
              Previous
            </button>
            <span aria-live="polite">
              Page {{ pagination.page }} of {{ pagination.totalPages }}
            </span>
            <button
              class="secondary-button"
              type="button"
              :disabled="loading || !pagination.hasNext"
              @click="changePage(pagination.page + 1)"
            >
              Next
            </button>
          </nav>
        </template>
      </section>
    </div>

    <div v-if="formOpen" class="modal-backdrop" @click.self="closeForm">
      <section
        class="account-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-form-heading"
        aria-describedby="account-form-intro"
      >
        <header class="modal-heading">
          <div>
            <p class="eyebrow">Account setup</p>
            <h2 id="account-form-heading">Open New Account</h2>
          </div>
          <button
            class="dismiss-button"
            type="button"
            aria-label="Close account form"
            :disabled="submitting"
            @click="closeForm"
          >
            ×
          </button>
        </header>

        <p id="account-form-intro" class="modal-intro">
          Choose an eligible customer, an active account product, and an active branch.
          The selected branch must match the customer’s home branch.
        </p>
        <div class="notice" role="note">
          Newly opened accounts start with zero available and ledger balances. Opening an
          account does not make an initial deposit.
        </div>

        <div v-if="optionsLoading" class="inline-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading eligible customers, products, and active branches...
        </div>

        <div v-else-if="optionsError" class="inline-state error-message" role="alert">
          <p>{{ optionsError }}</p>
          <button class="secondary-button" type="button" @click="loadOptions">
            Retry
          </button>
        </div>

        <form v-else class="account-form" @submit.prevent="submitForm">
          <div class="form-field">
            <label for="account-customer">Customer <span>*</span></label>
            <select
              id="account-customer"
              :value="form.customer"
              :disabled="submitting || !customers.length"
              :aria-invalid="Boolean(fieldError)"
              @change="setCustomer($event.target.value)"
            >
              <option value="">Select an eligible customer</option>
              <option v-for="customer in customers" :key="customer.id" :value="customer.id">
                {{ customer.display_name }} · CIF {{ customer.cif }}
                · {{ customer.home_branch.branch_code }} — {{ customer.home_branch.branch_name }}
              </option>
            </select>
          </div>

          <div class="form-field">
            <label for="account-product">Account Product <span>*</span></label>
            <select
              id="account-product"
              :value="form.product"
              :disabled="submitting || !products.length"
              :aria-invalid="Boolean(fieldError)"
              @change="setSelection('product', $event.target.value)"
            >
              <option value="">Select an active product</option>
              <option v-for="product in products" :key="product.id" :value="product.id">
                {{ product.product_code }} — {{ product.product_name }}
                ({{ product.product_type }}, {{ product.currency }})
              </option>
            </select>
          </div>

          <div class="form-field form-field-wide">
            <label for="account-branch">Account Branch <span>*</span></label>
            <select
              id="account-branch"
              :value="form.branch"
              :disabled="submitting || !branches.length"
              :aria-invalid="Boolean(fieldError)"
              @change="setSelection('branch', $event.target.value)"
            >
              <option value="">Select an active branch</option>
              <option v-for="branch in branches" :key="branch.id" :value="branch.id">
                {{ branch.branch_code }} — {{ branch.branch_name }}
              </option>
            </select>
            <span v-if="selectedCustomer()" class="field-hint">
              Customer home branch: {{ selectedCustomer().home_branch.branch_code }} —
              {{ selectedCustomer().home_branch.branch_name }}
            </span>
          </div>

          <p v-if="fieldError" class="form-error form-field-wide" role="alert">
            {{ fieldError }}
          </p>
          <p v-if="formError" class="form-error form-field-wide" role="alert">
            {{ formError }}
          </p>

          <footer class="form-actions form-field-wide">
            <button
              class="secondary-button"
              type="button"
              :disabled="submitting"
              @click="closeForm"
            >
              Cancel
            </button>
            <button
              class="primary-button"
              type="submit"
              :disabled="submitting || optionsLoading || !customers.length || !products.length || !branches.length"
              :aria-busy="submitting"
            >
              {{ submitting ? 'Opening account...' : 'Open Account' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.account-page {
  width: min(100%, 1280px);
  margin: 0 auto;
  padding: 30px clamp(16px, 4vw, 40px);
  color: #25364a;
}

.page-content {
  display: grid;
  gap: 20px;
}

.page-heading,
.section-heading,
.modal-heading,
.form-actions,
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.page-heading h1 {
  margin: 0;
  color: #173f6d;
  font-size: clamp(1.45rem, 3vw, 1.9rem);
}

.eyebrow {
  margin: 0 0 5px;
  color: #63758a;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.back-link {
  color: #245b8f;
  font-size: 0.82rem;
  font-weight: 700;
  text-decoration: none;
}

.back-link:hover,
.back-link:focus-visible {
  text-decoration: underline;
}

.list-card,
.state-card {
  border: 1px solid #e3e9f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 4px 14px rgb(26 52 82 / 5%);
}

.list-card {
  min-width: 0;
  padding: 20px;
}

.section-heading {
  margin-bottom: 20px;
}

.section-heading h2,
.modal-heading h2 {
  margin: 0;
  color: #173f6d;
  font-size: 1.1rem;
}

.list-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.record-count {
  color: #63758a;
  font-size: 0.8rem;
}

.primary-button,
.secondary-button {
  display: inline-flex;
  min-height: 37px;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 8px 13px;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
}

.primary-button {
  background: #0d6efd;
  color: #fff;
}

.primary-button:hover:not(:disabled) {
  background: #0a58ca;
}

.secondary-button {
  border-color: #cbd5e1;
  background: #fff;
  color: #334b65;
}

.secondary-button:hover:not(:disabled) {
  background: #f3f6fa;
}

.primary-button:disabled,
.secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
  text-align: left;
}

th,
td {
  border-bottom: 1px solid #e8edf3;
  padding: 12px 10px;
  vertical-align: middle;
}

th {
  background: #f6f8fb;
  color: #52657b;
  font-size: 0.7rem;
  font-weight: 700;
  white-space: nowrap;
}

td {
  color: #34485f;
}

.account-number,
.customer-name {
  color: #173f6d;
  font-weight: 700;
}

.secondary-detail {
  display: block;
  margin-top: 3px;
  color: #718096;
  font-size: 0.72rem;
}

.status-badge {
  display: inline-flex;
  width: fit-content;
  border-radius: 999px;
  padding: 4px 8px;
  background: #e8f5ee;
  color: #237548;
  font-size: 0.68rem;
  font-weight: 700;
}

.pagination {
  justify-content: center;
  margin-top: 18px;
  color: #53657b;
  font-size: 0.82rem;
}

.inline-state,
.empty-state,
.state-card {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 26px 16px;
  color: #53657b;
  font-size: 0.88rem;
  text-align: center;
}

.inline-state {
  flex-wrap: wrap;
}

.inline-state p,
.empty-state p,
.state-card p {
  margin: 0;
}

.empty-state {
  min-height: 150px;
  flex-direction: column;
  gap: 5px;
}

.empty-state h3 {
  margin: 0;
  color: #173f6d;
  font-size: 0.98rem;
}

.state-card {
  min-height: 150px;
  flex-direction: column;
  border: 1px solid #e3e9f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 4px 14px rgb(26 52 82 / 5%);
}

.error-card,
.error-message {
  color: #842029;
}

.error-card {
  border-color: #f1c2c7;
}

.spinner {
  width: 22px;
  height: 22px;
  border: 3px solid #dce5ef;
  border-top-color: #0d6efd;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.confirmation-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin: 0 0 18px;
  border: 1px solid #b7dfc5;
  border-radius: 8px;
  padding: 15px;
  background: #f0faf3;
  color: #28583a;
}

.confirmation-card h3 {
  margin: 0 0 7px;
  color: #1e5834;
  font-size: 0.95rem;
}

.confirmation-card p:not(.eyebrow) {
  margin: 4px 0 0;
  font-size: 0.8rem;
  line-height: 1.5;
}

.dismiss-button {
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #52657b;
  font-size: 1.4rem;
  line-height: 1;
  cursor: pointer;
}

.dismiss-button:hover:not(:disabled) {
  background: rgb(23 63 109 / 8%);
}

.dismiss-button:disabled {
  cursor: not-allowed;
}

.modal-backdrop {
  position: fixed;
  z-index: 20;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow-y: auto;
  padding: 20px;
  background: rgb(17 34 54 / 52%);
}

.account-modal {
  width: min(100%, 650px);
  max-height: min(90vh, 820px);
  overflow-y: auto;
  border: 1px solid #e3e9f0;
  border-radius: 12px;
  padding: clamp(18px, 4vw, 28px);
  background: #fff;
  box-shadow: 0 18px 50px rgb(12 35 60 / 25%);
}

.modal-heading {
  margin-bottom: 12px;
}

.modal-intro {
  margin: 0 0 14px;
  color: #5b6e83;
  font-size: 0.84rem;
  line-height: 1.55;
}

.notice {
  margin-bottom: 18px;
  border: 1px solid #b8d5f2;
  border-radius: 7px;
  padding: 11px 13px;
  background: #eef6ff;
  color: #244f7a;
  font-size: 0.8rem;
  line-height: 1.5;
}

.account-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 15px;
}

.form-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.form-field-wide {
  grid-column: 1 / -1;
}

.form-field label {
  color: #354b63;
  font-size: 0.78rem;
  font-weight: 700;
}

.form-field label > span {
  color: #b42318;
}

.form-field select {
  width: 100%;
  min-height: 40px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fff;
  color: #25364a;
  font: inherit;
  font-size: 0.82rem;
}

.form-field select:focus-visible,
.primary-button:focus-visible,
.secondary-button:focus-visible,
.dismiss-button:focus-visible,
.back-link:focus-visible {
  outline: 3px solid rgb(13 110 253 / 25%);
  outline-offset: 2px;
}

.form-field select:disabled {
  background: #f4f6f9;
  color: #718096;
}

.form-field select[aria-invalid="true"] {
  border-color: #b42318;
}

.field-hint {
  color: #63758a;
  font-size: 0.74rem;
}

.form-error {
  margin: 0;
  color: #842029;
  font-size: 0.8rem;
}

.form-actions {
  justify-content: flex-end;
  margin-top: 4px;
  border-top: 1px solid #e8edf3;
  padding-top: 15px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 680px) {
  .page-heading,
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .list-actions {
    width: 100%;
    justify-content: space-between;
  }

  .list-card {
    padding: 15px;
  }

  .account-form {
    grid-template-columns: 1fr;
  }

  .form-field-wide {
    grid-column: auto;
  }

  .modal-backdrop {
    align-items: flex-start;
    padding: 12px;
  }

  .account-modal {
    max-height: calc(100vh - 24px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 2s;
  }
}
</style>
