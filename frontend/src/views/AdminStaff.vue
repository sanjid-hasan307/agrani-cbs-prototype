<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, onBeforeRouteLeave, useRouter } from 'vue-router'
import api from '../services/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const verifying = ref(true)
const authorized = ref(false)
const verificationError = ref('')
const loading = ref(false)
const error = ref('')
const staffMembers = ref([])
const branches = ref([])
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
const currentStaff = ref(null)
const branchOptionsLoading = ref(false)
const branchOptionsError = ref('')
const submitting = ref(false)
const formError = ref('')
const fieldErrors = ref({})
const notice = ref('')
const form = ref({})
const initialForm = ref({})

const roles = ['Manager', 'Officer', 'Teller', 'Auditor']
const fieldLimits = {
  username: 150,
  password: 256,
  first_name: 150,
  last_name: 150,
  email: 254,
  employee_id: 30,
  designation: 100,
  phone: 20
}

let active = true
let requestController

function emptyForm() {
  return {
    username: '',
    password: '',
    password_confirmation: '',
    first_name: '',
    last_name: '',
    email: '',
    employee_id: '',
    branch: '',
    designation: '',
    phone: '',
    role: ''
  }
}

function clearStaffData() {
  staffMembers.value = []
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
  currentStaff.value = null
  branchOptionsLoading.value = false
  branchOptionsError.value = ''
  branches.value = []
  submitting.value = false
  formError.value = ''
  fieldErrors.value = {}
  form.value = emptyForm()
  initialForm.value = emptyForm()
}

async function redirectToLogin() {
  authorized.value = false
  clearStaffData()
  clearFormData()
  notice.value = ''
  authStore.logout()
  requestController?.abort()
  await router.replace('/login')
}

async function handleAuthorizationFailure(status) {
  if (status !== 401 && status !== 403) return false
  await redirectToLogin()
  return true
}

function isStaffRecord(staff) {
  return Number.isInteger(staff?.id)
    && typeof staff.employee_id === 'string'
    && typeof staff.username === 'string'
    && typeof staff.first_name === 'string'
    && typeof staff.last_name === 'string'
    && typeof staff.email === 'string'
    && (typeof staff.designation === 'string' || staff.designation === null)
    && (typeof staff.phone === 'string' || staff.phone === null)
    && Number.isInteger(staff.branch?.id)
    && typeof staff.branch.branch_code === 'string'
    && typeof staff.branch.branch_name === 'string'
    && (typeof staff.role === 'string' || staff.role === null)
    && typeof staff.user_is_active === 'boolean'
    && typeof staff.profile_is_active === 'boolean'
}

async function loadStaff(page = 1) {
  if (!authorized.value || !active) return

  loading.value = true
  error.value = ''
  clearStaffData()

  try {
    const response = await api.get('/admin/staff/', {
      params: { page },
      signal: requestController.signal
    })
    if (!active) return

    const data = response.data
    const meta = data?.pagination
    if (
      !data?.success
      || !Array.isArray(data.staff)
      || !data.staff.every(isStaffRecord)
      || !Number.isInteger(meta?.page)
      || !Number.isInteger(meta?.page_size)
      || !Number.isInteger(meta?.total_pages)
      || !Number.isInteger(meta?.total_items)
      || typeof meta?.has_previous !== 'boolean'
      || typeof meta?.has_next !== 'boolean'
    ) {
      error.value = 'Staff records could not be loaded. Please try again.'
      return
    }

    staffMembers.value = data.staff
    pagination.value = {
      page: meta.page,
      totalPages: Math.max(1, meta.total_pages),
      totalItems: meta.total_items,
      hasPrevious: meta.has_previous,
      hasNext: meta.has_next
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    clearStaffData()
    if (await handleAuthorizationFailure(requestError.response?.status)) return
    error.value = requestError.response?.status === 400
      ? 'The requested page is invalid. Please refresh the staff list.'
      : 'Unable to load staff records. Please check your connection and try again.'
  } finally {
    if (active) loading.value = false
  }
}

async function verifyAdminSession() {
  requestController?.abort()
  requestController = new AbortController()
  verifying.value = true
  authorized.value = false
  verificationError.value = ''
  error.value = ''
  notice.value = ''
  clearStaffData()
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
    await loadStaff(1)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return

    clearStaffData()
    clearFormData()
    authStore.logout()
    if (requestError.response?.status === 401 || requestError.response?.status === 403) {
      await router.replace('/login')
    } else {
      verificationError.value = 'Unable to verify your Admin session. Please try again.'
    }
  } finally {
    if (active) verifying.value = false
  }
}

