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
const searchInput = ref('')
const submittedSearch = ref('')
const customers = ref([])
const registrationOpen = ref(false)
const branchesLoading = ref(false)
const branches = ref([])
const branchError = ref('')
const submitting = ref(false)
const registrationError = ref('')
const fieldErrors = ref({})
const registrationConfirmation = ref(null)
const registrationForm = ref({})
const pagination = ref({
  page: 1,
  totalPages: 1,
  totalItems: 0,
  hasPrevious: false,
  hasNext: false
})

let active = true
let requestController

const registrationFieldLimits = {
  full_name: 150,
  phone: 20,
  email: 254,
  nid_number: 30,
  passport_number: 30,
  present_address: 5000,
  permanent_address: 5000,
  district: 100,
  nominee_name: 150,
  nominee_relationship: 50,
  nominee_phone: 20
}

function resetRegistrationForm() {
  registrationForm.value = {
    customer_type: 'INDIVIDUAL',
    full_name: '',
    phone: '',
    email: '',
    date_of_birth: '',
    gender: '',
    nid_number: '',
    passport_number: '',
    present_address: '',
    permanent_address: '',
    district: '',
    home_branch: '',
    nominee_name: '',
    nominee_relationship: '',
    nominee_phone: ''
  }
}

resetRegistrationForm()

function clearCustomerData() {
  customers.value = []
  pagination.value = {
    page: 1,
    totalPages: 1,
    totalItems: 0,
    hasPrevious: false,
    hasNext: false
  }
}

function clearRegistrationData() {
  registrationOpen.value = false
  branchesLoading.value = false
  branches.value = []
  branchError.value = ''
  submitting.value = false
  registrationError.value = ''
  fieldErrors.value = {}
  registrationConfirmation.value = null
  resetRegistrationForm()
}

async function redirectToLogin() {
  authorized.value = false
  clearCustomerData()
  clearRegistrationData()
  authStore.logout()
  await router.replace('/login')
}

async function loadCustomers(page = 1) {
  if (!authorized.value || !active) return

  loading.value = true
  error.value = ''
  clearCustomerData()

  try {
    const response = await api.get('/admin/customers/', {
      params: {
        page,
        ...(submittedSearch.value ? { search: submittedSearch.value } : {})
      },
      signal: requestController.signal
    })

    if (!active) return

    const data = response.data
    if (!data?.success || !Array.isArray(data.customers) || !data.pagination) {
      error.value = 'Customer records could not be loaded. Please try again.'
      return
    }

    customers.value = data.customers
    pagination.value = {
      page: data.pagination.page,
      totalPages: data.pagination.total_pages,
      totalItems: data.pagination.total_items,
      hasPrevious: data.pagination.has_previous,
      hasNext: data.pagination.has_next
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return

    clearCustomerData()
    const status = requestError.response?.status
    if (status === 401 || status === 403) {
      await redirectToLogin()
    } else if (status === 400) {
      error.value = 'The search could not be completed. Please use a shorter search and try again.'
    } else {
      error.value = 'Unable to load customer records. Please check your connection and try again.'
    }
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
  clearCustomerData()
  clearRegistrationData()

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
    await loadCustomers(1)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return

    clearCustomerData()
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

function validateRegistrationForm() {
  const form = registrationForm.value
  const errors = {}
  const requiredFields = [
    ['full_name', 'Full name'],
    ['phone', 'Phone'],
    ['present_address', 'Present address'],
    ['district', 'District']
  ]

  for (const [field, label] of requiredFields) {
    if (!form[field].trim()) errors[field] = `${label} is required.`
  }

  if (!['INDIVIDUAL', 'ORGANIZATION'].includes(form.customer_type)) {
    errors.customer_type = 'Select a supported customer type.'
  }
  if (form.customer_type === 'INDIVIDUAL'
    && !form.nid_number.trim()
    && !form.passport_number.trim()) {
    errors.nid_number = 'Enter an NID or passport number for an individual.'
    errors.passport_number = 'Enter an NID or passport number for an individual.'
  }
  if (!form.home_branch || !branches.value.some(
    branch => branch.id === Number(form.home_branch)
  )) {
    errors.home_branch = 'Select an active home branch.'
  }

  for (const [field, maxLength] of Object.entries(registrationFieldLimits)) {
    if (form[field].length > maxLength) {
      errors[field] = `Must be ${maxLength} characters or fewer.`
    }
  }

  if (form.email.trim()) {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailPattern.test(form.email.trim())) {
      errors.email = 'Enter a valid email address.'
    }
  }
  if (form.gender && !['MALE', 'FEMALE', 'OTHER'].includes(form.gender)) {
    errors.gender = 'Select a supported gender.'
  }
  if (form.date_of_birth) {
    const todayString = todayLocalIso()
    if (!isValidIsoDate(form.date_of_birth)) {
      errors.date_of_birth = 'Enter a valid date in YYYY-MM-DD format.'
    } else if (form.date_of_birth > todayString) {
      errors.date_of_birth = 'Date of birth cannot be in the future.'
    }
  }

  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}

function isValidIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false

  const [year, month, day] = value.split('-').map(Number)
  if (year < 1 || month < 1 || month > 12) return false
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const daysByMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  return day >= 1 && day <= daysByMonth[month - 1]
}

function todayLocalIso() {
  const today = new Date()
  return [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, '0'),
    String(today.getDate()).padStart(2, '0')
  ].join('-')
}

