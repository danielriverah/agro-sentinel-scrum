<template>
  <span :class="['service-pill', 'service-pill--' + status]">
    <span class="dot"></span> {{ label }}
  </span>
</template>

<script>
export default {
  name: 'ServicePill',
  props: {
    status: { type: String, default: 'unknown' },
    label:  { type: String, default: '' },
  },
}
</script>

<style scoped>
.service-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 600;
}
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.service-pill--ok       { background: #dcfce7; color: #16a34a; }
.service-pill--ok .dot  { background: #16a34a; }
.service-pill--degraded { background: #fef3c7; color: #d97706; }
.service-pill--degraded .dot { background: #d97706; }
.service-pill--error    { background: #fee2e2; color: #dc2626; }
.service-pill--error .dot    { background: #dc2626; }
.service-pill--unknown  { background: #f3f4f6; color: #6b7280; }
.service-pill--unknown .dot  { background: #9ca3af; }
</style>
