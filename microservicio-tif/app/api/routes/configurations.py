from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.services.crop_config_store import CropConfigStore

router = APIRouter(prefix="/configurations", tags=["configurations"])
store = CropConfigStore()


@router.get("", response_class=HTMLResponse)
async def configurations_view() -> str:
    return CONFIG_HTML


@router.get("/crops")
async def get_crop_config():
    return {"ok": True, "data": store.read()}


@router.put("/crops")
async def replace_crop_config(payload: dict[str, Any]):
    if "crops" not in payload or not isinstance(payload["crops"], dict):
        raise HTTPException(status_code=400, detail="Payload must include crops object")
    return {"ok": True, "data": store.write(payload)}


@router.post("/crops/variety")
async def upsert_variety(payload: dict[str, Any]):
    crop = str(payload.get("crop") or "").strip()
    variety = str(payload.get("variety") or "").strip()
    data = payload.get("data")
    if not crop or not variety or not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="crop, variety and data are required")
    return {"ok": True, "data": store.upsert_crop_variety(crop=crop, variety=variety, data=data)}


CONFIG_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Configuraciones AgroSentinel</title>
  <style>
    :root{--bg:#0f1115;--panel:#1a1f26;--border:#2e3743;--txt:#ecf2ea;--muted:#8ea08f;--accent:#3c8d5a}
    body{margin:0;font-family:Segoe UI,sans-serif;background:var(--bg);color:var(--txt)}
    .app{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
    .side{background:#171b20;border-right:1px solid var(--border);padding:20px}
    .brand{font-size:22px;font-weight:800;margin-bottom:20px}
    .item{padding:10px 12px;border-radius:8px;color:#c9d7cb;margin-bottom:8px;background:#1d232b}
    .item a{color:inherit;text-decoration:none;display:block}
    .item.active{background:#24303d;color:#e8f8ee}
    .main{padding:22px}
    .wrap{max-width:1100px}
    .card{background:#1a1f26;border:1px solid #2e3743;border-radius:12px;padding:14px;margin-bottom:14px}
    input,textarea{width:100%;padding:10px;border-radius:8px;border:1px solid #2e3743;background:#0f151d;color:#cfe6d4}
    textarea{min-height:220px}
    button{background:#3c8d5a;color:#fff;border:0;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer}
    .row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    a{color:#9cd8b0}
    @media(max-width:1050px){.app{grid-template-columns:1fr}.side{display:none}}
  </style>
</head>
<body>
  <div class="app">
    <aside class="side">
      <div class="brand">AgroSentinel</div>
      <div class="item"><a href="/scene/tile">Lotes y cultivos</a></div>
      <div class="item active"><a href="/configurations">Configuracion variedades</a></div>
    </aside>
    <main class="main">
      <div class="wrap">
        <div class="card">
          <h2 style="margin-top:0">Configuraciones de cultivos y variedades</h2>
          <p><a href="/scene/tile">Volver al dashboard</a></p>
        </div>
        <div class="card">
          <h3 style="margin-top:0">Agregar/editar variedad</h3>
          <div class="row">
            <input id="crop" placeholder="Articulo/cultivo (ej: LECHUGA)" />
            <input id="variety" placeholder="Variedad (ej: ANTANAS)" />
          </div>
          <textarea id="varietyData" placeholder='{"ndvi_optimo_min":0.64,"ndmi_optimo_min":0.22,"dias_cosecha_estimados":65}'></textarea>
          <button id="saveVariety">Guardar variedad</button>
          <div id="status"></div>
        </div>
        <div class="card">
          <h3 style="margin-top:0">JSON completo (crear/editar todo)</h3>
          <textarea id="fullJson"></textarea>
          <button id="reload">Recargar</button>
          <button id="saveAll">Guardar todo</button>
        </div>
      </div>
    </main>
  </div>
  <script>
    const full = document.getElementById("fullJson");
    const status = document.getElementById("status");
    async function reload(){
      const r = await fetch("/configurations/crops");
      const d = await r.json();
      full.value = JSON.stringify(d.data || {}, null, 2);
    }
    document.getElementById("reload").onclick = reload;
    document.getElementById("saveAll").onclick = async () => {
      try{
        const payload = JSON.parse(full.value);
        const r = await fetch("/configurations/crops",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
        const d = await r.json();
        status.textContent = r.ok ? "Configuracion guardada" : (d.detail || "Error");
      }catch(e){ status.textContent = "JSON invalido"; }
    };
    document.getElementById("saveVariety").onclick = async () => {
      try{
        const payload = {
          crop: document.getElementById("crop").value,
          variety: document.getElementById("variety").value,
          data: JSON.parse(document.getElementById("varietyData").value || "{}")
        };
        const r = await fetch("/configurations/crops/variety",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
        const d = await r.json();
        status.textContent = r.ok ? "Variedad guardada" : (d.detail || "Error");
        if(r.ok){ full.value = JSON.stringify(d.data || {}, null, 2); }
      }catch(e){ status.textContent = "JSON de variedad invalido"; }
    };
    reload();
  </script>
</body>
</html>
"""