function setRegistrationField(field, value) {
  registrationForm.value[field] = value
  if (fieldErrors.value[field]) {
    const updatedErrors = { ...fieldErrors.value }
    delete updatedErrors[field]
    fieldErrors.value = updatedErrors
  }
  if (
    ['nid_number', 'passport_number'].includes(field)
    && registrationForm.value.customer_type === 'INDIVIDUAL'
    && (
      registrationForm.value.nid_number.trim()
      || registrationForm.value.passport_number.trim()
    )
  ) {
    const updatedErrors = { ...fieldErrors.value }
    delete updatedErrors.nid_number
    delete updatedErrors.passport_number
    fieldErrors.value = updatedErrors
  }
  if (field === 'customer_type' && value === 'ORGANIZATION') {
    const updatedErrors = { ...fieldErrors.value }
    delete updatedErrors.nid_number
    delete updatedErrors.passport_number
    fieldErrors.value = updatedErrors
  }
  registrationError.value = ''
}

async function handleRegistrationAuthorizationFailure(status) {
  if (status !== 401 && status !== 403) return false
  await redirectToLogin()
  return true
}

async function openRegistration() {
  if (!authorized.value || submitting.value) return
  resetRegistrationForm()
  fieldErrors.value = {}
  registrationError.value = ''
  registrationConfirmation.value = null
  branchError.value = ''
  branches.value = []
  registrationOpen.value = true
  branchesLoading.value = true

  try {
    const response = await api.get('/admin/branches/options/', {
      signal: requestController.signal
    })
    if (!active || !registrationOpen.value) return

    if (!response.data?.success || !Array.isArray(response.data.branches)) {
      branchError.value = 'Unable to load active branches. Please try again.'
      return
    }

    branches.value = response.data.branches.filter(branch => (
      Number.isInteger(branch.id)
      && branch.id > 0
      && typeof branch.branch_code === 'string'
      && typeof branch.branch_name === 'string'
    ))
    if (branches.value.length === 0) {
      branchError.value = 'No active branches are available for customer registration.'
    }
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleRegistrationAuthorizationFailure(requestError.response?.status)) return
    branchError.value = 'Unable to load active branches. Please check your connection and retry.'
  } finally {
    if (active) branchesLoading.value = false
  }
}

function closeRegistration() {
  if (submitting.value) return
  clearRegistrationData()
}

