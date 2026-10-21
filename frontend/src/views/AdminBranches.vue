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
const branches = ref([])
const statusFilter = ref('active')
const pagination = ref({
  page: 1,
  totalPages: 1,
  totalItems: 0,
  hasPrevious: false,
  hasNext: false
})

const formOpen = ref(false)
const editing = ref(false)
const editingId = ref(null)
const formLoading = ref(false)
const submitting = ref(false)
const formError = ref('')
const fieldErrors = ref({})
const form = ref({})
const notice = ref('')

const branchFieldLimits = {
  branch_code: 20,
  branch_name: 150,
  routing_number: 20,
  district: 100,
  phone: 20,
  email: 254,
  address: 5000
}

let active = true
let requestController

function resetForm() {
  form.value = {
    branch_code: '',
    branch_name: '',
    routing_number: '',
    address: '',
    district: '',
    phone: '',
    email: ''
  }
}

resetForm()

function clearBranchData() {
  branches.value = []
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
  editing.value = false
  editingId.value = null
  formLoading.value = false
  submitting.value = false
  formError.value = ''
  fieldErrors.value = {}
  resetForm()
}

async function redirectToLogin() {
  authorized.value = false
  clearBranchData()
  clearFormData()
  notice.value = ''
  authStore.logout()
  await router.replace('/login')
}

async function handleAuthorizationFailure(status) {
  if (status !== 401 && status !== 403) return false
  await redirectToLogin()
  return true
}

