import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import AdminDashboard from '../views/AdminDashboard.vue'
import AdminCustomers from '../views/AdminCustomers.vue'
import AdminAccounts from '../views/AdminAccounts.vue'
import AdminBranches from '../views/AdminBranches.vue'
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
      path: '/dashboard/admin',
      name: 'AdminDashboard',
      component: AdminDashboard
    },
    {
      path: '/dashboard/admin/customers',
      name: 'AdminCustomers',
      component: AdminCustomers
    },
    {
      path: '/dashboard/admin/accounts',
      name: 'AdminAccounts',
      component: AdminAccounts
    },
    {
      path: '/dashboard/admin/branches',
      name: 'AdminBranches',
      component: AdminBranches
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