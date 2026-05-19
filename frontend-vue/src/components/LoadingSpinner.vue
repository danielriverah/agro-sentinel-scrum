<template>
  <div class="text-center py-5">
    <div class="spinner-border text-success" style="width:2.5rem;height:2.5rem;" role="status">
      <span class="sr-only">Cargando...</span>
    </div>
    <p class="mt-3 text-muted small">{{ mensaje }}</p>
  </div>
</template>

<script>
export default {
  name: 'LoadingSpinner',
  props: { mensaje: { type: String, default: 'Cargando datos...' } },
}
</script>
