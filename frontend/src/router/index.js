import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import ManagerDashboard from '../views/ManagerDashboard.vue'
import TellerDashboard from '../views/TellerDashboard.vue'

const router = createRouter({
  history: createWebHistory(),

  routes: [
    {
      path: '/',
      redirect: '/login'
    },

    {
      path: '/login',
      name: 'Login',
      component: LoginView
    },

    {
      path: '/dashboard/manager',
      name: 'ManagerDashboard',
      component: ManagerDashboard
    },
    {
      path: '/dashboard/teller',
      name: 'TellerDashboard',
      component: TellerDashboard
    }
  ]
})

export default router