import { defineStore } from 'pinia'


export const useAuthStore = defineStore('auth', {

    state: () => ({
        user: null,
        role: null,
        branch: null,
        isAuthenticated: false
    }),


    actions: {

        setUser(data) {

            this.user = data.username
            this.role = data.role
            this.branch = data.branch
            this.isAuthenticated = true

        },


        logout() {

            this.user = null
            this.role = null
            this.branch = null
            this.isAuthenticated = false

        }

    },


    persist: true

})