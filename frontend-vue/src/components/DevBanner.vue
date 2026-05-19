<template>
  <div class="dev-banner">
    <i class="fas fa-flask mr-2"></i>
    <strong>PENDIENTE DE DESARROLLO</strong>
    <span class="ml-2">— Esta vista usa datos ficticios. Se conectará al {{ servicio }} cuando el sprint esté completo.</span>
    <span v-if="sprint" class="ml-2 badge badge-light">
      <i class="fas fa-code-branch mr-1"></i>Sprint {{ sprint }}
    </span>
  </div>
</template>

<script>
export default {
  name: 'DevBanner',
  props: {
    servicio: { type: String, default: 'microservicio' },
    sprint: { type: [String, Number], default: null },
  },
}
</script>

<style scoped>
.dev-banner {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
  color: #1c1917;
  padding: 8px 16px;
  font-size: 0.82rem;
  border-left: 4px solid #d97706;
  border-radius: 4px;
  margin-bottom: 1.25rem;
}
</style>
