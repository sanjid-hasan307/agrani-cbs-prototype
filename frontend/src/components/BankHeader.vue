<template>
  <header class="bank-header">

    <div class="brand">
      <h2>Agrani Bank PLC</h2>
      <span>Core Banking System</span>
    </div>


    <div class="system-info">
      <span class="status">
        ● Secure System
      </span>
    </div>

  </header>
</template>


<style scoped>

.bank-header {

  height:70px;

  background:#003B7A;

  color:white;

  display:flex;

  align-items:center;

  justify-content:space-between;

  padding:0 40px;

}


.brand h2 {

  margin:0;

  font-size:22px;

  font-weight:700;

}


.brand span {

  font-size:13px;

  opacity:.85;

}


.status {

  font-size:14px;

  background:rgba(255,255,255,.15);

  padding:8px 15px;

  border-radius:20px;

}

</style>