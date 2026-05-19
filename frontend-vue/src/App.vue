<template>
  <div id="as-app">

    <!-- Sidebar -->
    <nav :class="['as-sidebar', { 'as-sidebar--collapsed': !sidebarOpen }]">
      <div class="as-sidebar__brand">
        <i class="fas fa-satellite"></i>
        <span class="as-sidebar__brand-text">AgroSentinel</span>
      </div>

      <ul class="as-sidebar__menu">
        <li>
          <router-link to="/dashboard" class="as-sidebar__link" active-class="as-sidebar__link--active">
            <i class="fas fa-tachometer-alt"></i><span>Dashboard</span>
          </router-link>
        </li>
        <li>
          <router-link to="/lotes" class="as-sidebar__link" active-class="as-sidebar__link--active">
            <i class="fas fa-map-marked-alt"></i><span>Lotes</span>
          </router-link>
        </li>
        <li>
          <router-link to="/alertas" class="as-sidebar__link" active-class="as-sidebar__link--active">
            <i class="fas fa-bell"></i>
            <span>Alertas</span>
            <span v-if="alertCount" class="as-badge">{{ alertCount }}</span>
          </router-link>
        </li>
        <li>
          <router-link to="/jobs" class="as-sidebar__link" active-class="as-sidebar__link--active">
            <i class="fas fa-tasks"></i><span>Trabajos</span>
          </router-link>
        </li>
        <li class="as-sidebar__divider"></li>
        <li>
          <router-link to="/servicios" class="as-sidebar__link" active-class="as-sidebar__link--active">
            <i class="fas fa-heartbeat"></i><span>Servicios</span>
          </router-link>
        </li>
        <li>
          <router-link to="/configuracion" class="as-sidebar__link" active-class="as-sidebar__link--active">
            <i class="fas fa-cog"></i><span>Configuración</span>
          </router-link>
        </li>
      </ul>

      <div class="as-sidebar__footer">
        <span class="as-sidebar__version">v0.1.0</span>
      </div>
    </nav>

    <!-- Main -->
    <div :class="['as-main', { 'as-main--expanded': !sidebarOpen }]">
      <!-- Topbar -->
      <header class="as-topbar">
        <button class="as-topbar__toggle" @click="$store.commit('toggleSidebar')">
          <i class="fas fa-bars"></i>
        </button>
        <span class="as-topbar__title">{{ currentTitle }}</span>
        <div class="as-topbar__right">
          <span class="badge badge-warning mr-2" title="Datos ficticios activos">
            <i class="fas fa-flask mr-1"></i>MOCK
          </span>
          <span class="as-topbar__user">
            <i class="fas fa-user-circle mr-1"></i>Demo
          </span>
        </div>
      </header>

      <!-- Page content -->
      <main class="as-content">
        <router-view />
      </main>
    </div>

  </div>
</template>

<script>
import { mapState } from 'vuex'
import { getAlertas } from '@/services/api'

export default {
  name: 'App',
  data() {
    return { alertCount: 0 }
  },
  computed: {
    ...mapState(['sidebarOpen']),
    currentTitle() {
      const map = {
        Dashboard: 'Dashboard',
        Lotes: 'Lotes Agrícolas',
        LoteDetalle: 'Detalle de Lote',
        Alertas: 'Alertas Activas',
        Jobs: 'Trabajos',
        Configuracion: 'Configuración',
        Servicios: 'Estado de Servicios',
      }
      return map[this.$route.name] || 'AgroSentinel'
    },
  },
  async created() {
    const alertas = await getAlertas()
    this.alertCount = alertas.length
  },
}
</script>

