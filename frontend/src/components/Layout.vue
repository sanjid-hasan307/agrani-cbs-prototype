<template>
  <div class="layout">

    <BankHeader />


    <main class="content">
      <router-view />
    </main>


    <BankFooter />

  </div>
</template>


<script setup>

import BankHeader from './BankHeader.vue'
import BankFooter from './BankFooter.vue'

</script>


<style scoped>

.layout {

  min-height:100vh;

  display:flex;

  flex-direction:column;

  background:#f4f6f9;

}


.content {
  flex:1;
  display:flex;
  flex-direction:column;
}

</style>