import axios from 'axios'

const api = axios.create({
  baseURL: 'http://219.245.185.245:8000/api/v1',
  timeout: 60000
})

export default api