<style>
/* ─── Reset & variables ───────────────────────────────────────────────── */
:root {
  --as-green-dark:   #1b4332;
  --as-green:        #2d6a4f;
  --as-green-mid:    #40916c;
  --as-green-light:  #74c69d;
  --as-green-pale:   #d8f3dc;
  --as-sidebar-w:    240px;
  --as-sidebar-coll: 64px;
  --as-topbar-h:     56px;
  --as-radius:       8px;
  --as-shadow:       0 1px 4px rgba(0,0,0,.08);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f1f5f2; color: #1c2b20; }
a { text-decoration: none; }

/* ─── Layout ──────────────────────────────────────────────────────────── */
#as-app { display: flex; min-height: 100vh; }

/* ─── Sidebar ─────────────────────────────────────────────────────────── */
.as-sidebar {
  width: var(--as-sidebar-w);
  min-height: 100vh;
  background: var(--as-green-dark);
  display: flex; flex-direction: column;
  position: fixed; top: 0; left: 0; z-index: 100;
  transition: width .25s ease;
  overflow: hidden;
}
.as-sidebar--collapsed { width: var(--as-sidebar-coll); }

.as-sidebar__brand {
  display: flex; align-items: center; gap: 12px;
  padding: 18px 16px;
  color: #fff; font-size: 1.15rem; font-weight: 700;
  border-bottom: 1px solid rgba(255,255,255,.1);
  white-space: nowrap;
}
.as-sidebar__brand i { font-size: 1.3rem; color: var(--as-green-light); min-width: 24px; }
.as-sidebar--collapsed .as-sidebar__brand-text { display: none; }

.as-sidebar__menu { list-style: none; padding: 10px 0; flex: 1; }
.as-sidebar__menu li { position: relative; }
.as-sidebar__divider {
  height: 1px; background: rgba(255,255,255,.1);
  margin: 8px 12px;
}
.as-sidebar__link {
  display: flex; align-items: center; gap: 12px;
  padding: 11px 16px;
  color: rgba(255,255,255,.75); font-size: .9rem;
  transition: background .15s, color .15s;
  white-space: nowrap; border-radius: 0;
}
.as-sidebar__link i { min-width: 22px; font-size: 1rem; }
.as-sidebar--collapsed .as-sidebar__link span { display: none; }
.as-sidebar--collapsed .as-badge { display: none; }
.as-sidebar__link:hover { background: rgba(255,255,255,.08); color: #fff; }
.as-sidebar__link--active { background: var(--as-green-mid) !important; color: #fff !important; }
.as-badge {
  margin-left: auto;
  background: #ef4444; color: #fff;
  font-size: .7rem; font-weight: 700;
  padding: 1px 6px; border-radius: 999px;
}
.as-sidebar__footer {
  padding: 12px 16px; border-top: 1px solid rgba(255,255,255,.1);
}
.as-sidebar__version { font-size: .72rem; color: rgba(255,255,255,.4); }
.as-sidebar--collapsed .as-sidebar__version { display: none; }

/* ─── Main ────────────────────────────────────────────────────────────── */
.as-main {
  margin-left: var(--as-sidebar-w);
  flex: 1; display: flex; flex-direction: column;
  transition: margin-left .25s ease;
  min-height: 100vh;
}
.as-main--expanded { margin-left: var(--as-sidebar-coll); }

/* ─── Topbar ──────────────────────────────────────────────────────────── */
.as-topbar {
  height: var(--as-topbar-h);
  background: #fff;
  box-shadow: var(--as-shadow);
  display: flex; align-items: center; gap: 14px;
  padding: 0 22px;
  position: sticky; top: 0; z-index: 99;
}
.as-topbar__toggle {
  background: none; border: none; cursor: pointer;
  color: #6b7280; font-size: 1.15rem; padding: 4px;
  transition: color .15s;
}
.as-topbar__toggle:hover { color: var(--as-green); }
.as-topbar__title { font-size: 1rem; font-weight: 600; color: #1c2b20; }
.as-topbar__right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.as-topbar__user { font-size: .85rem; color: #6b7280; }

/* ─── Content ─────────────────────────────────────────────────────────── */
.as-content { padding: 24px; flex: 1; }

/* ─── Shared cards ────────────────────────────────────────────────────── */
.as-card {
  background: #fff; border-radius: var(--as-radius);
  box-shadow: var(--as-shadow); padding: 20px;
  margin-bottom: 20px;
}
.as-card__title {
  font-size: .8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: #6b7280; margin-bottom: 12px;
}

/* ─── Stat cards ──────────────────────────────────────────────────────── */
.as-stat {
  background: #fff; border-radius: var(--as-radius);
  box-shadow: var(--as-shadow); padding: 18px 22px;
  display: flex; align-items: center; gap: 16px;
}
.as-stat__icon {
  width: 48px; height: 48px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.3rem; flex-shrink: 0;
}
.as-stat__value { font-size: 1.8rem; font-weight: 800; line-height: 1; }
.as-stat__label { font-size: .78rem; color: #6b7280; margin-top: 3px; }

/* ─── Page header ─────────────────────────────────────────────────────── */
.as-page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px;
}
.as-page-header h1 { font-size: 1.3rem; font-weight: 700; color: #1c2b20; }
.as-page-header small { font-size: .8rem; color: #6b7280; }

/* ─── Table ───────────────────────────────────────────────────────────── */
.as-table { width: 100%; border-collapse: collapse; font-size: .88rem; }
.as-table th {
  padding: 10px 14px; background: #f9fafb; border-bottom: 2px solid #e5e7eb;
  text-align: left; font-size: .75rem; text-transform: uppercase;
  letter-spacing: .05em; color: #6b7280; white-space: nowrap;
}
.as-table td { padding: 12px 14px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
.as-table tr:last-child td { border-bottom: none; }
.as-table tr:hover td { background: #f9fafb; }
.as-table a { color: var(--as-green); font-weight: 600; }
.as-table a:hover { color: var(--as-green-mid); text-decoration: underline; }

/* ─── Buttons ─────────────────────────────────────────────────────────── */
.as-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 16px; border-radius: 6px; font-size: .85rem; font-weight: 600;
  cursor: pointer; border: none; transition: opacity .15s, box-shadow .15s;
}
.as-btn:hover { opacity: .88; box-shadow: 0 2px 8px rgba(0,0,0,.12); }
.as-btn--primary { background: var(--as-green); color: #fff; }
.as-btn--outline {
  background: #fff; color: var(--as-green);
  border: 1.5px solid var(--as-green);
}

/* ─── Risk colors ─────────────────────────────────────────────────────── */
.risk-high        { color: #dc2626; }
.risk-medium_high { color: #d97706; }
.risk-medium      { color: #2563eb; }
.risk-low         { color: #16a34a; }
</style>
