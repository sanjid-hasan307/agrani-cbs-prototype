<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import api from '../services/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const verifying = ref(true)
const authorized = ref(false)
const username = ref('')
const verificationError = ref('')

async function verifyAdminSession() {
  verifying.value = true
  verificationError.value = ''

  try {
    const response = await api.get('/admin/session/')
    if (
      !response.data.success
      || response.data.role !== 'Admin'
      || typeof response.data.username !== 'string'
      || !response.data.username
    ) {
      authorized.value = false
      authStore.logout()
      await router.replace('/login')
      return
    }

    username.value = response.data.username
    authorized.value = true
    authStore.setUser(response.data)
  } catch (error) {
    authorized.value = false
    authStore.logout()

    if (error.response?.status === 401 || error.response?.status === 403) {
      await router.replace('/login')
    } else {
      verificationError.value = 'Unable to verify your Admin session. Please try again.'
    }
  } finally {
    verifying.value = false
  }
}

onMounted(verifyAdminSession)
</script>

<template>
  <section class="admin-dashboard">
    <div v-if="verifying" class="state-card" role="status">
      <span class="spinner" aria-hidden="true"></span>
      Verifying your Admin session...
    </div>

    <div v-else-if="verificationError" class="state-card error-card" role="alert">
      <p>{{ verificationError }}</p>
      <button class="retry-button" type="button" @click="verifyAdminSession">
        Retry
      </button>
    </div>

    <div v-else-if="authorized" class="dashboard-content">
      <header class="page-heading">
        <div>
          <p class="eyebrow">CBS Administration</p>
          <h1>Welcome, {{ username }}</h1>
          <p class="welcome">Role: <strong>CBS Admin</strong></p>
        </div>
      </header>

      <section class="overview-card" aria-labelledby="overview-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Read-only</p>
            <h2 id="overview-heading">System Overview</h2>
          </div>
          <span class="status-badge">Overview only</span>
        </div>
        <p>
          Your Admin session is verified. Live system metrics and administrative
          operations are not yet available in this dashboard.
        </p>
      </section>

      <section class="management-section" aria-label="Administration areas">
        <RouterLink class="management-card management-card-link" to="/dashboard/admin/customers">
          <span class="card-icon" aria-hidden="true">01</span>
          <h2>Customer Management</h2>
          <p>Customer records and profile administration.</p>
          <span class="open-section">View customer list</span>
        </RouterLink>

        <RouterLink class="management-card management-card-link" to="/dashboard/admin/accounts">
          <span class="card-icon" aria-hidden="true">02</span>
          <h2>Account Management</h2>
          <p>Account opening and account administration.</p>
          <span class="open-section">Manage accounts</span>
        </RouterLink>

        <RouterLink class="management-card management-card-link" to="/dashboard/admin/branches">
          <span class="card-icon" aria-hidden="true">03</span>
          <h2>Branch Management</h2>
          <p>Branch records and branch information.</p>
          <span class="open-section">Manage branches</span>
        </RouterLink>

        <article class="management-card">
          <span class="card-icon" aria-hidden="true">04</span>
          <h2>Staff Management</h2>
          <p>Staff profiles and role administration.</p>
          <span class="coming-soon">Coming Soon</span>
        </article>

        <article class="management-card">
          <span class="card-icon" aria-hidden="true">05</span>
          <h2>Audit Monitoring</h2>
          <p>Audit record review and monitoring.</p>
          <span class="coming-soon">Coming Soon</span>
        </article>
      </section>
    </div>
  </section>
</template>

<style scoped>
.admin-dashboard {
  width: min(100%, 1180px);
  margin: 0 auto;
  padding: 32px clamp(16px, 4vw, 40px);
  color: #25364a;
}

.dashboard-content {
  display: grid;
  gap: 20px;
}

.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.welcome {
  margin: 6px 0 0;
  color: #53657b;
  font-size: 0.88rem;
}

.overview-card,
.management-card,
.state-card {
  border: 1px solid #e3e9f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 4px 14px rgb(26 52 82 / 5%);
}

.overview-card {
  padding: 20px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-heading h2,
.management-card h2 {
  margin: 0;
  color: #173f6d;
  font-size: 1rem;
}

.overview-card > p,
.management-card p {
  color: #63758a;
  font-size: 0.84rem;
  line-height: 1.55;
}

.overview-card > p {
  margin: 14px 0 0;
}

.status-badge,
.coming-soon {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  border-radius: 999px;
  padding: 5px 9px;
  background: #eaf2fb;
  color: #245b8f;
  font-size: 0.7rem;
  font-weight: 700;
}

.management-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 205px), 1fr));
  gap: 14px;
}

.management-card {
  display: flex;
  min-height: 190px;
  flex-direction: column;
  align-items: flex-start;
  padding: 18px;
}

.management-card-link {
  color: inherit;
  text-decoration: none;
}

.management-card-link:hover,
.management-card-link:focus-visible {
  border-color: #9bbce0;
  box-shadow: 0 7px 20px rgb(26 72 120 / 12%);
}

.management-card-link:focus-visible {
  outline: 3px solid rgb(13 110 253 / 25%);
  outline-offset: 2px;
}

.management-card-link .open-section {
  margin-top: auto;
  color: #245b8f;
  font-size: 0.78rem;
  font-weight: 700;
}

.card-icon {
  display: grid;
  width: 34px;
  height: 34px;
  margin-bottom: 15px;
  place-items: center;
  border-radius: 8px;
  background: #eaf2fb;
  color: #245b8f;
  font-size: 0.7rem;
  font-weight: 700;
}

.management-card p {
  margin: 9px 0 16px;
}

.management-card .coming-soon {
  margin-top: auto;
  background: #f1f3f5;
  color: #53657b;
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

.error-card {
  border-color: #f1c2c7;
  color: #842029;
}

.error-card p {
  margin: 0;
}

.retry-button {
  min-height: 34px;
  border: 0;
  border-radius: 6px;
  padding: 6px 12px;
  background: #0d6efd;
  color: #fff;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
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

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 2s;
  }
}
</style>
