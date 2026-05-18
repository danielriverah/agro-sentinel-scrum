# Sprint 12 — Laravel: Consumo del Servicio AgroSentinel

**Duración:** 1 semana  
**Prerequisito:** Sprints 7 y 11 completados y desplegados en sus servidores  
**Objetivo:** Laravel consume AgroSentinel como servicio externo HTTP: solicita análisis, consulta estado por polling y recibe resultados vía webhook desde internet.  
**Historias:** US-022, US-023, US-024  
**Entregable:** Flujo completo desde el ERP Laravel hasta el diagnóstico en pantalla, con AgroSentinel en su propio servidor.

---

## Contexto crítico para la IA

**AgroSentinel NO está en el mismo servidor que Laravel.** Es un servicio externo independiente con su propia URL pública. Laravel se comunica con él exclusivamente por HTTP, igual que si fuera una API de terceros (como Stripe o Twilio).

```
[Servidor Laravel]                    [Servidor AgroSentinel]
  ERP PHP/Laravel         HTTP        Droplet TIF :8001
  Tu dominio        ─────────────►    Droplet IA  :8002
  tu-erp.com        ◄─────────────
                    Webhook HTTPS
```

**Consecuencias prácticas:**
- Las URLs de los servicios son públicas o accesibles por red privada — no `localhost`
- El webhook del Microservicio IA llega desde una IP externa — Laravel debe aceptarlo en su firewall
- La firma HMAC es la única forma de verificar que el webhook viene de AgroSentinel, no de otro origen
- Los timeouts deben ser generosos: `POST /analyze` devuelve 202 en < 1 segundo, pero el análisis real tarda 2–10 minutos
- Laravel no espera el resultado — lo recibe por webhook cuando está listo

**Modelo de comunicación — dos fases:**
```
FASE 1 — Solicitud (síncrona, < 1 segundo):
Laravel → POST https://tif.agro.tu-dominio.com/analyze
        ← 202 { job_id: "job_123", status: "processing" }

FASE 2 — Resultado (asíncrono, 2–10 minutos después):
AgroSentinel IA → POST https://tu-erp.com/api/sentinel/webhook
               ← 200 { ok: true }
```

Laravel puede opcionalmente hacer polling en `GET /jobs/{id}/status` si quiere mostrar progreso en tiempo real, pero el resultado definitivo siempre llega por webhook.

---

## Arquitectura de red recomendada

Para que el webhook funcione en producción, el Microservicio IA necesita poder hacer una llamada HTTPS a Laravel. Opciones:

**Opción A — URLs públicas con dominio (recomendada)**
```
TIF Service:  https://tif.agro.tu-dominio.com
IA Service:   https://ia.agro.tu-dominio.com
Webhook URL:  https://tu-erp.com/api/sentinel/webhook
```

**Opción B — Red privada DigitalOcean (si Laravel también está en DO)**
```
TIF Service:  http://[private-ip-droplet-tif]:8001
IA Service:   http://[private-ip-droplet-ia]:8002
Webhook URL:  http://[private-ip-laravel]/api/sentinel/webhook
```

**Para desarrollo local:**
```
TIF Service:  http://localhost:8001   (o via ngrok)
IA Service:   http://localhost:8002
Webhook URL:  https://[tu-subdominio].ngrok.io/api/sentinel/webhook
```

La URL del webhook se configura en DynamoDB en `laravel.webhook_url` — no en el código.

---

## Migraciones de base de datos

### `sentinel_jobs`
Rastrea cada análisis solicitado y su estado.

```php
Schema::create('sentinel_jobs', function (Blueprint $table) {
    $table->id();
    $table->string('job_id')->unique();
    $table->unsignedBigInteger('parcela_id');
    $table->string('status', 20)->default('processing');
    // processing → completed | failed
    $table->date('analysis_date')->nullable();
    $table->json('dates_requested');
    $table->json('indices_requested');
    $table->timestamp('requested_at')->useCurrent();
    $table->timestamp('completed_at')->nullable();
    $table->string('error_code', 100)->nullable();
    $table->text('error_message')->nullable();
    $table->timestamps();

    $table->index(['parcela_id', 'status']);
    $table->index('job_id');
});
```

