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
      />

      <input
        v-model="password"
        type="password"
        placeholder="Password"
      />

      <button
        class="submit-btn"
        @click="login"
      >
        Sign In
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

const authStore = useAuthStore()


async function login() {
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

      authStore.setUser(
        response.data
      )

      error.value = ""

      if (response.data.role === 'Manager') {
        await router.replace('/dashboard/manager')
        emit('close')
      } else {
        error.value = "Dashboard for this role is not available yet."
      }

    }


  } catch (err) {
    error.value = "Login failed"

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