async function submitRegistration() {
  if (submitting.value || branchesLoading.value || !validateRegistrationForm()) return

  const form = registrationForm.value
  let payload = {
    customer_type: form.customer_type,
    full_name: form.full_name.trim(),
    phone: form.phone.trim(),
    email: form.email.trim(),
    date_of_birth: form.date_of_birth || null,
    gender: form.gender,
    nid_number: form.nid_number.trim(),
    passport_number: form.passport_number.trim(),
    present_address: form.present_address.trim(),
    permanent_address: form.permanent_address.trim(),
    district: form.district.trim(),
    home_branch: Number(form.home_branch),
    nominee_name: form.nominee_name.trim(),
    nominee_relationship: form.nominee_relationship.trim(),
    nominee_phone: form.nominee_phone.trim()
  }

  submitting.value = true
  registrationError.value = ''
  fieldErrors.value = {}
  try {
    const response = await api.post('/admin/customers/', payload, {
      signal: requestController.signal
    })
    if (!active) return

    const customer = response.data?.customer
    if (
      response.status !== 201
      || !response.data?.success
      || !Number.isInteger(customer?.id)
      || typeof customer?.cif_number !== 'string'
      || typeof customer?.full_name !== 'string'
      || typeof customer?.home_branch !== 'string'
      || customer?.kyc_status !== 'PENDING'
    ) {
      registrationError.value = 'The customer could not be registered. Please try again.'
      return
    }

    payload = null
    clearRegistrationData()
    registrationConfirmation.value = {
      id: customer.id,
      cif_number: customer.cif_number,
      full_name: customer.full_name,
      home_branch: customer.home_branch,
      kyc_status: customer.kyc_status
    }
    await loadCustomers(1)
  } catch (requestError) {
    if (!active || requestError.code === 'ERR_CANCELED') return
    if (await handleRegistrationAuthorizationFailure(requestError.response?.status)) return

    const status = requestError.response?.status
    if (status === 400) {
      const serverErrors = requestError.response?.data?.errors
      if (serverErrors && typeof serverErrors === 'object') {
        fieldErrors.value = Object.fromEntries(
          Object.keys(serverErrors).map(field => [field, 'Please check this field.'])
        )
      }
      registrationError.value = 'Please review the highlighted fields and try again.'
    } else if (status === 409) {
      registrationError.value = 'A customer with one of the supplied identity documents already exists. Please verify the details and try again.'
    } else if (status === 413) {
      registrationError.value = 'The registration details are too large. Please shorten the address fields and try again.'
    } else {
      registrationError.value = 'Unable to register the customer. Please check your connection and try again.'
    }
  } finally {
    if (active) submitting.value = false
  }
}

function dismissRegistrationConfirmation() {
  registrationConfirmation.value = null
}

function submitSearch() {
  submittedSearch.value = searchInput.value.trim()
  loadCustomers(1)
}

function changePage(page) {
  if (page < 1 || page > pagination.value.totalPages || loading.value) return
  loadCustomers(page)
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('en-BD', {
    dateStyle: 'medium',
    timeZone: 'Asia/Dhaka'
  }).format(date)
}

onMounted(() => {
  verifyAdminSession()
})

onBeforeUnmount(() => {
  active = false
  requestController?.abort()
  clearCustomerData()
  clearRegistrationData()
})
</script>