### `parcela_indices`
Guarda los valores de índices espectrales por análisis.

```php
Schema::create('parcela_indices', function (Blueprint $table) {
    $table->id();
    $table->string('job_id');
    $table->unsignedBigInteger('parcela_id');
    $table->date('fecha');
    $table->string('indice', 20);
    $table->float('valor_min')->nullable();
    $table->float('valor_max')->nullable();
    $table->float('valor_mean')->nullable();
    $table->float('valor_std')->nullable();
    $table->integer('pixeles_validos')->default(0);
    $table->float('cloud_coverage')->default(0);
    $table->timestamps();

    $table->unique(['parcela_id', 'fecha', 'indice']);
    $table->index(['parcela_id', 'fecha']);
});
```

### `ia_analisis`
Guarda el resultado del diagnóstico IA cuando llega el webhook.

```php
Schema::create('ia_analisis', function (Blueprint $table) {
    $table->id();
    $table->string('job_id')->unique();
    $table->unsignedBigInteger('parcela_id');
    $table->date('fecha');
    $table->string('ai_provider', 50)->nullable();
    $table->string('ai_model', 100)->nullable();
    $table->integer('config_version')->nullable();
    $table->string('risk_level', 20)->nullable();
    // low | medium | medium_high | high
    $table->text('summary')->nullable();
    $table->json('probable_causes')->nullable();
    $table->json('recommendations')->nullable();
    $table->string('confidence', 20)->nullable();
    $table->json('limitations')->nullable();
    $table->json('rules_result')->nullable();
    $table->json('indices_stats')->nullable();
    $table->json('image_quality')->nullable();
    $table->json('warnings')->nullable();
    $table->string('source_s3_path')->nullable();
    $table->timestamps();

    $table->index(['parcela_id', 'fecha']);
    $table->index('risk_level');
});
```

---

## `app/Exceptions/AgroSentinelException.php`

```php
<?php

namespace App\Exceptions;

use Exception;

class AgroSentinelException extends Exception
{
    public function __construct(
        public readonly string $errorCode,
        string $message,
        public readonly array $missing = [],
        public readonly array $invalid = [],
        public readonly array $details = []
    ) {
        parent::__construct($message);
    }

    public function isConfigError(): bool
    {
        return in_array($this->errorCode, [
            'CONFIG_VALIDATION_ERROR',
            'DYNAMODB_CONFIG_NOT_FOUND',
            'CONFIG_DISABLED',
            'ENV_CONFIG_MISSING',
        ]);
    }

    public function isServiceUnavailable(): bool
    {
        return in_array($this->errorCode, [
            'COPERNICUS_AUTH_ERROR',
            'STORAGE_PRESSURE',
            'AI_PROVIDER_UNAVAILABLE',
        ]);
    }
}
```

---

## `config/agro_sentinel.php`

```php
<?php

return [
    /*
     * URLs base de los microservicios AgroSentinel.
     * Estos servicios corren en su propio servidor — NO en el servidor de Laravel.
     * En producción usar HTTPS con dominio propio o IP privada de DigitalOcean.
     */
    'tif_service_url' => env('AGRO_SENTINEL_TIF_URL'),
    'ia_service_url'  => env('AGRO_SENTINEL_IA_URL'),

    /*
     * Clave compartida para autenticar requests de Laravel hacia AgroSentinel.
     * Debe coincidir con security.api_secret_key en DynamoDB.
     */
    'api_secret_key'  => env('AGRO_SENTINEL_API_KEY'),

    /*
     * Clave para validar la firma HMAC de los webhooks que llegan desde AgroSentinel IA.
     * Debe coincidir con laravel.webhook_secret en DynamoDB.
     */
    'webhook_secret'  => env('AGRO_SENTINEL_WEBHOOK_SECRET'),

    /*
     * Timeout para llamadas HTTP hacia AgroSentinel.
     * POST /analyze devuelve 202 en < 1s, así que 15s es suficiente para la solicitud inicial.
     * GET /jobs/{id}/status también es rápido.
     */
    'http_timeout'    => env('AGRO_SENTINEL_TIMEOUT', 15),

    /*
     * Intervalo de polling para consultar el estado de un job (en segundos).
     * Solo si se implementa polling en tiempo real — el webhook es el mecanismo principal.
     */
    'polling_interval' => env('AGRO_SENTINEL_POLLING_INTERVAL', 30),
];
```

