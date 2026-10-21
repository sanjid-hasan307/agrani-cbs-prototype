<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../services/api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const loggingOut = ref(false)
const logoutError = ref('')

const dashboardTitle = computed(() => {
  if (route.path === '/dashboard/admin/customers') return 'Customer Management'
  if (route.path === '/dashboard/admin/accounts') return 'Account Management'
  if (route.path === '/dashboard/admin') return 'Admin Dashboard'
  if (route.path === '/dashboard/manager') return 'Manager Dashboard'
  if (route.path === '/dashboard/teller') return 'Teller Dashboard'
  return ''
})

async function logout() {
  if (loggingOut.value) return

  loggingOut.value = true
  logoutError.value = ''

  try {
    await api.get('/csrf/')
    await api.post('/logout/', null, {
      baseURL: new URL(api.defaults.baseURL).origin
    })
    authStore.logout()
    await router.replace('/login')
  } catch (error) {
    if (error.response?.status === 401) {
      authStore.logout()
      await router.replace('/login')
    } else {
      logoutError.value = 'Unable to log out securely. Please try again.'
    }
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <header class="bank-header">

    <div class="brand">
      <h2>Agrani Bank CBS</h2>
      <span>Core Banking System</span>
    </div>

    <div class="header-actions">
      <span v-if="dashboardTitle" class="dashboard-title">{{ dashboardTitle }}</span>
      <span class="status">
        <span aria-hidden="true">●</span> Secure System
      </span>
      <button
        v-if="dashboardTitle"
        class="logout-button"
        type="button"
        :disabled="loggingOut"
        :aria-busy="loggingOut"
        @click="logout"
      >
        {{ loggingOut ? 'Logging out...' : 'Logout' }}
      </button>
    </div>

    <p v-if="logoutError" class="logout-error" role="alert">
      {{ logoutError }}
    </p>
  </header>
</template>


<style scoped>

.bank-header {
  position: relative;
  min-height:64px;
  background:linear-gradient(135deg,#0d6efd,#0a58ca);
  color:white;
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:10px clamp(16px, 4vw, 40px);
}

.brand h2 {
  margin:0;
  font-size:20px;
  font-weight:700;
}

.brand span {
  font-size:13px;
  opacity:.85;
}

.status {
  font-size:14px;
  background:rgba(255,255,255,.15);
  padding:7px 13px;
  border-radius:20px;
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.dashboard-title {
  color: #fff;
  font-size: 13px;
  white-space: nowrap;
}

.logout-button {
  min-height: 32px;
  border: 1px solid rgb(255 255 255 / 75%);
  border-radius: 5px;
  padding: 5px 11px;
  background: transparent;
  color: #fff;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.logout-button:hover:not(:disabled),
.logout-button:focus-visible {
  background: #fff;
  color: #0a58ca;
}

.logout-button:focus-visible {
  outline: 3px solid rgb(255 255 255 / 45%);
  outline-offset: 2px;
}

.logout-button:disabled {
  cursor: wait;
  opacity: .7;
}

.logout-error {
  position: absolute;
  z-index: 1;
  top: 100%;
  right: clamp(16px, 4vw, 40px);
  max-width: min(420px, calc(100vw - 32px));
  margin: 5px 0 0;
  border: 1px solid #f5c2c7;
  border-radius: 5px;
  padding: 8px 11px;
  background: #f8d7da;
  color: #842029;
  font-size: 12px;
  box-shadow: 0 3px 10px rgb(0 0 0 / 10%);
}

@media (max-width: 480px) {
  .bank-header {
    gap: 10px;
    padding-right: 12px;
    padding-left: 12px;
  }

  .brand h2 {
    font-size: 17px;
  }

  .brand span {
    font-size: 11px;
  }

  .header-actions {
    gap: 6px;
  }

  .dashboard-title {
    font-size: 11px;
  }

  .status {
    display: none;
  }

  .logout-button {
    min-height: 30px;
    padding: 4px 8px;
    font-size: 11px;
  }

  .logout-error {
    right: 12px;
  }
}

</style>