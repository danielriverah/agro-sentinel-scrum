<template>
  <div class="index-gauge">
    <div class="d-flex justify-content-between align-items-center mb-1">
      <span class="index-name">{{ name }}</span>
      <span class="index-value" :style="{ color: barColor }">{{ formattedMean }}</span>
    </div>
    <div class="progress" style="height: 8px;">
      <div
        class="progress-bar"
        :style="{ width: barWidth + '%', background: barColor }"
        role="progressbar"
      ></div>
    </div>
    <div class="d-flex justify-content-between mt-1">
      <small class="text-muted">Min {{ data.min.toFixed(2) }}</small>
      <small class="text-muted">Max {{ data.max.toFixed(2) }}</small>
    </div>
  </div>
</template>

<script>
const RANGES = {
  ndvi:  { min: -1, max: 1,   low: 0.3, high: 0.6,  colors: ['#dc2626','#f59e0b','#16a34a'] },
  ndmi:  { min: -1, max: 1,   low: 0.1, high: 0.25, colors: ['#dc2626','#f59e0b','#2563eb'] },
  ndre:  { min: -1, max: 1,   low: 0.2, high: 0.35, colors: ['#dc2626','#f59e0b','#16a34a'] },
  msavi2:{ min: -1, max: 1,   low: 0.2, high: 0.5,  colors: ['#dc2626','#f59e0b','#16a34a'] },
  bsi:   { min: -1, max: 1,   low: -0.1,high: 0.1,  colors: ['#16a34a','#f59e0b','#dc2626'] },
  evi:   { min: -1, max: 1,   low: 0.2, high: 0.4,  colors: ['#dc2626','#f59e0b','#16a34a'] },
  default:{ min:-1, max: 1,   low: 0.2, high: 0.5,  colors: ['#dc2626','#f59e0b','#16a34a'] },
}
export default {
  name: 'IndexGauge',
  props: {
    name: { type: String, required: true },
    data: { type: Object, required: true },
  },
  computed: {
    range()  { return RANGES[this.name.toLowerCase()] || RANGES.default },
    barWidth() {
      const { min, max } = this.range
      return Math.min(100, Math.max(0, ((this.data.mean - min) / (max - min)) * 100))
    },
    barColor() {
      const { low, high, colors } = this.range
      if (this.data.mean < low)  return colors[0]
      if (this.data.mean < high) return colors[1]
      return colors[2]
    },
    formattedMean() { return this.data.mean.toFixed(3) },
  },
}
</script>

<style scoped>
.index-gauge { margin-bottom: 1rem; }
.index-name  { font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }
.index-value { font-size: 1.05rem; font-weight: 700; }
</style>