<template>
  <section class="customer-page">
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
          <h1>Customer Management</h1>
        </div>
        <RouterLink class="back-link" to="/dashboard/admin">
          <span aria-hidden="true">←</span>
          Back to Admin Dashboard
        </RouterLink>
      </div>

      <section class="list-card" aria-labelledby="customer-list-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Customer records</p>
            <h2 id="customer-list-heading">Customer List</h2>
          </div>
          <div class="list-actions">
            <span class="record-count">{{ pagination.totalItems }} records</span>
            <button class="primary-button" type="button" @click="openRegistration">
              Register New Customer
            </button>
          </div>
        </div>

        <section
          v-if="registrationConfirmation"
          class="confirmation-card"
          aria-live="polite"
          aria-labelledby="registration-confirmation-title"
        >
          <div>
            <p class="eyebrow">Registration complete</p>
            <h3 id="registration-confirmation-title">Customer registered successfully</h3>
            <p>
              {{ registrationConfirmation.full_name }}
              <span aria-hidden="true">·</span>
              CIF {{ registrationConfirmation.cif_number }}
              <span aria-hidden="true">·</span>
              Customer ID {{ registrationConfirmation.id }}
            </p>
            <p>
              Home branch: {{ registrationConfirmation.home_branch }}
              <span aria-hidden="true">·</span>
              KYC status: {{ registrationConfirmation.kyc_status }}
              (pending review)
            </p>
          </div>
          <button
            class="dismiss-button"
            type="button"
            aria-label="Dismiss registration confirmation"
            @click="dismissRegistrationConfirmation"
          >
            ×
          </button>
        </section>

        <form class="search-form" role="search" @submit.prevent="submitSearch">
          <label class="visually-hidden" for="customer-search">Search customers</label>
          <input
            id="customer-search"
            v-model="searchInput"
            type="search"
            maxlength="100"
            placeholder="Search by customer, CIF, district or branch"
            :disabled="loading"
          />
          <button class="primary-button" type="submit" :disabled="loading">
            Search
          </button>
        </form>

        <div v-if="loading" class="inline-state" role="status">
          <span class="spinner" aria-hidden="true"></span>
          Loading customer records...
        </div>

        <div v-else-if="error" class="inline-state error-message" role="alert">
          <p>{{ error }}</p>
          <button class="secondary-button" type="button" @click="loadCustomers(pagination.page)">
            Retry
          </button>
        </div>

        <div v-else-if="customers.length === 0" class="empty-state" role="status">
          <h3>No customers found</h3>
          <p>
            {{ submittedSearch
              ? 'Try another search term.'
              : 'There are no customer records to display yet.' }}
          </p>
        </div>

        <template v-else>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Customer ID</th>
                  <th scope="col">Full Name</th>
                  <th scope="col">Customer Type</th>
                  <th scope="col">KYC Status</th>
                  <th scope="col">Account/Customer Status</th>
                  <th scope="col">Home Branch</th>
                  <th scope="col">Created Date</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="customer in customers" :key="customer.id">
                  <td>{{ customer.id }}</td>
                  <td class="customer-name">{{ customer.full_name }}</td>
                  <td>{{ customer.customer_type }}</td>
                  <td>
                    <span class="badge" :class="`badge-${customer.kyc_status?.toLowerCase()}`">
                      {{ customer.kyc_status }}
                    </span>
                  </td>
                  <td>{{ customer.status }}</td>
                  <td>{{ customer.home_branch }}</td>
                  <td>{{ formatDate(customer.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <nav class="pagination" aria-label="Customer list pagination">
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

      <div
        v-if="registrationOpen"
        class="modal-backdrop"
        @click.self="closeRegistration"
      >
        <section
          class="registration-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="registration-heading"
          aria-describedby="registration-intro"
        >
          <header class="modal-header">
            <div>
              <p class="eyebrow">CBS Administration</p>
              <h2 id="registration-heading">Register New Customer</h2>
              <p id="registration-intro" class="modal-intro">
                New customers are created with KYC status Pending for review.
              </p>
            </div>
            <button
              class="dismiss-button"
              type="button"
              aria-label="Close registration form"
              :disabled="submitting"
              @click="closeRegistration"
            >
              ×
            </button>
          </header>

          <div v-if="branchError" class="form-alert" role="alert">
            <p>{{ branchError }}</p>
            <button
              v-if="branches.length === 0"
              class="secondary-button"
              type="button"
              :disabled="branchesLoading"
              @click="openRegistration"
            >
              Retry loading branches
            </button>
          </div>
          <div v-else-if="branchesLoading" class="inline-state" role="status">
            <span class="spinner" aria-hidden="true"></span>
            Loading active branches...
          </div>

          <form
            v-else
            class="registration-form"
            novalidate
            @submit.prevent="submitRegistration"
          >
            <p v-if="registrationError" class="form-alert" role="alert">
              {{ registrationError }}
            </p>

            <div class="form-grid">
              <div class="form-field">
                <label for="registration-customer-type">Customer Type <span>*</span></label>
                <select
                  id="registration-customer-type"
                  :value="registrationForm.customer_type"
                  :aria-invalid="Boolean(fieldErrors.customer_type)"
                  aria-describedby="registration-customer-type-error"
                  :disabled="submitting"
                  @change="setRegistrationField('customer_type', $event.target.value)"
                >
                  <option value="INDIVIDUAL">Individual</option>
                  <option value="ORGANIZATION">Organization</option>
                </select>
                <span
                  v-if="fieldErrors.customer_type"
                  id="registration-customer-type-error"
                  class="field-error"
                >{{ fieldErrors.customer_type }}</span>
              </div>

              <div class="form-field">
                <label for="registration-full-name">Full Name <span>*</span></label>
                <input
                  id="registration-full-name"
                  :value="registrationForm.full_name"
                  type="text"
                  maxlength="150"
                  autocomplete="off"
                  :aria-invalid="Boolean(fieldErrors.full_name)"
                  aria-describedby="registration-full-name-error"
                  :disabled="submitting"
                  @input="setRegistrationField('full_name', $event.target.value)"
                />
                <span v-if="fieldErrors.full_name" id="registration-full-name-error" class="field-error">
                  {{ fieldErrors.full_name }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-phone">Phone <span>*</span></label>
                <input
                  id="registration-phone"
                  :value="registrationForm.phone"
                  type="tel"
                  maxlength="20"
                  autocomplete="off"
                  :aria-invalid="Boolean(fieldErrors.phone)"
                  aria-describedby="registration-phone-error"
                  :disabled="submitting"
                  @input="setRegistrationField('phone', $event.target.value)"
                />
                <span v-if="fieldErrors.phone" id="registration-phone-error" class="field-error">
                  {{ fieldErrors.phone }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-email">Email <span class="optional-label">Optional</span></label>
                <input
                  id="registration-email"
                  :value="registrationForm.email"
                  type="email"
                  maxlength="254"
                  autocomplete="off"
                  :aria-invalid="Boolean(fieldErrors.email)"
                  aria-describedby="registration-email-error"
                  :disabled="submitting"
                  @input="setRegistrationField('email', $event.target.value)"
                />
                <span v-if="fieldErrors.email" id="registration-email-error" class="field-error">
                  {{ fieldErrors.email }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-date-of-birth">Date of Birth <span class="optional-label">Optional</span></label>
                <input
                  id="registration-date-of-birth"
                  :value="registrationForm.date_of_birth"
                  type="date"
                  :max="todayLocalIso()"
                  :aria-invalid="Boolean(fieldErrors.date_of_birth)"
                  aria-describedby="registration-date-of-birth-error"
                  :disabled="submitting"
                  @input="setRegistrationField('date_of_birth', $event.target.value)"
                />
                <span v-if="fieldErrors.date_of_birth" id="registration-date-of-birth-error" class="field-error">
                  {{ fieldErrors.date_of_birth }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-gender">Gender <span class="optional-label">Optional</span></label>
                <select
                  id="registration-gender"
                  :value="registrationForm.gender"
                  :aria-invalid="Boolean(fieldErrors.gender)"
                  aria-describedby="registration-gender-error"
                  :disabled="submitting"
                  @change="setRegistrationField('gender', $event.target.value)"
                >
                  <option value="">Select gender</option>
                  <option value="MALE">Male</option>
                  <option value="FEMALE">Female</option>
                  <option value="OTHER">Other</option>
                </select>
                <span v-if="fieldErrors.gender" id="registration-gender-error" class="field-error">
                  {{ fieldErrors.gender }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-nid">
                  NID Number <span class="optional-label">Optional</span>
                </label>
                <input
                  id="registration-nid"
                  :value="registrationForm.nid_number"
                  type="text"
                  maxlength="30"
                  autocomplete="new-password"
                  spellcheck="false"
                  :aria-invalid="Boolean(fieldErrors.nid_number)"
                  aria-describedby="registration-identity-note registration-nid-error"
                  :disabled="submitting"
                  @input="setRegistrationField('nid_number', $event.target.value)"
                />
                <span v-if="fieldErrors.nid_number" id="registration-nid-error" class="field-error">
                  {{ fieldErrors.nid_number }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-passport">
                  Passport Number <span class="optional-label">Optional</span>
                </label>
                <input
                  id="registration-passport"
                  :value="registrationForm.passport_number"
                  type="text"
                  maxlength="30"
                  autocomplete="new-password"
                  spellcheck="false"
                  :aria-invalid="Boolean(fieldErrors.passport_number)"
                  aria-describedby="registration-identity-note registration-passport-error"
                  :disabled="submitting"
                  @input="setRegistrationField('passport_number', $event.target.value)"
                />
                <span v-if="fieldErrors.passport_number" id="registration-passport-error" class="field-error">
                  {{ fieldErrors.passport_number }}
                </span>
              </div>

              <p id="registration-identity-note" class="form-hint form-field-wide">
                Individual customers must provide an NID or passport. These values are not shown in the customer list or confirmation.
              </p>

              <div class="form-field">
                <label for="registration-present-address">Present Address <span>*</span></label>
                <textarea
                  id="registration-present-address"
                  :value="registrationForm.present_address"
                  maxlength="5000"
                  rows="3"
                  :aria-invalid="Boolean(fieldErrors.present_address)"
                  aria-describedby="registration-present-address-error"
                  :disabled="submitting"
                  @input="setRegistrationField('present_address', $event.target.value)"
                ></textarea>
                <span v-if="fieldErrors.present_address" id="registration-present-address-error" class="field-error">
                  {{ fieldErrors.present_address }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-permanent-address">
                  Permanent Address <span class="optional-label">Optional</span>
                </label>
                <textarea
                  id="registration-permanent-address"
                  :value="registrationForm.permanent_address"
                  maxlength="5000"
                  rows="3"
                  :aria-invalid="Boolean(fieldErrors.permanent_address)"
                  aria-describedby="registration-permanent-address-error"
                  :disabled="submitting"
                  @input="setRegistrationField('permanent_address', $event.target.value)"
                ></textarea>
                <span v-if="fieldErrors.permanent_address" id="registration-permanent-address-error" class="field-error">
                  {{ fieldErrors.permanent_address }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-district">District <span>*</span></label>
                <input
                  id="registration-district"
                  :value="registrationForm.district"
                  type="text"
                  maxlength="100"
                  autocomplete="off"
                  :aria-invalid="Boolean(fieldErrors.district)"
                  aria-describedby="registration-district-error"
                  :disabled="submitting"
                  @input="setRegistrationField('district', $event.target.value)"
                />
                <span v-if="fieldErrors.district" id="registration-district-error" class="field-error">
                  {{ fieldErrors.district }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-home-branch">Home Branch <span>*</span></label>
                <select
                  id="registration-home-branch"
                  :value="registrationForm.home_branch"
                  :aria-invalid="Boolean(fieldErrors.home_branch)"
                  aria-describedby="registration-home-branch-error"
                  :disabled="submitting || branches.length === 0"
                  @change="setRegistrationField('home_branch', $event.target.value)"
                >
                  <option value="">Select an active branch</option>
                  <option
                    v-for="branch in branches"
                    :key="branch.id"
                    :value="branch.id"
                  >
                    {{ branch.branch_name }} ({{ branch.branch_code }})
                  </option>
                </select>
                <span v-if="fieldErrors.home_branch" id="registration-home-branch-error" class="field-error">
                  {{ fieldErrors.home_branch }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-nominee-name">Nominee Name <span class="optional-label">Optional</span></label>
                <input
                  id="registration-nominee-name"
                  :value="registrationForm.nominee_name"
                  type="text"
                  maxlength="150"
                  autocomplete="off"
                  :aria-invalid="Boolean(fieldErrors.nominee_name)"
                  aria-describedby="registration-nominee-name-error"
                  :disabled="submitting"
                  @input="setRegistrationField('nominee_name', $event.target.value)"
                />
                <span v-if="fieldErrors.nominee_name" id="registration-nominee-name-error" class="field-error">
                  {{ fieldErrors.nominee_name }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-nominee-relationship">Nominee Relationship <span class="optional-label">Optional</span></label>
                <input
                  id="registration-nominee-relationship"
                  :value="registrationForm.nominee_relationship"
                  type="text"
                  maxlength="50"
                  autocomplete="off"
                  :aria-invalid="Boolean(fieldErrors.nominee_relationship)"
                  aria-describedby="registration-nominee-relationship-error"
                  :disabled="submitting"
                  @input="setRegistrationField('nominee_relationship', $event.target.value)"
                />
                <span v-if="fieldErrors.nominee_relationship" id="registration-nominee-relationship-error" class="field-error">
                  {{ fieldErrors.nominee_relationship }}
                </span>
              </div>

              <div class="form-field">
                <label for="registration-nominee-phone">Nominee Phone <span class="optional-label">Optional</span></label>
                <input
                  id="registration-nominee-phone"
                  :value="registrationForm.nominee_phone"
                  type="tel"
                  maxlength="20"
                  autocomplete="off"
                  :aria-invalid="Boolean(fieldErrors.nominee_phone)"
                  aria-describedby="registration-nominee-phone-error"
                  :disabled="submitting"
                  @input="setRegistrationField('nominee_phone', $event.target.value)"
                />
                <span v-if="fieldErrors.nominee_phone" id="registration-nominee-phone-error" class="field-error">
                  {{ fieldErrors.nominee_phone }}
                </span>
              </div>
            </div>

            <footer class="form-actions">
              <button
                class="secondary-button"
                type="button"
                :disabled="submitting"
                @click="closeRegistration"
              >
                Cancel
              </button>
              <button
                class="primary-button"
                type="submit"
                :disabled="submitting || branches.length === 0 || branchesLoading"
              >
                {{ submitting ? 'Registering...' : 'Submit Registration' }}
              </button>
            </footer>
          </form>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.customer-page {
  width: min(100%, 1320px);
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
  font-size: 0.86rem;
  font-weight: 700;
  text-decoration: none;
}

.back-link:hover,
.back-link:focus-visible {
  color: #0a58ca;
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
  padding: 20px;
}

.section-heading {
  margin-bottom: 18px;
}

.section-heading h2 {
  margin: 0;
  color: #173f6d;
  font-size: 1.05rem;
}

.list-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.record-count {
  color: #63758a;
  font-size: 0.82rem;
}

.confirmation-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  border: 1px solid #b8dfc4;
  border-radius: 8px;
  padding: 16px;
  background: #eff9f1;
  color: #285c36;
}

.confirmation-card h3 {
  margin: 0 0 7px;
  color: #205331;
  font-size: 0.96rem;
}

.confirmation-card p:not(.eyebrow) {
  margin: 4px 0 0;
  font-size: 0.82rem;
}

.confirmation-card .eyebrow {
  color: #487555;
}

.dismiss-button {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #53657b;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
}

.dismiss-button:hover:not(:disabled),
.dismiss-button:focus-visible {
  background: #eaf2fb;
  color: #173f6d;
}

.dismiss-button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.modal-backdrop {
  position: fixed;
  z-index: 20;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  overflow-y: auto;
  padding: clamp(12px, 4vh, 36px) 16px;
  background: rgb(19 36 55 / 58%);
}

.registration-modal {
  width: min(100%, 900px);
  max-height: calc(100vh - 2 * clamp(12px, 4vh, 36px));
  overflow-y: auto;
  border: 1px solid #dce5ef;
  border-radius: 12px;
  padding: clamp(18px, 4vw, 30px);
  background: #fff;
  box-shadow: 0 20px 60px rgb(11 31 52 / 28%);
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  border-bottom: 1px solid #e8edf3;
  padding-bottom: 16px;
}

.modal-header h2 {
  margin: 0;
  color: #173f6d;
  font-size: clamp(1.15rem, 3vw, 1.45rem);
}

.modal-intro {
  margin: 8px 0 0;
  color: #63758a;
  font-size: 0.84rem;
}

.registration-form {
  display: grid;
  gap: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.form-field {
  display: grid;
  align-content: start;
  gap: 6px;
  min-width: 0;
}

.form-field label {
  color: #31465c;
  font-size: 0.82rem;
  font-weight: 700;
}

.form-field label > span:not(.optional-label) {
  color: #b42318;
}

.optional-label {
  margin-left: 4px;
  color: #738295;
  font-size: 0.72rem;
  font-weight: 500;
}

.form-field input,
.form-field select,
.form-field textarea {
  width: 100%;
  min-height: 40px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fff;
  color: #25364a;
  font: inherit;
  font-size: 0.86rem;
}

.form-field textarea {
  min-height: 88px;
  resize: vertical;
}

.form-field input:focus,
.form-field select:focus,
.form-field textarea:focus {
  border-color: #0d6efd;
  outline: 3px solid rgb(13 110 253 / 15%);
}

.form-field [aria-invalid="true"] {
  border-color: #b42318;
}

.form-field [aria-invalid="true"]:focus {
  outline-color: rgb(180 35 24 / 15%);
}

.field-error {
  color: #a12828;
  font-size: 0.75rem;
}

.form-field-wide {
  grid-column: 1 / -1;
}

.form-hint {
  margin: -5px 0 0;
  color: #63758a;
  font-size: 0.78rem;
  line-height: 1.45;
}

.form-alert {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0;
  border: 1px solid #f1c2c7;
  border-radius: 7px;
  padding: 11px 13px;
  background: #fff5f5;
  color: #842029;
  font-size: 0.84rem;
}

.form-alert p {
  margin: 0;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  border-top: 1px solid #e8edf3;
  padding-top: 16px;
}

.search-form {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.search-form input {
  width: min(100%, 480px);
  min-height: 40px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px 11px;
  color: #25364a;
  font: inherit;
  font-size: 0.88rem;
}

.search-form input:focus {
  border-color: #0d6efd;
  outline: 3px solid rgb(13 110 253 / 15%);
}

.primary-button,
.secondary-button {
  min-height: 38px;
  border: 0;
  border-radius: 6px;
  padding: 8px 14px;
  font: inherit;
  font-size: 0.84rem;
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
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #245b8f;
}

.secondary-button:hover:not(:disabled) {
  background: #eaf2fb;
}

.primary-button:disabled,
.secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  text-align: left;
  white-space: nowrap;
}

th,
td {
  border-bottom: 1px solid #e8edf3;
  padding: 12px 10px;
}

th {
  background: #f5f8fb;
  color: #53657b;
  font-size: 0.74rem;
  font-weight: 700;
}

tbody tr:hover {
  background: #f8fbff;
}

.customer-name {
  color: #173f6d;
  font-weight: 700;
}

.badge {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 8px;
  background: #eaf2fb;
  color: #245b8f;
  font-size: 0.72rem;
  font-weight: 700;
}

.badge-verified,
.badge-active {
  background: #e7f5ec;
  color: #246b3c;
}

.badge-rejected,
.badge-blocked {
  background: #fce8e8;
  color: #9a3030;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
  margin-top: 18px;
  color: #53657b;
  font-size: 0.84rem;
}

.empty-state,
.inline-state {
  display: flex;
  min-height: 130px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #63758a;
  text-align: center;
}

.empty-state h3,
.empty-state p,
.inline-state p {
  margin: 0;
}

.empty-state h3 {
  color: #173f6d;
  font-size: 1rem;
}

.inline-state {
  flex-direction: row;
}

.error-message {
  flex-wrap: wrap;
  color: #842029;
}

.state-card {
  display: flex;
  min-height: 170px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 20px;
  color: #53657b;
  text-align: center;
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

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 640px) {
  .page-heading,
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .list-actions {
    width: 100%;
    align-items: flex-start;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .form-field-wide {
    grid-column: auto;
  }

  .search-form {
    flex-direction: column;
  }

  .search-form input {
    width: 100%;
  }

  .pagination {
    justify-content: space-between;
    gap: 8px;
  }

  .form-actions {
    flex-direction: column-reverse;
  }

  .form-actions button {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 2s;
  }
}
</style>