Variables a agregar en `.env` de Laravel:
```env
# Servidor externo de AgroSentinel — ajustar con las URLs reales del servidor
AGRO_SENTINEL_TIF_URL=https://tif.agro.tu-dominio.com
AGRO_SENTINEL_IA_URL=https://ia.agro.tu-dominio.com

# Debe coincidir con security.api_secret_key en DynamoDB de AgroSentinel
AGRO_SENTINEL_API_KEY=CAMBIAR-POR-CLAVE-COMPARTIDA

# Debe coincidir con laravel.webhook_secret en DynamoDB de AgroSentinel
AGRO_SENTINEL_WEBHOOK_SECRET=CAMBIAR-POR-CLAVE-WEBHOOK

AGRO_SENTINEL_TIMEOUT=15
```

Para desarrollo local con los microservicios corriendo en Docker:
```env
AGRO_SENTINEL_TIF_URL=http://localhost:8001
AGRO_SENTINEL_IA_URL=http://localhost:8002
```

---

## `app/Services/AgroSentinelService.php`

```php
<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Http\Client\RequestException;
use App\Exceptions\AgroSentinelException;
use App\Models\SentinelJob;

class AgroSentinelService
{
    private string $tifUrl;
    private string $iaUrl;
    private string $apiKey;
    private int $timeout;

    public function __construct()
    {
        $this->tifUrl  = config('agro_sentinel.tif_service_url');
        $this->iaUrl   = config('agro_sentinel.ia_service_url');
        $this->apiKey  = config('agro_sentinel.api_secret_key');
        $this->timeout = config('agro_sentinel.http_timeout', 15);
    }

    /**
     * Solicita un análisis satelital para un lote.
     * El resultado llega por webhook — este método solo inicia el proceso.
     *
     * @param  mixed  $parcela  Modelo Eloquent con id, polygon_geojson, cultivo, etapa_fenologica, area_ha
     * @param  array  $dates    ['YYYY-MM-DD', 'YYYY-MM-DD'] — rango de fechas
     * @param  array  $indices  Índices a calcular (default: los 5 principales)
     * @param  bool   $forceReprocess  Si true, ignora cache en S3
     * @return array  { job_id, status: "processing" }
     */
    public function requestAnalysis(
        mixed $parcela,
        array $dates,
        array $indices = ['NDVI', 'NDMI', 'NDRE', 'MSAVI2', 'BSI'],
        bool $forceReprocess = false
    ): array {
        $this->validateConfig();

        $jobId = 'job_' . now()->format('YmdHis') . '_' . $parcela->id;

        try {
            $response = Http::withHeaders([
                'X-API-Key'    => $this->apiKey,
                'Content-Type' => 'application/json',
                'Accept'       => 'application/json',
            ])
            ->timeout($this->timeout)
            ->post("{$this->tifUrl}/analyze", [
                'job_id'          => $jobId,
                'lot_id'          => $parcela->id,
                'polygon_geojson' => $parcela->polygon_geojson,
                'dates'           => $dates,
                'indices'         => $indices,
                'force_reprocess' => $forceReprocess,
                // Contexto para el análisis IA
                'lot_context' => [
                    'lot_name'           => $parcela->nombre ?? "Parcela {$parcela->id}",
                    'crop'               => $parcela->cultivo,
                    'phenological_stage' => $parcela->etapa_fenologica ?? null,
                    'area_ha'            => $parcela->area_ha ?? null,
                ],
            ]);

        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            throw new AgroSentinelException(
                'SERVICE_UNREACHABLE',
                "No se pudo conectar al servicio AgroSentinel TIF en {$this->tifUrl}. " .
                "Verificar que el servicio esté corriendo y que la URL sea correcta.",
            );
        }

        if ($response->failed()) {
            $this->throwFromResponse($response);
        }

        $result = $response->json();

        // Registrar el job en la BD local para rastreo
        SentinelJob::create([
            'job_id'            => $result['job_id'],
            'parcela_id'        => $parcela->id,
            'status'            => 'processing',
            'dates_requested'   => $dates,
            'indices_requested' => $indices,
        ]);

        return $result;
    }

    /**
     * Consulta el estado actual de un análisis en curso.
     * Útil para mostrar progreso en la UI mientras se espera el webhook.
     */
    public function getJobStatus(string $jobId): array
    {
        try {
            $response = Http::withHeaders(['X-API-Key' => $this->apiKey])
                ->timeout($this->timeout)
                ->get("{$this->tifUrl}/jobs/{$jobId}/status");
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            throw new AgroSentinelException('SERVICE_UNREACHABLE', 'No se pudo conectar al servicio TIF.');
        }

        if ($response->failed()) {
            $this->throwFromResponse($response);
        }

        return $response->json();
    }

    /**
     * Obtiene los últimos resultados de análisis de un lote desde AgroSentinel.
     * Alternativa al webhook si se necesita consultar resultados pasados directamente.
     */
    public function getLotResults(int $lotId): array
    {
        try {
            $response = Http::withHeaders(['X-API-Key' => $this->apiKey])
                ->timeout($this->timeout)
                ->get("{$this->tifUrl}/lots/{$lotId}/results");
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            throw new AgroSentinelException('SERVICE_UNREACHABLE', 'No se pudo conectar al servicio TIF.');
        }

        if ($response->failed()) {
            $this->throwFromResponse($response);
        }

        return $response->json();
    }

    /**
     * Obtiene las alertas activas (lotes con riesgo medium_high o high).
     */
    public function getActiveAlerts(): array
    {
        try {
            $response = Http::withHeaders(['X-API-Key' => $this->apiKey])
                ->timeout($this->timeout)
                ->get("{$this->iaUrl}/alerts");
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            throw new AgroSentinelException('SERVICE_UNREACHABLE', 'No se pudo conectar al servicio IA.');
        }

        if ($response->failed()) {
            $this->throwFromResponse($response);
        }

        return $response->json();
    }

    /**
     * Verifica que los microservicios estén en línea y con configuración válida.
     * Útil para mostrar estado en el panel administrativo.
     */
    public function getServicesHealth(): array
    {
        $tifHealth = $this->getHealth("{$this->tifUrl}/health", 'TIF');
        $iaHealth  = $this->getHealth("{$this->iaUrl}/health", 'IA');

        return [
            'tif' => $tifHealth,
            'ia'  => $iaHealth,
            'all_ok' => $tifHealth['reachable'] && $iaHealth['reachable']
                        && ($tifHealth['data']['config']['valid'] ?? false)
                        && ($iaHealth['data']['config']['valid'] ?? false),
        ];
    }

    // ─── Métodos privados ───────────────────────────────────────────────────────

    private function getHealth(string $url, string $label): array
    {
        try {
            $response = Http::timeout(5)->get($url);
            return [
                'reachable' => true,
                'status'    => $response->status(),
                'data'      => $response->json(),
            ];
        } catch (\Exception $e) {
            return [
                'reachable' => false,
                'label'     => $label,
                'error'     => $e->getMessage(),
            ];
        }
    }

    private function throwFromResponse(\Illuminate\Http\Client\Response $response): void
    {
        $body = $response->json() ?? [];

        throw new AgroSentinelException(
            errorCode: $body['error_code'] ?? 'HTTP_' . $response->status(),
            message:   $body['message'] ?? "Error {$response->status()} del servicio AgroSentinel",
            missing:   $body['missing'] ?? [],
            invalid:   $body['invalid'] ?? [],
            details:   $body['details'] ?? [],
        );
    }

    private function validateConfig(): void
    {
        if (empty($this->tifUrl) || empty($this->apiKey)) {
            throw new AgroSentinelException(
                'LARAVEL_CONFIG_MISSING',
                'Faltan variables de entorno de AgroSentinel en Laravel. ' .
                'Verificar AGRO_SENTINEL_TIF_URL y AGRO_SENTINEL_API_KEY en .env',
            );
        }
    }
}
```

