import Vue from 'vue'
import VueRouter from 'vue-router'

Vue.use(VueRouter)

const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
  },
  {
    path: '/lotes',
    name: 'Lotes',
    component: () => import('@/views/LotesView.vue'),
  },
  {
    path: '/lotes/:id',
    name: 'LoteDetalle',
    component: () => import('@/views/LoteDetalleView.vue'),
    props: true,
  },
  {
    path: '/alertas',
    name: 'Alertas',
    component: () => import('@/views/AlertasView.vue'),
  },
  {
    path: '/jobs',
    name: 'Jobs',
    component: () => import('@/views/JobsView.vue'),
  },
  {
    path: '/configuracion',
    name: 'Configuracion',
    component: () => import('@/views/ConfiguracionView.vue'),
  },
  {
    path: '/servicios',
    name: 'Servicios',
    component: () => import('@/views/ServiciosView.vue'),
  },
]

const router = new VueRouter({
  mode: 'history',
  base: process.env.BASE_URL,
  routes,
})

export default router
