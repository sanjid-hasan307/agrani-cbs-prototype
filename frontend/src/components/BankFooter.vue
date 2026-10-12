<template>
  <footer class="bank-footer">

    <div class="copyright">
      © 2026 Agrani Bank PLC
    </div>


    <button 
      class="login-btn"
      @click="showLogin = true"
    >
      🔒 Secure Login
    </button>


    <LoginModal
      v-if="showLogin"
      @close="showLogin = false"
    />

  </footer>
</template>


<script setup>

import { ref } from 'vue'
import LoginModal from './LoginModal.vue'


const showLogin = ref(false)

</script>


<style scoped>

.bank-footer {

  height:65px;

  background:#003B7A;

  color:white;

  display:flex;

  align-items:center;

  justify-content:space-between;

  padding:0 40px;

}


.copyright {

  font-size:14px;

}


.login-btn {

  background:white;

  color:#003B7A;

  border:none;

  padding:10px 22px;

  border-radius:8px;

  font-weight:600;

  cursor:pointer;

}


.login-btn:hover {

  background:#f1f5f9;

}

</style>