---

## `app/Http/Controllers/SentinelController.php`

```php
<?php

namespace App\Http\Controllers;

use App\Services\AgroSentinelService;
use App\Exceptions\AgroSentinelException;
use App\Models\SentinelJob;
use App\Models\IaAnalisis;
use App\Models\ParcelaIndice;
use Illuminate\Http\Request;

class SentinelController extends Controller
{
    public function __construct(private AgroSentinelService $service) {}

    /**
     * Solicita un análisis para un lote.
     * El resultado llegará por webhook en 2–10 minutos.
     */
    public function requestAnalysis(Request $request, int $parcelaId)
    {
        $request->validate([
            'dates'   => ['required', 'array', 'size:2'],
            'dates.*' => ['required', 'date_format:Y-m-d'],
            'indices' => ['sometimes', 'array'],
        ]);

        $parcela = \App\Models\Parcela::findOrFail($parcelaId);

        try {
            $result = $this->service->requestAnalysis(
                parcela: $parcela,
                dates:   $request->input('dates'),
                indices: $request->input('indices', ['NDVI', 'NDMI', 'NDRE', 'MSAVI2', 'BSI']),
            );

            return response()->json([
                'ok'      => true,
                'job_id'  => $result['job_id'],
                'status'  => 'processing',
                'message' => 'Análisis iniciado. El resultado llegará por webhook en 2-10 minutos.',
            ], 202);

        } catch (AgroSentinelException $e) {

            if ($e->isConfigError()) {
                return response()->json([
                    'ok'       => false,
                    'error'    => 'El servicio de análisis tiene configuración incompleta.',
                    'code'     => $e->errorCode,
                    'missing'  => $e->missing,
                    'invalid'  => $e->invalid,
                ], 503);
            }

            if ($e->isServiceUnavailable()) {
                return response()->json([
                    'ok'    => false,
                    'error' => 'El servicio de análisis no está disponible en este momento.',
                    'code'  => $e->errorCode,
                ], 503);
            }

            return response()->json([
                'ok'    => false,
                'error' => $e->getMessage(),
                'code'  => $e->errorCode,
            ], 422);
        }
    }

    /**
     * Consulta el estado de un job en curso.
     * Útil para polling desde el frontend mientras se espera el webhook.
     */
    public function getJobStatus(string $jobId)
    {
        // Primero verificar en BD local (más rápido)
        $localJob = SentinelJob::where('job_id', $jobId)->first();

        if ($localJob && $localJob->status !== 'processing') {
            return response()->json([
                'job_id'       => $localJob->job_id,
                'status'       => $localJob->status,
                'analysis_date'=> $localJob->analysis_date,
                'completed_at' => $localJob->completed_at,
                'source'       => 'local',
            ]);
        }

        // Si sigue en processing, consultar el servicio externo
        try {
            $result = $this->service->getJobStatus($jobId);
            return response()->json(array_merge($result, ['source' => 'agro_sentinel']));
        } catch (AgroSentinelException $e) {
            return response()->json(['error' => $e->getMessage(), 'code' => $e->errorCode], 503);
        }
    }

    /**
     * Devuelve el último análisis completo de un lote (desde la BD local).
     */
    public function getLotLastAnalysis(int $parcelaId)
    {
        $analisis = IaAnalisis::where('parcela_id', $parcelaId)
            ->orderBy('fecha', 'desc')
            ->with('indices')
            ->first();

        if (!$analisis) {
            return response()->json(['message' => 'No hay análisis disponibles para este lote.'], 404);
        }

        return response()->json($analisis);
    }

    /**
     * Devuelve el historial de análisis de un lote.
     */
    public function getLotHistory(int $parcelaId)
    {
        $historial = IaAnalisis::where('parcela_id', $parcelaId)
            ->orderBy('fecha', 'desc')
            ->select(['id', 'job_id', 'fecha', 'risk_level', 'summary', 'confidence', 'ai_provider'])
            ->paginate(10);

        return response()->json($historial);
    }

    /**
     * Devuelve las alertas activas (riesgo medium_high o high) desde la BD local.
     * Más rápido que consultar el servicio externo en cada request.
     */
    public function getActiveAlerts()
    {
        $alertas = IaAnalisis::whereIn('risk_level', ['medium_high', 'high'])
            ->where('fecha', '>=', now()->subDays(7))
            ->orderByRaw("FIELD(risk_level, 'high', 'medium_high')")
            ->orderBy('fecha', 'desc')
            ->with('parcela:id,nombre,cultivo')
            ->get(['id', 'job_id', 'parcela_id', 'fecha', 'risk_level', 'summary', 'warnings']);

        return response()->json($alertas);
    }

    /**
     * Devuelve el estado de salud de los microservicios.
     * Para el panel administrativo.
     */
    public function getServicesHealth()
    {
        $health = $this->service->getServicesHealth();
        $httpStatus = $health['all_ok'] ? 200 : 503;
        return response()->json($health, $httpStatus);
    }

    // ─── Webhook ────────────────────────────────────────────────────────────────

    /**
     * Recibe el resultado del análisis desde el Microservicio IA.
     * AgroSentinel llama a este endpoint cuando el análisis termina.
     * Viene desde un servidor externo — se valida con firma HMAC.
     */
    public function receiveWebhook(Request $request)
    {
        // 1. Validar firma HMAC antes de procesar cualquier dato
        if (!$this->validateWebhookSignature($request)) {
            \Log::warning('AgroSentinel webhook: firma inválida', [
                'ip'        => $request->ip(),
                'signature' => $request->header('X-AgroSentinel-Signature'),
            ]);
            return response()->json(['ok' => false, 'error' => 'Firma inválida'], 401);
        }

        $payload = $request->json()->all();

        if (empty($payload['job_id'])) {
            return response()->json(['ok' => false, 'error' => 'job_id requerido'], 400);
        }

        // 2. Actualizar estado del job en BD local
        SentinelJob::where('job_id', $payload['job_id'])->update([
            'status'        => 'completed',
            'analysis_date' => $payload['meta']['analysis_date'] ?? null,
            'completed_at'  => now(),
        ]);

        // 3. Guardar diagnóstico IA
        IaAnalisis::updateOrCreate(
            ['job_id' => $payload['job_id']],
            [
                'parcela_id'    => $payload['lot_id'],
                'fecha'         => $payload['meta']['analysis_date'] ?? now()->toDateString(),
                'ai_provider'   => $payload['meta']['ai_provider'] ?? null,
                'ai_model'      => $payload['meta']['ai_model'] ?? null,
                'config_version'=> $payload['meta']['config_version'] ?? null,
                'risk_level'    => $payload['ai_result']['risk_level']
                                ?? $payload['rules_result']['risk_level']
                                ?? null,
                'summary'          => $payload['ai_result']['summary'] ?? null,
                'probable_causes'  => $payload['ai_result']['probable_causes'] ?? null,
                'recommendations'  => $payload['ai_result']['recommendations'] ?? null,
                'confidence'       => $payload['ai_result']['confidence'] ?? null,
                'limitations'      => $payload['ai_result']['limitations'] ?? null,
                'rules_result'     => $payload['rules_result'] ?? null,
                'image_quality'    => $payload['image_quality'] ?? null,
                'warnings'         => $payload['meta']['warnings'] ?? null,
            ]
        );

        // 4. Guardar índices numéricos en parcela_indices
        if (!empty($payload['indices'])) {
            $fecha = $payload['meta']['analysis_date'] ?? now()->toDateString();
            foreach ($payload['indices'] as $nombre => $stats) {
                ParcelaIndice::updateOrCreate(
                    [
                        'parcela_id' => $payload['lot_id'],
                        'fecha'      => $fecha,
                        'indice'     => strtoupper($nombre),
                    ],
                    [
                        'job_id'          => $payload['job_id'],
                        'valor_min'       => $stats['min'] ?? null,
                        'valor_max'       => $stats['max'] ?? null,
                        'valor_mean'      => $stats['mean'] ?? null,
                        'valor_std'       => $stats['std'] ?? null,
                        'pixeles_validos' => $stats['valid_pixels'] ?? 0,
                        'cloud_coverage'  => $payload['image_quality']['cloud_percentage'] ?? 0,
                    ]
                );
            }
        }

        // 5. Disparar evento Laravel para notificaciones en tiempo real (opcional)
        // event(new AnalisisSatelitalCompletado($payload['lot_id'], $payload['job_id']));

        \Log::info('AgroSentinel webhook recibido', [
            'job_id'     => $payload['job_id'],
            'lot_id'     => $payload['lot_id'],
            'risk_level' => $payload['ai_result']['risk_level'] ?? 'unknown',
        ]);

        // Responder 200 inmediatamente para que AgroSentinel no reintente
        return response()->json(['ok' => true], 200);
    }

    // ─── Privados ───────────────────────────────────────────────────────────────

    private function validateWebhookSignature(Request $request): bool
    {
        $signature = $request->header('X-AgroSentinel-Signature');
        if (empty($signature)) {
            return false;
        }

        $secret   = config('agro_sentinel.webhook_secret');
        $expected = 'sha256=' . hash_hmac('sha256', $request->getContent(), $secret);

        return hash_equals($expected, $signature);
    }
}
```

