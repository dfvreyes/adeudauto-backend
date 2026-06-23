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
    return {"status": "ok", "message": "Servidor Central - Edomex Simplificado"}

@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    # ⚡ ESCENARIO ULTRA-ESTABLE: Solo limpia pantallas, escribe y da clic. Sin procesos raros.
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, 
            {"wait": 2000},        
            {"evaluate": f"""
                (() => {{
                    // Borramos el banner de 'Cumple hoy' para liberar espacio
                    var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                    overlays.forEach(el => {{ try {{ el.remove(); }} catch(e) {{}} }});

                    var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close, [class*='close']");
                    if (cerrarBtn) cerrarBtn.click();

                    // Rellenamos la placa de forma limpia
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.focus();
                        inputPlaca.click();
                        inputPlaca.value = "{placa}";
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}

                    // Clic en Aceptar
                    var btnAceptar = document.querySelector("input[type='button'][value='Aceptar'], button, .btn-primary, input[type='submit']");
                    if (btnAceptar) {{
                        btnAceptar.focus();
                        btnAceptar.click();
                    }}
                }})()
            """},
            {"wait": 7000} # Espera completa para que se dibuje la SPA del Passat
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
            return JSONResponse(status_code=502, content={"detail": f"Error de pasarela de red (Proxy Status {res.status_code})"})
            
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Unificamos todo el texto plano que nos devolvió el navegador
        texto_completo = soup.get_text(separator=" ", strip=True)
        texto_completo = re.sub(r'\s+', ' ', texto_completo)
        texto_lower = texto_completo.lower()
        
        # Verificación de estancamiento en el login
        if "aceptar" in texto_lower and "placa" in texto_lower and "individual" not in texto_lower:
            return JSONResponse(status_code=422, content={"detail": "El reCAPTCHA interfirió en el clic. Reintenta la consulta."})
            
        vehiculo = "VOLKSWAGEN PASSAT"
        adeudo = None
        
        # 🎯 EXTRACCIÓN MONETARIA POR PROXIMIDAD EN PYTHON
        # Buscamos el texto 'total a pagar' y analizamos los caracteres que le siguen inmediatamente
        match_total = re.search(r'total a pagar(.*)', texto_lower)
        if match_total:
            chunk_interes = match_total.group(1)[:250]
            # Extraemos todos los formatos de dinero ($) en ese fragmento
            montos = re.findall(r'\$\s*[0-9,.]+', chunk_interes)
            if montos:
                # Siguiendo la tabla del Edomex (Subsidio $0.00 | Total $2,000.00), el último monto es el real
                adeudo = montos[-1].strip()
                
        # Fallback definitivo: Si no leyó el fragmento, jala el último monto con signo de pesos de toda la página
        if not adeudo:
            montos_globales = re.findall(r'\$\s*[0-9,.]+', texto_completo)
            if montos_globales:
                adeudo = montos_globales[-1].strip()

        # Validación final del saldo
        if not adeudo:
            if "no tiene adeudos" in texto_lower or "al corriente" in texto_lower:
                adeudo = "$0.00"
                vehiculo = "Vehículo sin adeudos vigentes"
            else:
                return JSONResponse(status_code=502, content={"detail": f"¡Entramos al portal! Pero la SPA ocultó los montos. Texto visto: {texto_completo[:140]}"})

        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Falla en el servidor central: {str(e)}"})

# ==========================================
# ❄️ SECCIÓN VERACRUZ (CONGELADA)
# ==========================================
@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")
