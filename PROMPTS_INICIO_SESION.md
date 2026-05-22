# AgroSentinel — Prompt de Inicio de Sesión

Copia y pega este prompt completo al inicio de cada conversación con cualquier IA
antes de pedir que escriba código o tome decisiones de diseño.

---

## Prompt estándar (versión completa)

```
Eres el desarrollador principal del proyecto AgroSentinel.
Antes de responder cualquier pregunta o generar cualquier código,
lee los siguientes archivos en este orden exacto:

1. README.md                        → visión general y estado del proyecto
2. docs/ARQUITECTURA.md             → reglas técnicas, contratos, lo que cada servicio NO puede hacer
3. docs/ESTRUCTURA_PROYECTO.md      → árbol completo del repo y qué sprint implementa qué módulo
4. docs/DYNAMODB_CONFIG.md          → estructura exacta de la configuración
5. docs/ERRORES.md                  → códigos de error y excepciones
6. DEFINITION_OF_DONE.md           → criterios que debe cumplir todo código entregado
7. PRODUCT_BACKLOG.md              → historias de usuario y sus criterios de aceptación
8. sprints/[área]/SPRINT_[N].md    → el sprint activo (ver tabla de estado en README.md)

Cuando termines de leer, responde con:
- Sprint activo: [número y nombre]
- Primera tarea pendiente: [nombre del archivo o tarea]
- Cualquier duda de contexto antes de escribir código

No generes código hasta que yo confirme el sprint y la tarea.
Si ya confirmé, genera el archivo completo —no stubs ni "...".
Usa las excepciones tipadas de exceptions.py, nunca Exception genérica.
Sigue el contrato de entrada/salida exacto de docs/ARQUITECTURA.md.
```

---

## Prompt corto (cuando el contexto ya está cargado en la sesión)

```
Continuamos en el Sprint [N] — [nombre del sprint].
Tarea actual: [nombre del archivo].
Recuerda: [restricción clave del sprint si aplica].
Genera el archivo completo siguiendo el DoD.
```

---

## Prompt para retomar después de un error

```
El código del archivo [nombre] tiene un problema:
[descripción del error o traza]

Antes de proponer una solución, verifica:
1. Que la excepción usada existe en app/core/exceptions.py
2. Que el contrato de respuesta sigue docs/ARQUITECTURA.md
3. Que no se importan librerías del microservicio opuesto

Propón solo el cambio mínimo necesario para resolver el error.
```

---

## Prompt para pedir un test

```
Escribe los tests para [nombre del archivo] siguiendo el DoD del Sprint [N].
Casos requeridos según DEFINITION_OF_DONE.md:
- Caso feliz: [descripción]
- Caso de error principal: [descripción]
Usa pytest con mocks para dependencias externas (DynamoDB, S3, Copernicus, Anthropic).
No uses fixtures globales — cada test debe ser independiente.
```

---

## Prompt para validar un sprint antes de marcarlo completado

```
Revisa el Sprint [N] y confirma que cumple todos los criterios del DEFINITION_OF_DONE.md.
Para cada criterio, responde: ✅ cumplido / ❌ faltante / ⚠️ parcial.
Si hay criterios faltantes, lista los archivos que hay que crear o modificar.
```
