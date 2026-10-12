<template>
  <section class="hero">

    <div class="hero-content">

      <h1>
        Agrani Bank PLC
      </h1>

      <h2>
        Core Banking System
      </h2>


      <p class="description">
        A centralized banking operations platform for secure
        account management, branch transactions and authorization workflow.
      </p>


      <div class="info-cards">

        <div class="card">
          <h3>
            Branch Operations
          </h3>

          <p>
            Manage daily branch activities and banking services.
          </p>
        </div>


        <div class="card">

          <h3>
            Account Management
          </h3>

          <p>
            Maintain customer accounts with secure access control.
          </p>

        </div>


        <div class="card">

          <h3>
            Transaction Processing
          </h3>

          <p>
            Process deposits, withdrawals and fund transfers.
          </p>

        </div>


      </div>


      <div class="security-note">

        🔒 Authorized Banking Personnel Only

      </div>


    </div>

  </section>
</template>


<style scoped>

.hero {

  display:flex;

  justify-content:center;

  align-items:center;

  padding:45px 40px;

}


.hero-content {

  text-align:center;

  max-width:1000px;

}


h1 {

  font-size:40px;

  color:#003B7A;

  margin-bottom:8px;

}


h2 {

  font-size:24px;

  color:#334155;

  margin-bottom:20px;

}


.description {

  color:#64748b;

  font-size:16px;

  max-width:750px;

  margin:auto;

  line-height:1.6;

}


.info-cards {

  display:flex;

  gap:25px;

  margin-top:35px;

}


.card {

  flex:1;

  background:white;

  padding:25px;

  border-radius:12px;

  border-top:4px solid #003B7A;

  box-shadow:0 5px 18px rgba(0,0,0,0.08);

}


.card h3 {

  color:#003B7A;

  font-size:18px;

}


.card p {

  color:#64748b;

  font-size:14px;

  line-height:1.5;

}


.security-note {

  margin-top:30px;

  color:#475569;

  font-size:14px;

}


</style>