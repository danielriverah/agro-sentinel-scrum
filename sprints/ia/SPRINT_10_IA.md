# Sprint 10 — IA: Integración Anthropic + Prompt

**Duración:** 1 semana  
**Prerequisito:** Sprint 9 completado  
**Objetivo:** El servicio construye el payload para Anthropic, llama a la API y valida la respuesta.  
**Historias:** US-016, US-017  
**Entregable:** Dado un payload de estadísticas con alertas, devuelve el diagnóstico normalizado de Anthropic.

---

## Contexto para la IA

La llamada a Anthropic usa la API de mensajes estándar. El system prompt está en `prompts/system_prompt_agronomico.md` y se carga una sola vez al iniciar el servicio.

El payload del usuario es JSON estructurado — no texto libre. La IA debe responder SOLO con JSON. Si la respuesta tiene bloques de código markdown (```json ... ```) hay que stripearlos antes de parsear.

Temperatura: 0.2 — respuestas consistentes y conservadoras.

---

## Archivos a implementar

### `app/services/ai/prompt_builder.py`

```python
class PromptBuilder:
    def build_user_payload(
        self,
        lot_context: dict,
        current_indices: dict,
        historical_means: dict | None,
        changes_pct: dict | None,
        rules_result: dict,
        image_quality: dict,
        weather_context: dict | None
    ) -> str:
        """
        Construye el mensaje de usuario como JSON string.
        El sistema prompt viene del archivo .md — este método construye solo el user message.
        """
        payload = {
            "lot": lot_context,
            "analysis_date": ...,
            "image_quality": image_quality,
            "indices": {
                name: {
                    "current": stats["mean"],
                    "historical_mean": historical_means.get(name) if historical_means else None,
                    "change_pct": changes_pct.get(name) if changes_pct else None
                }
                for name, stats in current_indices.items()
            },
            "weather": weather_context,
            "rules_result": rules_result
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
```

### `app/services/ai/anthropic_client.py`

```python
class AnthropicClient:
    def __init__(self, api_key: str, model: str, max_tokens: int = 2500, temperature: float = 0.2):
        ...

    async def complete(self, system_prompt: str, user_message: str, timeout: int = 60) -> str:
        """
        Llama a la API de Anthropic.
        Devuelve el texto de la respuesta.
        Lanza AiTimeoutError si supera timeout.
        Lanza AiProviderRuntimeError en error 5xx.
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_message}]
                }
            )
        ...
```

### `app/services/ai/response_parser.py`

```python
class ResponseParser:
    REQUIRED_FIELDS = ["risk_level", "summary", "probable_causes", "recommendations", "confidence", "limitations"]
    VALID_RISK_LEVELS = {"low", "medium", "medium_high", "high"}
    VALID_CONFIDENCE = {"low", "medium", "high"}

    def parse(self, raw_response: str) -> dict:
        """
        1. Stripear bloques markdown si existen (```json ... ```)
        2. Parsear JSON
        3. Validar campos requeridos
        4. Normalizar tipos (probable_causes debe ser list, etc.)
        5. Si falta un campo → completar con valor por defecto razonable
        6. Si risk_level no es válido → "medium" por defecto
        Lanza AiResponseInvalidError solo si el JSON es completamente inválido.
        """
        ...
```

### `app/services/ai/provider_factory.py`

```python
class ProviderFactory:
    def get_client(self, config: dict):
        """
        Devuelve el cliente correcto según config['ai']['provider'].
        Soporta: anthropic, openai (compatible), ollama, vllm, custom.
        """
        provider = config["ai"]["provider"]
        provider_config = config["ai"]["providers"][provider]

        if provider == "anthropic":
            return AnthropicClient(
                api_key=provider_config["api_key"],
                model=provider_config["model"],
                max_tokens=config["ai"]["max_tokens"],
                temperature=config["ai"]["temperature"]
            )
        elif provider in ["openai", "ollama", "vllm", "lmstudio"]:
            return OpenAICompatibleClient(
                base_url=provider_config["base_url"],
                api_key=provider_config.get("api_key", ""),
                model=provider_config["model"],
                ...
            )
        ...
```

---

## Criterios de aceptación

- [ ] Con API key real de Anthropic, la llamada devuelve JSON válido con los 6 campos requeridos
- [ ] Una respuesta con bloques markdown (```json```) se parsea correctamente
- [ ] Una respuesta con `risk_level: "crítico"` (valor inválido) se normaliza a `"medium"`
- [ ] Si falta el campo `limitations`, se completa con `["Análisis basado en datos satelitales"]`
- [ ] Con API key inválida → `AiProviderRuntimeError` (no 500 genérico)
- [ ] Temperatura 0.2 se aplica correctamente (verificable en el request a Anthropic)

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `prompts/system_prompt_agronomico.md` (versión completa) | ⬜ |
| `app/services/ai/prompt_builder.py` | ⬜ |
| `app/services/ai/anthropic_client.py` | ⬜ |
| `app/services/ai/response_parser.py` | ⬜ |
| `app/services/ai/provider_factory.py` | ⬜ |
| Tests unitarios response_parser (10+ casos de respuestas malformadas) | ⬜ |
| Test integración Anthropic real | ⬜ |

**Sprint completado:** ⬜

---
---

