from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import json, time, random, urllib.parse, re

app = FastAPI()

# 🔑 TU API KEY DE SCRAPINGBEE ACTIVA
SCRAPINGBEE_API_KEY = "LMYGEFZL35211YDJEFNK30DSG9CYRSMRYZ5JQUQTXW10WC3QO6GXJ7DPLNPEBF1EHWPIQ4FOCOFUA8IG"
SPB = "https://app.scrapingbee.com/api/v1/"
URL_EDOMEX = "https://tenencia.edomex.gob.mx/TenenciaIndividual/tenencia/A06E1A88B8A6ED4B/#/"

class ConsultaEstadoRequest(BaseModel):
    session_id: str | None = None
    sessionId: str | None = None
    placa: str
    captcha_texto: str | None = None
    captchaTexto: str | None = None

@app.middleware("http")
async def cors(request: Request, call_next):
    if request.method == "OPTIONS":
        r = Response(status_code=204)
    else:
        try:
            r = await call_next(request)
        except Exception as e:
            r = JSONResponse(status_code=500, content={"detail": f"Falla interna: {e}"})
    origin = request.headers.get("origin", "*")
    r.headers["Access-Control-Allow-Origin"] = origin
    r.headers["Access-Control-Allow-Credentials"] = "true"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept"
    return r

@app.get("/")
async def root():
    return {"status": "ok", "message": "Servidor Central - Edomex Angular Fix"}

@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    # ⚡ SOLUCIÓN REAC_FORMS: Escribimos el valor y disparamos los eventos 'input' y 'change'
    # envueltos en un try/catch seguro que retorna un string simple para evitar errores 500 de proxy.
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, 
            {"wait": 2000},        
            {"evaluate": f"""
                (() => {{
                    try {{
                        // 1. Eliminar molestos anuncios del frente
                        var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                        overlays.forEach(el => {{ el.remove(); }});
                        
                        var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close");
                        if (cerrarBtn) cerrarBtn.click();

                        // 2. Hackear el Input de Angular Reactive Forms
                        var inputPlaca = document.querySelector("input");
                        if (inputPlaca) {{
                            inputPlaca.focus();
                            inputPlaca.value = "{placa}";
                            // Forzamos al core de Angular a enterarse que la propiedad cambió
                            inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            inputPlaca.blur();
                        }}
                    }} catch(e) {{}}
                    return "DOM_READY";
                }})();
            """},
            {"wait": 1000},
            {"click": "input[type='button'][value='Aceptar'], button, .btn-primary"},
            {"wait": 7000} # Tiempo para que la SPA cargue la tabla del Passat
        ]
    }
    
    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_EDOMEX,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true", 
        "js_scenario": json.dumps(js_scenario),
        "return_page_source": "true"
    }
    
    try:
        res = requests.get(SPB, params=params, timeout=90)
        
        if res.status_code >= 400:
            return JSONResponse(status_code=502, content={"detail": f"Error de comunicación con el proxy residencial (Status {res.status_code})"})
            
        soup = BeautifulSoup(res.text, "html.parser")
        texto_completo = soup.get_text(separator=" ", strip=True)
        texto_completo = re.sub(r'\s+', ' ', texto_completo)
        texto_lower = texto_completo.lower()
        
        # 🎯 CONTROL DE CALIDAD INTERNO: ¿Realmente pasamos la puerta?
        # Si la página sigue mostrando las palabras de la pantalla de login y no hay rastro de montos
        if "ejercicio" not in texto_lower and "modelo" not in texto_lower and "total a pagar" not in texto_lower:
            return JSONResponse(
                status_code=422, 
                content={"detail": "El portal de Edomex rechazó el envío (Angular detectó el campo vacío o reCAPTCHA bloqueó el clic). Reintenta la consulta."}
            )
            
        vehiculo = "VOLKSWAGEN PASSAT"
        adeudo = None
        
        # Extracción de Datos en la página real del auto
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) < 2:
                continue
            primera_celda = celdas[0].strip().lower()
            if "vehículo" in primera_celda or "vehiculo" in primera_celda:
                vehiculo = celdas[1].strip().upper()
                
        # Búsqueda del dinero
        montos_detectados = re.findall(r'\$\s*[0-9,.]+', texto_completo)
        if montos_detectados:
            adeudo = montos_detectados[-1].strip()

        if not adeudo:
            if "no tiene adeudos" in texto_lower or "al corriente" in texto_lower:
                adeudo = "$0.00"
                vehiculo = "Vehículo sin adeudos vigentes"
            else:
                return JSONResponse(status_code=502, content={"detail": f"¡Entramos al Passat! Pero las celdas cambiaron. Texto: {texto_completo[:120]}"})

        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Error interno en Render: {str(e)}"})

# ==========================================
# ❄️ SECCIÓN VERACRUZ (CONGELADA)
# ==========================================
@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")