---

## Rutas en `routes/api.php`

```php
use App\Http\Controllers\SentinelController;

// ─── Rutas autenticadas (usuarios del ERP) ──────────────────────────────────
Route::middleware('auth:sanctum')->prefix('sentinel')->group(function () {

    // Solicitar análisis de un lote
    Route::post('/parcelas/{parcela}/analyze', [SentinelController::class, 'requestAnalysis']);

    // Consultar estado de un análisis en curso (polling)
    Route::get('/jobs/{jobId}/status', [SentinelController::class, 'getJobStatus']);

    // Resultados de un lote (desde BD local)
    Route::get('/parcelas/{parcela}/last-analysis', [SentinelController::class, 'getLotLastAnalysis']);
    Route::get('/parcelas/{parcela}/history', [SentinelController::class, 'getLotHistory']);

    // Alertas activas
    Route::get('/alerts', [SentinelController::class, 'getActiveAlerts']);

    // Estado de los microservicios (para panel admin)
    Route::get('/health', [SentinelController::class, 'getServicesHealth']);
});

// ─── Webhook — sin auth Sanctum, validado por firma HMAC ───────────────────
// AgroSentinel llama a este endpoint desde su servidor externo
Route::post('/sentinel/webhook', [SentinelController::class, 'receiveWebhook'])
    ->withoutMiddleware(['throttle:api']);
// Sin rate limiting para el webhook — AgroSentinel puede reintentarlo 3 veces
```