async function loadBranches(page = 1) {
  if (!authorized.value || !active) return

  loading.value = true
  error.value = ''
  clearBranchData()
  try {
    const response = await api.get('/admin/branches/', {
      params: { page, status: statusFilter.value },
      signal: requestController.signal
    })
    if (!active) return

    const data = response.data
    const meta = data?.pagination
    if (
      !data?.success
      || !Array.isArray(data.branches)
      || !meta
      || !Number.isInteger(meta.page)
      || !Number.isInteger(meta.total_pages)
      || !Number.isInteger(meta.total_items)
    ) {
      error.value = 'Branch records could not be loaded. Please try again.'
      return
    }

    branches.value = data.branches
    pagination.value = {
      page: meta.page,
      totalPages: Math.max(1, meta.total_pages),
      totalItems: meta.total_items,
      hasPrevious: Boolean(meta.has_previous),
      hasNext: Boolean(meta.has_next)
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    clearBranchData()
    if (await handleAuthorizationFailure(requestError.response?.status)) return
    error.value = requestError.response?.status === 400
      ? 'The page or status filter is invalid. Please choose a valid filter and retry.'
      : 'Unable to load branch records. Please check your connection and try again.'
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
  notice.value = ''
  clearBranchData()
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
    await loadBranches(1)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    clearBranchData()
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

function changeStatusFilter(value) {
  if (!['active', 'inactive', 'all'].includes(value)) return
  statusFilter.value = value
  loadBranches(1)
}

function changePage(page) {
  if (
    !Number.isInteger(page)
    || page < 1
    || page > pagination.value.totalPages
    || loading.value
  ) return
  loadBranches(page)
}

function openCreateForm() {
  if (!authorized.value || submitting.value || formLoading.value) return
  clearFormData()
  formOpen.value = true
}

function validateForm() {
  const values = form.value
  const errors = {}
  const required = [
    ['branch_code', 'Branch code'],
    ['branch_name', 'Branch name'],
    ['address', 'Address'],
    ['district', 'District']
  ]

  for (const [field, label] of required) {
    if (!values[field].trim()) errors[field] = `${label} is required.`
  }
  for (const [field, limit] of Object.entries(branchFieldLimits)) {
    if (values[field].length > limit) {
      errors[field] = `Must be ${limit} characters or fewer.`
    }
  }
  if (values.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = 'Enter a valid email address.'
  }

  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}

function setField(field, value) {
  form.value[field] = value
  if (fieldErrors.value[field]) {
    const nextErrors = { ...fieldErrors.value }
    delete nextErrors[field]
    fieldErrors.value = nextErrors
  }
  formError.value = ''
}

function closeForm() {
  if (submitting.value || formLoading.value) return
  clearFormData()
}

async function openEditForm(branchId) {
  if (!authorized.value || submitting.value || formLoading.value) return
  clearFormData()
  formOpen.value = true
  editing.value = true
  editingId.value = branchId
  formLoading.value = true

  try {
    const response = await api.get(`/admin/branches/${branchId}/`, {
      signal: requestController.signal
    })
    if (!active || !formOpen.value) return

    const branch = response.data?.branch
    if (
      !response.data?.success
      || !branch
      || branch.id !== branchId
      || typeof branch.branch_code !== 'string'
      || typeof branch.branch_name !== 'string'
      || typeof branch.address !== 'string'
      || typeof branch.district !== 'string'
      || typeof branch.is_active !== 'boolean'
    ) {
      formError.value = 'Branch details could not be loaded. Please retry.'
      return
    }

    form.value = {
      branch_code: branch.branch_code,
      branch_name: branch.branch_name,
      routing_number: '',
      address: branch.address,
      district: branch.district,
      phone: branch.phone || '',
      email: branch.email || '',
      is_active: branch.is_active
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return
    if (requestError.response?.status === 404) {
      formError.value = 'This branch no longer exists. Refresh the branch list and try again.'
    } else {
      formError.value = 'Unable to load branch details. Please check your connection and retry.'
    }
  } finally {
    if (active) formLoading.value = false
  }
}

async function submitForm() {
  if (submitting.value || formLoading.value || !validateForm()) return
  submitting.value = true
  formError.value = ''

  const payload = editing.value
    ? {
        branch_name: form.value.branch_name.trim(),
        address: form.value.address.trim(),
        district: form.value.district.trim(),
        phone: form.value.phone.trim(),
        email: form.value.email.trim()
      }
    : {
        branch_code: form.value.branch_code.trim(),
        branch_name: form.value.branch_name.trim(),
        routing_number: form.value.routing_number.trim(),
        address: form.value.address.trim(),
        district: form.value.district.trim(),
        phone: form.value.phone.trim(),
        email: form.value.email.trim()
      }

  try {
    const response = editing.value
      ? await api.patch(`/admin/branches/${editingId.value}/`, payload, {
          signal: requestController.signal
        })
      : await api.post('/admin/branches/', payload, {
          signal: requestController.signal
        })
    if (!active) return

    const branch = response.data?.branch
    if (
      !response.data?.success
      || !Number.isInteger(branch?.id)
      || typeof branch?.branch_code !== 'string'
      || typeof branch?.branch_name !== 'string'
    ) {
      formError.value = 'The branch could not be saved. Please try again.'
      return
    }

    notice.value = editing.value
      ? `Branch ${branch.branch_code} was updated successfully.`
      : `Branch ${branch.branch_code} was created successfully.`
    clearFormData()
    await loadBranches(1)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return

    const status = requestError.response?.status
    if (status === 400) {
      const serverErrors = requestError.response?.data?.errors
      if (serverErrors && typeof serverErrors === 'object') {
        fieldErrors.value = Object.fromEntries(
          Object.keys(serverErrors).map(field => [field, 'Please check this field.'])
        )
      }
      formError.value = 'Branch details were rejected. Review the fields and try again.'
    } else if (status === 404) {
      formError.value = 'This branch no longer exists. Refresh the list and try again.'
    } else if (status === 409) {
      formError.value = 'The branch code or routing number is already in use.'
    } else if (status === 413) {
      formError.value = 'The request is too large. Shorten the address and try again.'
    } else {
      formError.value = 'Unable to save the branch. Please check your connection and try again.'
    }
  } finally {
    if (active) submitting.value = false
  }
}

async function toggleBranchStatus(branch) {
  if (submitting.value || !authorized.value) return
  const nextActive = !branch.is_active
  const action = nextActive ? 'reactivate' : 'deactivate'
  const relationshipNote = ' Existing customer, account, and staff relationships will remain unchanged.'
  if (!window.confirm(`Are you sure you want to ${action} ${branch.branch_code}?${relationshipNote}`)) {
    return
  }

  submitting.value = true
  error.value = ''
  try {
    const response = await api.patch(
      `/admin/branches/${branch.id}/`,
      { is_active: nextActive },
      { signal: requestController.signal }
    )
    if (!active) return

    if (!response.data?.success || response.data.branch?.is_active !== nextActive) {
      error.value = 'Branch status could not be changed. Please try again.'
      return
    }
    notice.value = `Branch ${branch.branch_code} was ${nextActive ? 'reactivated' : 'deactivated'}. Existing relationships were retained.`
    await loadBranches(pagination.value.page)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return
    const status = requestError.response?.status
    if (status === 400) {
      error.value = 'The branch status change was rejected. Refresh the list and retry.'
    } else if (status === 404) {
      error.value = 'This branch no longer exists. Refresh the branch list.'
    } else {
      error.value = 'Unable to change branch status. Please check your connection and retry.'
    }
  } finally {
    if (active) submitting.value = false
  }
}

function formatDate(value) {
  if (typeof value !== 'string') return '—'
  const date = new Date(value)
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
  clearBranchData()
  clearFormData()
  notice.value = ''
})
</script>

<template>
  <section class="branch-page">
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
          <h1>Branch Management</h1>
        </div>
        <RouterLink class="back-link" to="/dashboard/admin">
          <span aria-hidden="true">←</span>
          Back to Admin Dashboard
        </RouterLink>
      </div>

      <section class="list-card" aria-labelledby="branch-list-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Branch records</p>
            <h2 id="branch-list-heading">Branch List</h2>
          </div>
          <div class="list-actions">
            <span class="record-count">{{ pagination.totalItems }} records</span>
            <button class="primary-button" type="button" @click="openCreateForm">
              Add New Branch
            </button>
          </div>
        </div>

        <section v-if="notice" class="notice success-notice" aria-live="polite">
          <p>{{ notice }}</p>
          <button
            class="dismiss-button"
            type="button"
            aria-label="Dismiss notification"
            @click="notice = ''"
          >
            ×
          </button>
        </section>

        <div class="filter-row">
          <label for="branch-status-filter">Show branches</label>
          <select
            id="branch-status-filter"
            :value="statusFilter"
            :disabled="loading"
            @change="changeStatusFilter($event.target.value)"
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="all">All</option>
          </select>
        </div>

        <div v-if="loading" class="inline-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading branch records...
        </div>

        <div v-else-if="error" class="inline-state error-message" role="alert">
          <p>{{ error }}</p>
          <button class="secondary-button" type="button" @click="loadBranches(pagination.page)">
            Retry
          </button>
        </div>

        <div v-else-if="branches.length === 0" class="empty-state" role="status">
          <h3>No branches found</h3>
          <p>There are no {{ statusFilter }} branch records to display.</p>
        </div>

        <template v-else>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Branch Code</th>
                  <th scope="col">Branch Name</th>
                  <th scope="col">District</th>
                  <th scope="col">Address</th>
                  <th scope="col">Phone</th>
                  <th scope="col">Email</th>
                  <th scope="col">Status</th>
                  <th scope="col">Updated Date</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="branch in branches" :key="branch.id">
                  <td class="branch-code">{{ branch.branch_code }}</td>
                  <td class="branch-name">{{ branch.branch_name }}</td>
                  <td>{{ branch.district }}</td>
                  <td class="address-cell">{{ branch.address }}</td>
                  <td>{{ branch.phone || '—' }}</td>
                  <td>{{ branch.email || '—' }}</td>
                  <td>
                    <span
                      class="status-badge"
                      :class="branch.is_active ? 'status-active' : 'status-inactive'"
                    >
                      {{ branch.is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td>{{ formatDate(branch.updated_at) }}</td>
                  <td>
                    <div class="row-actions">
                      <button
                        class="text-button"
                        type="button"
                        :disabled="submitting"
                        @click="openEditForm(branch.id)"
                      >
                        View / Edit
                      </button>
                      <button
                        class="text-button"
                        type="button"
                        :disabled="submitting"
                        @click="toggleBranchStatus(branch)"
                      >
                        {{ branch.is_active ? 'Deactivate' : 'Reactivate' }}
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <nav class="pagination" aria-label="Branch list pagination">
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
        class="branch-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="branch-form-heading"
        aria-describedby="branch-form-intro"
      >
        <header class="modal-heading">
          <div>
            <p class="eyebrow">{{ editing ? 'Branch details' : 'Branch setup' }}</p>
            <h2 id="branch-form-heading">
              {{ editing ? 'View / Edit Branch' : 'Add New Branch' }}
            </h2>
          </div>
          <button
            class="dismiss-button"
            type="button"
            aria-label="Close branch form"
            :disabled="submitting || formLoading"
            @click="closeForm"
          >
            ×
          </button>
        </header>

        <p id="branch-form-intro" class="modal-intro">
          Branch codes are manually assigned and cannot be changed after creation.
          Inactive branches retain existing customer, account, and staff relationships.
        </p>

        <div v-if="formLoading" class="inline-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading branch details...
        </div>

        <form v-else class="branch-form" @submit.prevent="submitForm">
          <template v-if="editing">
            <div class="form-field">
              <label for="branch-code-readonly">Branch Code</label>
              <input id="branch-code-readonly" :value="form.branch_code" readonly />
            </div>
            <div class="form-field">
              <label for="branch-routing-readonly">Routing Number</label>
              <input
                id="branch-routing-readonly"
                value="Immutable; not returned by the detail API"
                readonly
                aria-describedby="branch-routing-note"
              />
              <span id="branch-routing-note" class="field-hint">
                It cannot be changed, and the detail API does not expose its value.
              </span>
            </div>
          </template>
          <template v-else>
            <div class="form-field">
              <label for="branch-code">Branch Code <span>*</span></label>
              <input
                id="branch-code"
                :value="form.branch_code"
                maxlength="20"
                autocomplete="off"
                :aria-invalid="Boolean(fieldErrors.branch_code)"
                aria-describedby="branch-code-error"
                :disabled="submitting"
                @input="setField('branch_code', $event.target.value)"
              />
              <span v-if="fieldErrors.branch_code" id="branch-code-error" class="field-error">
                {{ fieldErrors.branch_code }}
              </span>
            </div>
            <div class="form-field">
              <label for="branch-routing">Routing Number <span class="optional-label">Optional</span></label>
              <input
                id="branch-routing"
                :value="form.routing_number"
                maxlength="20"
                autocomplete="off"
                :aria-invalid="Boolean(fieldErrors.routing_number)"
                aria-describedby="branch-routing-create-error"
                :disabled="submitting"
                @input="setField('routing_number', $event.target.value)"
              />
              <span
                v-if="fieldErrors.routing_number"
                id="branch-routing-create-error"
                class="field-error"
              >
                {{ fieldErrors.routing_number }}
              </span>
            </div>
          </template>

          <div class="form-field">
            <label for="branch-name">Branch Name <span>*</span></label>
            <input
              id="branch-name"
              :value="form.branch_name"
              maxlength="150"
              :aria-invalid="Boolean(fieldErrors.branch_name)"
              aria-describedby="branch-name-error"
              :disabled="submitting"
              @input="setField('branch_name', $event.target.value)"
            />
            <span v-if="fieldErrors.branch_name" id="branch-name-error" class="field-error">
              {{ fieldErrors.branch_name }}
            </span>
          </div>

          <div class="form-field">
            <label for="branch-district">District <span>*</span></label>
            <input
              id="branch-district"
              :value="form.district"
              maxlength="100"
              :aria-invalid="Boolean(fieldErrors.district)"
              aria-describedby="branch-district-error"
              :disabled="submitting"
              @input="setField('district', $event.target.value)"
            />
            <span v-if="fieldErrors.district" id="branch-district-error" class="field-error">
              {{ fieldErrors.district }}
            </span>
          </div>

          <div class="form-field form-field-wide">
            <label for="branch-address">Address <span>*</span></label>
            <textarea
              id="branch-address"
              :value="form.address"
              maxlength="5000"
              rows="3"
              :aria-invalid="Boolean(fieldErrors.address)"
              aria-describedby="branch-address-error"
              :disabled="submitting"
              @input="setField('address', $event.target.value)"
            ></textarea>
            <span v-if="fieldErrors.address" id="branch-address-error" class="field-error">
              {{ fieldErrors.address }}
            </span>
          </div>

          <div class="form-field">
            <label for="branch-phone">Phone <span class="optional-label">Optional</span></label>
            <input
              id="branch-phone"
              :value="form.phone"
              type="tel"
              maxlength="20"
              autocomplete="off"
              :aria-invalid="Boolean(fieldErrors.phone)"
              aria-describedby="branch-phone-error"
              :disabled="submitting"
              @input="setField('phone', $event.target.value)"
            />
            <span v-if="fieldErrors.phone" id="branch-phone-error" class="field-error">
              {{ fieldErrors.phone }}
            </span>
          </div>

          <div class="form-field">
            <label for="branch-email">Email <span class="optional-label">Optional</span></label>
            <input
              id="branch-email"
              :value="form.email"
              type="email"
              maxlength="254"
              autocomplete="off"
              :aria-invalid="Boolean(fieldErrors.email)"
              aria-describedby="branch-email-error"
              :disabled="submitting"
              @input="setField('email', $event.target.value)"
            />
            <span v-if="fieldErrors.email" id="branch-email-error" class="field-error">
              {{ fieldErrors.email }}
            </span>
          </div>

          <div v-if="editing" class="form-field form-field-wide">
            <span class="field-label">Branch Status</span>
            <p class="status-explanation">
              {{ form.is_active ? 'Active' : 'Inactive' }}. Use the confirmed
              {{ form.is_active ? 'Deactivate' : 'Reactivate' }} action in the list to change status.
            </p>
          </div>

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
              :disabled="submitting || formLoading"
              :aria-busy="submitting"
            >
              {{ submitting ? 'Saving...' : editing ? 'Save Changes' : 'Create Branch' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.branch-page {
  width: min(100%, 1360px);
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
  margin-bottom: 16px;
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
.secondary-button:disabled,
.text-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  color: #435970;
  font-size: 0.8rem;
  font-weight: 700;
}

.filter-row select {
  min-height: 35px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 6px 9px;
  background: #fff;
  color: #25364a;
  font: inherit;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.79rem;
  text-align: left;
}

th,
td {
  border-bottom: 1px solid #e8edf3;
  padding: 11px 9px;
  vertical-align: top;
}

th {
  background: #f6f8fb;
  color: #52657b;
  font-size: 0.69rem;
  font-weight: 700;
  white-space: nowrap;
}

td {
  color: #34485f;
}

.branch-code,
.branch-name {
  color: #173f6d;
  font-weight: 700;
}

.address-cell {
  min-width: 180px;
  max-width: 260px;
  white-space: normal;
}

.status-badge {
  display: inline-flex;
  width: fit-content;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 0.68rem;
  font-weight: 700;
  white-space: nowrap;
}

.status-active {
  background: #e8f5ee;
  color: #237548;
}

.status-inactive {
  background: #f1f3f5;
  color: #53657b;
}

.row-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  min-width: 86px;
}

.text-button {
  border: 0;
  padding: 2px 0;
  background: transparent;
  color: #245b8f;
  font: inherit;
  font-size: 0.75rem;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.text-button:hover:not(:disabled) {
  text-decoration: underline;
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
.error-message,
.form-error {
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

.notice {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  border: 1px solid #b7dfc5;
  border-radius: 8px;
  padding: 11px 13px;
  background: #f0faf3;
  color: #28583a;
  font-size: 0.82rem;
}

.notice p {
  margin: 0;
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

.branch-modal {
  width: min(100%, 720px);
  max-height: min(90vh, 850px);
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
  margin: 0 0 17px;
  color: #5b6e83;
  font-size: 0.83rem;
  line-height: 1.55;
}

.branch-form {
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

.form-field label,
.field-label {
  color: #354b63;
  font-size: 0.78rem;
  font-weight: 700;
}

.form-field label > span {
  color: #b42318;
}

.optional-label {
  margin-left: 4px;
  color: #718096 !important;
  font-size: 0.7rem;
  font-weight: 500;
}

.form-field input,
.form-field textarea {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 9px 10px;
  background: #fff;
  color: #25364a;
  font: inherit;
  font-size: 0.82rem;
}

.form-field input {
  min-height: 40px;
}

.form-field textarea {
  min-height: 85px;
  resize: vertical;
}

.form-field input[readonly] {
  background: #f4f6f9;
  color: #64748b;
}

.form-field input:focus-visible,
.form-field textarea:focus-visible,
.filter-row select:focus-visible,
.primary-button:focus-visible,
.secondary-button:focus-visible,
.text-button:focus-visible,
.dismiss-button:focus-visible,
.back-link:focus-visible {
  outline: 3px solid rgb(13 110 253 / 25%);
  outline-offset: 2px;
}

.form-field input[aria-invalid="true"],
.form-field textarea[aria-invalid="true"] {
  border-color: #b42318;
}

.field-error {
  color: #842029;
  font-size: 0.73rem;
}

.field-hint,
.status-explanation {
  color: #63758a;
  font-size: 0.75rem;
  line-height: 1.45;
}

.status-explanation {
  margin: 0;
}

.form-error {
  margin: 0;
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

@media (max-width: 760px) {
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

  .branch-form {
    grid-template-columns: 1fr;
  }

  .form-field-wide {
    grid-column: auto;
  }

  .modal-backdrop {
    align-items: flex-start;
    padding: 12px;
  }

  .branch-modal {
    max-height: calc(100vh - 24px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 2s;
  }
}
</style>
