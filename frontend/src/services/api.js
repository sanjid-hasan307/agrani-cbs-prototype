import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000/api',

  withCredentials: true,

  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  withXSRFToken: true,

  headers: {
    'Content-Type': 'application/json'
  }
})

export default api