---

## Modelos Eloquent

### `app/Models/SentinelJob.php`

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class SentinelJob extends Model
{
    protected $fillable = [
        'job_id', 'parcela_id', 'status', 'analysis_date',
        'dates_requested', 'indices_requested', 'requested_at',
        'completed_at', 'error_code', 'error_message',
    ];

    protected $casts = [
        'dates_requested'   => 'array',
        'indices_requested' => 'array',
        'requested_at'      => 'datetime',
        'completed_at'      => 'datetime',
    ];

    public function parcela()
    {
        return $this->belongsTo(Parcela::class);
    }

    public function analisis()
    {
        return $this->hasOne(IaAnalisis::class, 'job_id', 'job_id');
    }
}
```

### `app/Models/IaAnalisis.php`

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class IaAnalisis extends Model
{
    protected $table = 'ia_analisis';

    protected $fillable = [
        'job_id', 'parcela_id', 'fecha', 'ai_provider', 'ai_model',
        'config_version', 'risk_level', 'summary', 'probable_causes',
        'recommendations', 'confidence', 'limitations', 'rules_result',
        'image_quality', 'warnings',
    ];

    protected $casts = [
        'probable_causes' => 'array',
        'recommendations' => 'array',
        'limitations'     => 'array',
        'rules_result'    => 'array',
        'image_quality'   => 'array',
        'warnings'        => 'array',
        'fecha'           => 'date',
    ];

    public function parcela()
    {
        return $this->belongsTo(Parcela::class);
    }

    public function indices()
    {
        return $this->hasMany(ParcelaIndice::class, 'job_id', 'job_id');
    }

    public function getRiskLevelColorAttribute(): string
    {
        return match($this->risk_level) {
            'high'        => 'red',
            'medium_high' => 'orange',
            'medium'      => 'yellow',
            default       => 'green',
        };
    }

    public function getRiskLevelLabelAttribute(): string
    {
        return match($this->risk_level) {
            'high'        => 'Alto',
            'medium_high' => 'Medio-Alto',
            'medium'      => 'Medio',
            default       => 'Bajo',
        };
    }
}
```

