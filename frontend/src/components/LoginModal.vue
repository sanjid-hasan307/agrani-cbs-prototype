<template>
  <div class="overlay">

    <div class="login-card">

      <button class="close" @click="emit('close')">
        ×
      </button>

      <h2>Agrani Bank PLC</h2>

      <p class="subtitle">
        CBS Authentication
      </p>

      <input
        v-model="username"
        type="text"
        placeholder="User ID"
        autocomplete="username"
        :disabled="submitting"
      />

      <input
        v-model="password"
        type="password"
        placeholder="Password"
        autocomplete="current-password"
        :disabled="submitting"
      />

      <button
        class="submit-btn"
        @click="login"
        :disabled="submitting"
      >
        {{ submitting ? 'Signing in...' : 'Sign In' }}
      </button>

      <p v-if="error" class="error">
        {{ error }}
      </p>

    </div>

  </div>
</template>


<script setup>

import { ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../services/api'

import { useAuthStore } from '../stores/auth'

const emit = defineEmits(['close'])
const router = useRouter()

const username = ref('')
const password = ref('')

const error = ref('')
const submitting = ref(false)

const authStore = useAuthStore()


async function login() {
  if (submitting.value) return

  submitting.value = true
  error.value = ''
  try {
    // Get CSRF cookie before submitting credentials
    await api.get('/csrf/')
    const response = await api.post(
      '/login/',
      {
        username: username.value,
        password: password.value
      }
    )

    if (response.data.success) {
      if (response.data.role === 'Manager') {
        authStore.setUser(response.data)
        await router.replace('/dashboard/manager')
        emit('close')
      } else if (response.data.role === 'Teller') {
        authStore.setUser(response.data)
        await router.replace('/dashboard/teller')
        emit('close')
      } else {
        authStore.logout()
        error.value = 'Your account does not have a supported dashboard role. Please contact an administrator.'
      }
    } else {
      error.value = response.data.message || 'Login failed. Please check your credentials.'
    }
  } catch (requestError) {
    error.value = requestError.response?.data?.message
      || 'Login failed. Please check your credentials and try again.'
  } finally {
    submitting.value = false
  }
}

</script>


<style scoped>

.overlay {

  position: fixed;
  inset: 0;

  display:flex;
  justify-content:center;
  align-items:center;

  background:rgba(0,0,0,.4);

}

.submit-btn:disabled {
  cursor: wait;
  opacity: .7;
}


.login-card {

  width:360px;

  background:white;

  padding:35px;

  border-radius:15px;

}


.close {

  float:right;

  border:none;

  background:none;

  font-size:25px;

}


input {

  width:100%;

  padding:12px;

  margin-top:15px;

}


.submit-btn {

  width:100%;

  margin-top:20px;

  padding:12px;

  background:#003b7a;

  color:white;

  border:none;

  border-radius:8px;

}


.error {

  color:red;

  text-align:center;

}

</style>