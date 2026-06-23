from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import json, time, random, urllib.parse

app = FastAPI()

# 🔑 TU API KEY DE SCRAPINGBEE ACTIVA
SCRAPINGBEE_API_KEY = "LMYGEFZL35211YDJEFNK30DSG9CYRSMRYZ5JQUQTXW10WC3QO6GXJ7DPLNPEBF1EHWPIQ4FOCOFUA8IG"
SPB = "https://app.scrapingbee.com/api/v1/"

# 🌐 URL del portal de Tenencia del Edomex (SPA Angular)
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
    return {"status": "ok", "message": "Servidor Central - Edomex Optimizada"}

# ==========================================
# 🔥 SECCIÓN ESTADO DE MÉXICO (SOLUCIÓN REAL)
# ==========================================
@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    # Escenario JS: Espera los campos, fulmina el banner de "Cumple hoy" borrándolo del HTML,
    # rellena la placa de forma orgánica y presiona el botón "Aceptar".
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, # Espera que cargue la estructura básica de Angular
            {"wait": 4000},        # 4 segundos clave para que el banner termine de saltar en pantalla
            {"evaluate": f"""
                (() => {{
                    // 1. BOMBA ATÓMICA AL BANNER: Borramos de la existencia cualquier modal,
                    // pop-up, fade o elemento flotante que obstruya la pantalla (incluyendo el banner de 'Cumple hoy')
                    var molestos = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                    molestos.forEach(el => {{
                        try {{ el.remove(); }} catch(e) {{}}
                    }});

                    // Intentar hacer clic en cualquier botón de cerrar (X) por si acaso
                    var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close, [class*='close']");
                    if (cerrarBtn) cerrarBtn.click();

                    // 2. BUSCAR EL INPUT DE LA PLACA
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.value = "{placa}";
                        // Disparar eventos para que el framework de Angular se entere del cambio de texto
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}

                    // 3. SELECCIONAR Y SELLO AL BOTÓN "ACEPTAR"
                    var btnAceptar = document.querySelector("input[type='button'][value='Aceptar'], button, .btn-primary");
                    if (btnAceptar) {{
                        btnAceptar.click();
                    }}
                }})()
            """},
            {"wait": 5000} # Esperamos 5 segundos a que refresque la pantalla con los adeudos reales
        ]
    }
    
    # PARAMETROS TOTALMENTE LIMPIOS (Eliminado solve_captcha que causaba el HTTP 400)
    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_EDOMEX,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true", # Mantiene la IP residencial MX para pasar el reCAPTCHA de forma transparente
        "js_scenario": json.dumps(js_scenario),
        "return_page_source": "true"
    }
    
    try:
        res = requests.get(SPB, params=params, timeout=85)
        
        if res.status_code >= 400:
            return JSONResponse(
                status_code=502,
                content={"detail": f"Portal Edomex no disponible (Proxy Status {res.status_code}): {res.text[:100]}"}
            )
            
        soup = BeautifulSoup(res.text, "html.parser")
        texto_completo = soup.get_text()
        
        vehiculo = "Vehículo registrado (Estado de México)"
        adeudo = "$0.00"
        
        # Extracción inteligente examinando el texto plano y tablas resultantes
        if "total a pagar" in texto_completo.lower() or "importe" in texto_completo.lower():
            for row in soup.find_all("tr"):
                celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(celdas) >= 2:
                    t = " ".join(celdas).lower()
                    if "total" in t or "importe" in t or "pagar" in t:
                        adeudo = celdas[1] if len(celdas[1]) > 1 else celdas[0]
                        break
        elif "no tiene adeudos" in texto_completo.lower() or "al corriente" in texto_completo.lower():
            adeudo = "$0.00"
            vehiculo = "Vehículo sin adeudos vigentes (Al corriente)"

        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Error crítico en backend Edomex: {str(e)}"}
        )

# ==========================================
# ❄️ SECCIÓN VERACRUZ (CONGELADA)
# ==========================================
@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")