---

## Uso desde un controlador o comando artisan

```php
// Solicitar análisis
$service = app(AgroSentinelService::class);

$result = $service->requestAnalysis(
    parcela: $parcela,
    dates:   ['2026-01-01', '2026-01-31'],
    indices: ['NDVI', 'NDMI', 'NDRE'],
);

// job_id para rastrear
$jobId = $result['job_id'];

// Polling manual (opcional mientras se espera webhook)
$status = $service->getJobStatus($jobId);
// { status: "processing" } o { status: "completed", ... }

// Verificar estado de los microservicios
$health = $service->getServicesHealth();
// { tif: { reachable: true, ... }, ia: { reachable: true, ... }, all_ok: true }
```

---

## Criterios de aceptación

- [ ] `POST /api/sentinel/parcelas/{id}/analyze` devuelve 202 con `job_id` en < 1 segundo
- [ ] El `job_id` se guarda en `sentinel_jobs` con status `processing`
- [ ] El webhook llega a Laravel cuando AgroSentinel termina el análisis
- [ ] La firma HMAC se valida — petición sin firma → 401 en log y respuesta
- [ ] El resultado se guarda en `ia_analisis` y `parcela_indices` al recibir el webhook
- [ ] El `sentinel_jobs.status` se actualiza a `completed` al recibir el webhook
- [ ] `GET /api/sentinel/alerts` devuelve lotes con riesgo alto desde la BD local
- [ ] `GET /api/sentinel/health` muestra si los microservicios externos están en línea
- [ ] Si `AGRO_SENTINEL_TIF_URL` no está configurado, devuelve error claro (no excepción genérica)
- [ ] Si el servicio externo no responde, devuelve 503 con mensaje legible
- [ ] Las migraciones corren con `php artisan migrate`

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| Migración `sentinel_jobs` | ⬜ |
| Migración `parcela_indices` | ⬜ |
| Migración `ia_analisis` | ⬜ |
| `app/Exceptions/AgroSentinelException.php` | ⬜ |
| `config/agro_sentinel.php` | ⬜ |
| Variables en `.env` de Laravel | ⬜ |
| `app/Services/AgroSentinelService.php` | ⬜ |
| `app/Http/Controllers/SentinelController.php` | ⬜ |
| `app/Models/SentinelJob.php` | ⬜ |
| `app/Models/IaAnalisis.php` | ⬜ |
| `app/Models/ParcelaIndice.php` | ⬜ |
| Rutas en `routes/api.php` | ⬜ |
| Test: `requestAnalysis` con mock HTTP de AgroSentinel | ⬜ |
| Test: `receiveWebhook` con firma válida e inválida | ⬜ |
| Test: `getJobStatus` con polling | ⬜ |

**Sprint completado:** ⬜