async function loadBranchOptions() {
  if (!authorized.value || !active) return

  branchOptionsLoading.value = true
  branchOptionsError.value = ''
  branches.value = []

  try {
    const response = await api.get('/admin/branches/options/', {
      signal: requestController.signal
    })
    if (!active || !formOpen.value) return

    const options = response.data?.branches
    if (
      !response.data?.success
      || !Array.isArray(options)
      || !options.every(branch => (
        Number.isInteger(branch?.id)
        && typeof branch.branch_code === 'string'
        && typeof branch.branch_name === 'string'
      ))
    ) {
      branchOptionsError.value = 'Active branch options could not be loaded. Please retry.'
      return
    }

    branches.value = options
    if (!branches.value.length) {
      branchOptionsError.value = 'No active branches are available for staff assignment.'
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return
    branchOptionsError.value = 'Unable to load active branches. Check your connection and retry.'
  } finally {
    if (active) branchOptionsLoading.value = false
  }
}

function openCreateForm() {
  if (!authorized.value || submitting.value || loading.value) return
  clearFormData()
  formOpen.value = true
  loadBranchOptions()
}

function openEditForm(staff) {
  if (!authorized.value || submitting.value || loading.value) return
  clearFormData()
  formOpen.value = true
  editing.value = true
  editingId.value = staff.id
  currentStaff.value = staff
  const values = {
    ...emptyForm(),
    first_name: staff.first_name,
    last_name: staff.last_name,
    email: staff.email,
    branch: String(staff.branch.id),
    designation: staff.designation || '',
    phone: staff.phone || '',
    role: roles.includes(staff.role) ? staff.role : ''
  }
  form.value = { ...values }
  initialForm.value = { ...values }
  loadBranchOptions()
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

function validateForm() {
  const values = form.value
  const errors = {}

  if (!editing.value) {
    if (!values.username.trim()) errors.username = 'Username is required.'
    if (!values.password) errors.password = 'Password is required.'
    if (!values.employee_id.trim()) errors.employee_id = 'Employee ID is required.'
    if (!values.branch) errors.branch = 'Select an active branch.'
    if (!values.role) errors.role = 'Select a banking role.'
    if (values.password !== values.password_confirmation) {
      errors.password_confirmation = 'Passwords do not match.'
    }
  }

  for (const [field, maxLength] of Object.entries(fieldLimits)) {
    if (values[field].length > maxLength) {
      errors[field] = `Must be ${maxLength} characters or fewer.`
    }
  }
  if (values.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = 'Enter a valid email address.'
  }
  if (values.role && !roles.includes(values.role)) {
    errors.role = 'Select one of the permitted banking roles.'
  }
  const branchChanged = editing.value
    && values.branch !== initialForm.value.branch
  if (branchChanged && !values.branch) {
    errors.branch = 'Select an active branch.'
  }
  if (
    (values.branch && (!editing.value || branchChanged))
    && !branches.value.some(branch => branch.id === Number(values.branch))
  ) {
    errors.branch = 'Select an active branch.'
  }

  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}

function closeForm() {
  if (submitting.value) return
  clearFormData()
}

function createPayload() {
  return {
    username: form.value.username.trim(),
    password: form.value.password,
    first_name: form.value.first_name.trim(),
    last_name: form.value.last_name.trim(),
    email: form.value.email.trim(),
    employee_id: form.value.employee_id.trim(),
    branch: Number(form.value.branch),
    designation: form.value.designation.trim(),
    phone: form.value.phone.trim(),
    role: form.value.role
  }
}

function updatePayload() {
  const payload = {}
  for (const field of [
    'first_name',
    'last_name',
    'email',
    'designation',
    'phone'
  ]) {
    if (form.value[field] !== initialForm.value[field]) {
      payload[field] = form.value[field].trim()
    }
  }
  if (form.value.branch !== initialForm.value.branch) {
    payload.branch = Number(form.value.branch)
  }
  if (form.value.role && form.value.role !== initialForm.value.role) {
    payload.role = form.value.role
  }
  return payload
}

function setServerFieldErrors(data) {
  const allowedFields = new Set([
    'username',
    'password',
    'first_name',
    'last_name',
    'email',
    'employee_id',
    'branch',
    'designation',
    'phone',
    'role'
  ])
  const errors = data?.errors
  if (!errors || typeof errors !== 'object') return

  fieldErrors.value = Object.fromEntries(
    Object.keys(errors)
      .filter(field => allowedFields.has(field))
      .map(field => [field, 'Please check this field.'])
  )
}

async function submitForm() {
  if (
    submitting.value
    || branchOptionsLoading.value
    || !formOpen.value
    || !validateForm()
  ) return

  submitting.value = true
  formError.value = ''
  const payload = editing.value ? updatePayload() : createPayload()
  if (editing.value && !Object.keys(payload).length) {
    formError.value = 'Make at least one change before saving.'
    submitting.value = false
    return
  }

  try {
    const response = editing.value
      ? await api.patch(`/admin/staff/${editingId.value}/`, payload, {
          signal: requestController.signal
        })
      : await api.post('/admin/staff/', payload, {
          signal: requestController.signal
        })
    if (!active) return

    if (!response.data?.success || !isStaffRecord(response.data.staff)) {
      formError.value = 'Staff details could not be saved. Please try again.'
      return
    }

    const savedStaff = response.data.staff
    notice.value = editing.value
      ? `Staff profile ${savedStaff.employee_id} was updated successfully.`
      : `Staff profile ${savedStaff.employee_id} was created successfully.`
    clearFormData()
    await loadStaff(pagination.value.page)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return

    const status = requestError.response?.status
    if (status === 400) {
      setServerFieldErrors(requestError.response?.data)
      formError.value = 'Staff details were rejected. Review the fields and try again.'
    } else if (status === 404) {
      formError.value = 'This staff profile no longer exists. Refresh the list and try again.'
    } else if (status === 409) {
      formError.value = 'The username or employee ID is already in use.'
    } else if (status === 413) {
      formError.value = 'The request is too large. Shorten the entered values and try again.'
    } else {
      formError.value = 'Unable to save staff details. Please check your connection and retry.'
    }
  } finally {
    if (active) submitting.value = false
  }
}

async function changeStaffStatus(staff) {
  if (submitting.value || !authorized.value) return

  const shouldActivate = !staff.user_is_active || !staff.profile_is_active
  const action = shouldActivate ? 'activate' : 'deactivate'
  const explanation = shouldActivate
    ? ' Activation requires the assigned branch to be active and an approved banking role to be assigned.'
    : ' Deactivation sets both the Django User and StaffProfile active flags to inactive. Existing sessions are not guaranteed to be revoked immediately.'
  if (!window.confirm(`Are you sure you want to ${action} ${staff.employee_id}?${explanation}`)) {
    return
  }

  submitting.value = true
  error.value = ''
  try {
    const response = await api.post(
      `/admin/staff/${staff.id}/${action}/`,
      {},
      { signal: requestController.signal }
    )
    if (!active) return

    const updatedStaff = response.data?.staff
    if (
      !response.data?.success
      || !isStaffRecord(updatedStaff)
      || updatedStaff.user_is_active !== shouldActivate
      || updatedStaff.profile_is_active !== shouldActivate
    ) {
      error.value = 'Staff status could not be changed. Please try again.'
      return
    }

    notice.value = `Staff profile ${staff.employee_id} was ${shouldActivate ? 'activated' : 'deactivated'}.`
    await loadStaff(pagination.value.page)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleAuthorizationFailure(requestError.response?.status)) return

    const status = requestError.response?.status
    if (status === 400 && shouldActivate) {
      error.value = 'Activation was rejected. Confirm the assigned branch is active and an approved banking role is set.'
    } else if (status === 404) {
      error.value = 'This staff profile no longer exists. Refresh the staff list.'
    } else if (status === 409) {
      error.value = 'The staff status change conflicts with the current profile. Refresh and retry.'
    } else {
      error.value = 'Unable to change staff status. Please check your connection and retry.'
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
    || submitting.value
  ) return
  loadStaff(page)
}

function displayName(staff) {
  return [staff.first_name, staff.last_name].filter(Boolean).join(' ') || '—'
}

function displayRole(role) {
  if (!role) return 'Not assigned'
  if (role === 'CONFLICT') return 'Role conflict'
  return role
}

onBeforeRouteLeave(() => {
  clearStaffData()
  clearFormData()
  active = false
  requestController?.abort()
})

onMounted(verifyAdminSession)

onBeforeUnmount(() => {
  active = false
  requestController?.abort()
  clearStaffData()
  clearFormData()
})
</script>

<template>
  <section class="admin-staff">
    <div v-if="verifying" class="state-card" role="status">
      <span class="spinner" aria-hidden="true"></span>
      Verifying your Admin session...
    </div>

    <div v-else-if="!authorized" class="state-card error-card" role="alert">
      <p>{{ verificationError || 'An Admin session is required to view staff records.' }}</p>
      <button class="secondary-button" type="button" @click="verifyAdminSession">
        Retry
      </button>
    </div>

    <div v-else class="page-content">
      <header class="page-heading">
        <div>
          <p class="eyebrow">CBS Administration</p>
          <h1>Staff Management</h1>
        </div>
        <RouterLink class="back-link" to="/dashboard/admin">
          <span aria-hidden="true">←</span>
          Back to Admin Dashboard
        </RouterLink>
      </header>

      <section class="list-card" aria-labelledby="staff-list-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Staff records</p>
            <h2 id="staff-list-heading">Staff List</h2>
          </div>
          <div class="list-actions">
            <span class="record-count">{{ pagination.totalItems }} records</span>
            <button
              class="primary-button"
              type="button"
              :disabled="loading || submitting"
              @click="openCreateForm"
            >
              Add New Staff
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

        <p class="status-guidance">
          Deactivation updates both the User and Staff Profile active flags. Existing
          sessions are not guaranteed to be revoked immediately. Activation requires
          the assigned branch to be active.
        </p>

        <div v-if="loading" class="inline-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading staff records...
        </div>

        <div v-else-if="error" class="inline-state error-message" role="alert">
          <p>{{ error }}</p>
          <button class="secondary-button" type="button" @click="loadStaff(pagination.page)">
            Retry
          </button>
        </div>

        <div v-else-if="staffMembers.length === 0" class="empty-state" role="status">
          <h3>No staff records found</h3>
          <p>Add a managed staff profile to get started.</p>
        </div>

        <template v-else>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Employee ID</th>
                  <th scope="col">Username</th>
                  <th scope="col">Staff Name</th>
                  <th scope="col">Designation</th>
                  <th scope="col">Banking Role</th>
                  <th scope="col">Branch</th>
                  <th scope="col">User Status</th>
                  <th scope="col">Profile Status</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="staff in staffMembers" :key="staff.id">
                  <td class="employee-id">{{ staff.employee_id }}</td>
                  <td>{{ staff.username }}</td>
                  <td>{{ displayName(staff) }}</td>
                  <td>{{ staff.designation || '—' }}</td>
                  <td>{{ displayRole(staff.role) }}</td>
                  <td class="branch-cell">
                    <span>{{ staff.branch.branch_code }}</span>
                    <span>{{ staff.branch.branch_name }}</span>
                  </td>
                  <td>
                    <span
                      class="status-badge"
                      :class="staff.user_is_active ? 'status-active' : 'status-inactive'"
                    >
                      {{ staff.user_is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td>
                    <span
                      class="status-badge"
                      :class="staff.profile_is_active ? 'status-active' : 'status-inactive'"
                    >
                      {{ staff.profile_is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td>
                    <div class="row-actions">
                      <button
                        class="text-button"
                        type="button"
                        :disabled="submitting || loading"
                        @click="openEditForm(staff)"
                      >
                        Edit
                      </button>
                      <button
                        class="text-button"
                        type="button"
                        :disabled="submitting || loading"
                        @click="changeStaffStatus(staff)"
                      >
                        {{ staff.user_is_active && staff.profile_is_active ? 'Deactivate' : 'Activate' }}
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <nav class="pagination" aria-label="Staff list pagination">
            <button
              class="secondary-button"
              type="button"
              :disabled="loading || submitting || !pagination.hasPrevious"
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
              :disabled="loading || submitting || !pagination.hasNext"
              @click="changePage(pagination.page + 1)"
            >
              Next
            </button>
          </nav>
        </template>
      </section>

      <section
        v-if="formOpen"
        class="form-card"
        aria-labelledby="staff-form-heading"
      >
        <header class="section-heading form-heading">
          <div>
            <p class="eyebrow">{{ editing ? 'Staff profile' : 'Staff setup' }}</p>
            <h2 id="staff-form-heading">
              {{ editing ? 'Edit Staff' : 'Add New Staff' }}
            </h2>
          </div>
          <button
            class="dismiss-button"
            type="button"
            aria-label="Cancel and close staff form"
            :disabled="submitting"
            @click="closeForm"
          >
            ×
          </button>
        </header>

        <p v-if="editing && currentStaff" class="immutable-details">
          Username: <strong>{{ currentStaff.username }}</strong>
          <span aria-hidden="true"> · </span>
          Employee ID: <strong>{{ currentStaff.employee_id }}</strong>
          <span> (these fields cannot be changed)</span>
        </p>
        <p v-else class="form-intro">
          Username, password, employee ID, active branch, and one permitted banking
          role are required. The Admin role and Django permission settings are not
          available here.
        </p>

        <div v-if="branchOptionsLoading" class="inline-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading active branches...
        </div>
        <div v-else-if="branchOptionsError" class="inline-state error-message" role="alert">
          <p>{{ branchOptionsError }}</p>
          <button class="secondary-button" type="button" @click="loadBranchOptions">
            Retry
          </button>
        </div>

        <form class="staff-form" novalidate @submit.prevent="submitForm">
          <div v-if="!editing" class="field">
            <label for="staff-username">Username <span aria-hidden="true">*</span></label>
            <input
              id="staff-username"
              :value="form.username"
              type="text"
              autocomplete="off"
              maxlength="150"
              required
              :aria-invalid="Boolean(fieldErrors.username)"
              :aria-describedby="fieldErrors.username ? 'staff-username-error' : undefined"
              :disabled="submitting"
              @input="setField('username', $event.target.value)"
            >
            <span v-if="fieldErrors.username" id="staff-username-error" class="field-error">
              {{ fieldErrors.username }}
            </span>
          </div>

          <div v-if="!editing" class="field">
            <label for="staff-password">Password <span aria-hidden="true">*</span></label>
            <input
              id="staff-password"
              :value="form.password"
              type="password"
              autocomplete="new-password"
              maxlength="256"
              required
              :aria-invalid="Boolean(fieldErrors.password)"
              :aria-describedby="fieldErrors.password ? 'staff-password-error' : undefined"
              :disabled="submitting"
              @input="setField('password', $event.target.value)"
            >
            <span v-if="fieldErrors.password" id="staff-password-error" class="field-error">
              {{ fieldErrors.password }}
            </span>
          </div>

          <div v-if="!editing" class="field">
            <label for="staff-password-confirmation">
              Confirm password <span aria-hidden="true">*</span>
            </label>
            <input
              id="staff-password-confirmation"
              :value="form.password_confirmation"
              type="password"
              autocomplete="new-password"
              maxlength="256"
              required
              :aria-invalid="Boolean(fieldErrors.password_confirmation)"
              :aria-describedby="fieldErrors.password_confirmation ? 'staff-password-confirmation-error' : undefined"
              :disabled="submitting"
              @input="setField('password_confirmation', $event.target.value)"
            >
            <span
              v-if="fieldErrors.password_confirmation"
              id="staff-password-confirmation-error"
              class="field-error"
            >
              {{ fieldErrors.password_confirmation }}
            </span>
          </div>

          <div v-if="!editing" class="field">
            <label for="staff-employee-id">Employee ID <span aria-hidden="true">*</span></label>
            <input
              id="staff-employee-id"
              :value="form.employee_id"
              type="text"
              maxlength="30"
              required
              :aria-invalid="Boolean(fieldErrors.employee_id)"
              :aria-describedby="fieldErrors.employee_id ? 'staff-employee-id-error' : undefined"
              :disabled="submitting"
              @input="setField('employee_id', $event.target.value)"
            >
            <span v-if="fieldErrors.employee_id" id="staff-employee-id-error" class="field-error">
              {{ fieldErrors.employee_id }}
            </span>
          </div>

          <div class="field">
            <label for="staff-first-name">First name</label>
            <input
              id="staff-first-name"
              :value="form.first_name"
              type="text"
              autocomplete="given-name"
              maxlength="150"
              :aria-invalid="Boolean(fieldErrors.first_name)"
              :aria-describedby="fieldErrors.first_name ? 'staff-first-name-error' : undefined"
              :disabled="submitting"
              @input="setField('first_name', $event.target.value)"
            >
            <span v-if="fieldErrors.first_name" id="staff-first-name-error" class="field-error">
              {{ fieldErrors.first_name }}
            </span>
          </div>

          <div class="field">
            <label for="staff-last-name">Last name</label>
            <input
              id="staff-last-name"
              :value="form.last_name"
              type="text"
              autocomplete="family-name"
              maxlength="150"
              :aria-invalid="Boolean(fieldErrors.last_name)"
              :aria-describedby="fieldErrors.last_name ? 'staff-last-name-error' : undefined"
              :disabled="submitting"
              @input="setField('last_name', $event.target.value)"
            >
            <span v-if="fieldErrors.last_name" id="staff-last-name-error" class="field-error">
              {{ fieldErrors.last_name }}
            </span>
          </div>

          <div class="field">
            <label for="staff-email">Email</label>
            <input
              id="staff-email"
              :value="form.email"
              type="email"
              autocomplete="email"
              maxlength="254"
              :aria-invalid="Boolean(fieldErrors.email)"
              :aria-describedby="fieldErrors.email ? 'staff-email-error' : undefined"
              :disabled="submitting"
              @input="setField('email', $event.target.value)"
            >
            <span v-if="fieldErrors.email" id="staff-email-error" class="field-error">
              {{ fieldErrors.email }}
            </span>
          </div>

          <div class="field">
            <label for="staff-branch">Active branch <span v-if="!editing" aria-hidden="true">*</span></label>
            <select
              id="staff-branch"
              :value="form.branch"
              :required="!editing"
              :aria-invalid="Boolean(fieldErrors.branch)"
              :aria-describedby="fieldErrors.branch ? 'staff-branch-error' : undefined"
              :disabled="submitting || branchOptionsLoading || (Boolean(branchOptionsError) && !editing)"
              @change="setField('branch', $event.target.value)"
            >
              <option value="">Select an active branch</option>
              <option
                v-if="editing && currentStaff && !branches.some(branch => branch.id === currentStaff.branch.id)"
                :value="String(currentStaff.branch.id)"
                disabled
              >
                {{ currentStaff.branch.branch_code }} — {{ currentStaff.branch.branch_name }} (current assignment)
              </option>
              <option
                v-for="branch in branches"
                :key="branch.id"
                :value="String(branch.id)"
              >
                {{ branch.branch_code }} — {{ branch.branch_name }}
              </option>
            </select>
            <span v-if="fieldErrors.branch" id="staff-branch-error" class="field-error">
              {{ fieldErrors.branch }}
            </span>
          </div>

          <div class="field">
            <label for="staff-designation">Designation</label>
            <input
              id="staff-designation"
              :value="form.designation"
              type="text"
              maxlength="100"
              :aria-invalid="Boolean(fieldErrors.designation)"
              :aria-describedby="fieldErrors.designation ? 'staff-designation-error' : undefined"
              :disabled="submitting"
              @input="setField('designation', $event.target.value)"
            >
            <span v-if="fieldErrors.designation" id="staff-designation-error" class="field-error">
              {{ fieldErrors.designation }}
            </span>
          </div>

          <div class="field">
            <label for="staff-phone">Phone</label>
            <input
              id="staff-phone"
              :value="form.phone"
              type="tel"
              autocomplete="tel"
              maxlength="20"
              :aria-invalid="Boolean(fieldErrors.phone)"
              :aria-describedby="fieldErrors.phone ? 'staff-phone-error' : undefined"
              :disabled="submitting"
              @input="setField('phone', $event.target.value)"
            >
            <span v-if="fieldErrors.phone" id="staff-phone-error" class="field-error">
              {{ fieldErrors.phone }}
            </span>
          </div>

          <div class="field">
            <label for="staff-role">Banking role <span v-if="!editing" aria-hidden="true">*</span></label>
            <select
              id="staff-role"
              :value="form.role"
              :required="!editing"
              :aria-invalid="Boolean(fieldErrors.role)"
              :aria-describedby="fieldErrors.role ? 'staff-role-error' : undefined"
              :disabled="submitting"
              @change="setField('role', $event.target.value)"
            >
              <option value="">Select a banking role</option>
              <option v-for="role in roles" :key="role" :value="role">{{ role }}</option>
            </select>
            <span v-if="fieldErrors.role" id="staff-role-error" class="field-error">
              {{ fieldErrors.role }}
            </span>
          </div>

          <div v-if="formError" class="form-error" role="alert">
            {{ formError }}
          </div>

          <div class="form-actions">
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
              :disabled="submitting || branchOptionsLoading || (Boolean(branchOptionsError) && !editing)"
              :aria-busy="submitting"
            >
              {{ submitting ? 'Saving...' : editing ? 'Save Changes' : 'Create Staff' }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.admin-staff {
  width: min(100%, 1380px);
  margin: 0 auto;
  padding: 32px clamp(16px, 4vw, 40px);
  color: #25364a;
}

.page-content {
  display: grid;
  gap: 20px;
}

.page-heading,
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
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
  font-size: 0.84rem;
  font-weight: 700;
  text-decoration: none;
}

.back-link:hover,
.back-link:focus-visible {
  text-decoration: underline;
}

.back-link:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible {
  outline: 3px solid rgb(13 110 253 / 25%);
  outline-offset: 2px;
}

.list-card,
.form-card,
.state-card {
  border: 1px solid #e3e9f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 4px 14px rgb(26 52 82 / 5%);
}

.list-card,
.form-card {
  padding: 20px;
}

.section-heading h2 {
  margin: 0;
  color: #173f6d;
  font-size: 1.05rem;
}

.list-actions,
.form-actions,
.row-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.record-count {
  color: #63758a;
  font-size: 0.82rem;
  white-space: nowrap;
}

.primary-button,
.secondary-button {
  min-height: 36px;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 7px 12px;
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
  border-color: #cbd6e2;
  background: #fff;
  color: #344b63;
}

.secondary-button:hover:not(:disabled) {
  background: #f3f6f9;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.notice {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin: 18px 0;
  border: 1px solid #badbcc;
  border-radius: 7px;
  padding: 10px 12px;
  background: #d1e7dd;
  color: #0f5132;
  font-size: 0.84rem;
}

.notice p {
  margin: 0;
}

.dismiss-button {
  border: 0;
  padding: 0 3px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
}

.status-guidance,
.form-intro,
.immutable-details {
  margin: 16px 0;
  color: #63758a;
  font-size: 0.83rem;
  line-height: 1.55;
}

.status-guidance {
  border-left: 3px solid #9bbce0;
  padding: 8px 11px;
  background: #f4f8fc;
}

.immutable-details strong {
  color: #344b63;
}

.table-scroll {
  overflow-x: auto;
  margin-top: 12px;
  border: 1px solid #e3e9f0;
  border-radius: 7px;
}

table {
  width: 100%;
  min-width: 1030px;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.8rem;
}

th,
td {
  border-bottom: 1px solid #e8edf2;
  padding: 11px 12px;
  vertical-align: middle;
}

th {
  background: #f5f8fb;
  color: #52657a;
  font-size: 0.72rem;
  font-weight: 700;
  white-space: nowrap;
}

tbody tr:last-child td {
  border-bottom: 0;
}

.employee-id {
  color: #173f6d;
  font-weight: 700;
  white-space: nowrap;
}

.branch-cell {
  min-width: 150px;
}

.branch-cell span {
  display: block;
}

.branch-cell span:first-child {
  color: #344b63;
  font-weight: 700;
}

.branch-cell span:last-child {
  margin-top: 3px;
  color: #63758a;
  font-size: 0.73rem;
}

.status-badge {
  display: inline-flex;
  width: fit-content;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 0.7rem;
  font-weight: 700;
}

.status-active {
  background: #d1e7dd;
  color: #0f5132;
}

.status-inactive {
  background: #f8d7da;
  color: #842029;
}

.row-actions {
  gap: 8px;
  white-space: nowrap;
}

.text-button {
  border: 0;
  padding: 4px 0;
  background: transparent;
  color: #245b8f;
  font: inherit;
  font-size: 0.77rem;
  font-weight: 700;
  cursor: pointer;
}

.text-button:hover:not(:disabled) {
  text-decoration: underline;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
  color: #53657b;
  font-size: 0.82rem;
}

.inline-state,
.empty-state {
  display: flex;
  min-height: 110px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px;
  color: #63758a;
  font-size: 0.88rem;
  text-align: center;
}

.inline-state p,
.empty-state p {
  margin: 0;
}

.empty-state h3 {
  margin: 0;
  color: #344b63;
  font-size: 1rem;
}

.error-message,
.form-error {
  color: #842029;
}

.form-error {
  grid-column: 1 / -1;
  border: 1px solid #f1c2c7;
  border-radius: 6px;
  padding: 10px 12px;
  background: #f8d7da;
  font-size: 0.83rem;
}

.form-heading {
  margin-bottom: 8px;
}

.staff-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.field label {
  color: #344b63;
  font-size: 0.8rem;
  font-weight: 700;
}

.field label span {
  color: #b02a37;
}

.field input,
.field select {
  width: 100%;
  min-height: 39px;
  border: 1px solid #cbd6e2;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fff;
  color: #25364a;
  font: inherit;
  font-size: 0.84rem;
}

.field input:disabled,
.field select:disabled {
  background: #f1f3f5;
}

.field-error {
  color: #842029;
  font-size: 0.75rem;
}

.form-actions {
  grid-column: 1 / -1;
  justify-content: flex-end;
  border-top: 1px solid #e8edf2;
  padding-top: 14px;
}

.state-card {
  display: flex;
  min-height: 150px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 20px;
  color: #53657b;
  font-size: 0.9rem;
  text-align: center;
}

.state-card p {
  margin: 0;
}

.error-card {
  border-color: #f1c2c7;
  color: #842029;
}

.spinner {
  width: 22px;
  height: 22px;
  border: 3px solid #dce5ef;
  border-top-color: #0d6efd;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 700px) {
  .admin-staff {
    padding-top: 22px;
  }

  .page-heading,
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .list-actions {
    width: 100%;
    justify-content: space-between;
  }

  .list-card,
  .form-card {
    padding: 15px;
  }

  .staff-form {
    grid-template-columns: 1fr;
  }

  .form-actions {
    grid-column: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 2s;
  }
}
</style>
