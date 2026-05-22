<template>
  <span :class="['badge', badgeClass]">
    <i :class="['mr-1', iconClass]"></i>{{ label }}
  </span>
</template>

<script>
const MAP = {
  high:        { cls: 'badge-danger',  icon: 'fas fa-exclamation-circle', label: 'Alto' },
  medium_high: { cls: 'badge-warning', icon: 'fas fa-exclamation-triangle', label: 'Medio-Alto' },
  medium:      { cls: 'badge-info',    icon: 'fas fa-info-circle', label: 'Medio' },
  low:         { cls: 'badge-success', icon: 'fas fa-check-circle', label: 'Bajo' },
}
export default {
  name: 'RiskBadge',
  props: { risk: { type: String, required: true } },
  computed: {
    badgeClass() { return (MAP[this.risk] || MAP.low).cls },
    iconClass()  { return (MAP[this.risk] || MAP.low).icon },
    label()      { return (MAP[this.risk] || MAP.low).label },
  },
}
</script>
