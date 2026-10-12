<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../services/api'

const router = useRouter()

const loading = ref(true)
const authorized = ref(false)
const username = ref('')
const error = ref('')

onMounted(async () => {
  try {
    const response = await api.get('/manager/session/')

    if (response.data.success && response.data.role === 'Manager') {
      authorized.value = true
      username.value = response.data.username
    } else {
      router.replace('/login')
    }
  } catch (err) {
    authorized.value = false

    if (err.response?.status === 401 || err.response?.status === 403) {
      router.replace('/login')
    } else {
      error.value = 'Unable to verify your session. Please try again.'
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="manager-dashboard">
    <p v-if="loading">Verifying your session...</p>

    <p v-else-if="error" class="error">{{ error }}</p>

    <div v-else-if="authorized">
      <h1>Manager Dashboard</h1>
      <p>Agrani Bank PLC — Core Banking System</p>

      <div class="notice">
        Welcome, {{ username }}.
        Manager Dashboard frontend is under development.
      </div>
    </div>
  </section>
</template>

<style scoped>
.manager-dashboard {
  padding: 40px;
}

h1 {
  color: #003b7a;
}

.notice {
  margin-top: 24px;
  padding: 20px;
  background: #fff;
  border-left: 4px solid #003b7a;
  border-radius: 6px;
}

.error {
  color: #b42318;
}
</style>