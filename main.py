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

# 🌐 URL real del portal de Tenencia del Edomex
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
    return {"status": "ok", "message": "Servidor Central - Edomex con reCAPTCHA"}

# ==========================================
# 🔥 SECCIÓN ESTADO DE MÉXICO (EDOMEX CON SOLVER)
# ==========================================
@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    # Escenario JS: Desaparece el anuncio del camino, escribe la placa, 
    # espera a que ScrapingBee resuelva el reCAPTCHA y da clic en Aceptar.
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, # Espera a que cargue la SPA
            {"wait": 2000},
            {"evaluate": f"""
                (() => {{
                    // 1. TRUCO DE MAGIA: Buscamos el anuncio pop-up y cualquier fondo oscuro y lo eliminamos del mapa
                    // para que no estorbe visualmente al dar clics
                    var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade']");
                    overlays.forEach(el => el.remove());
                    
                    // Si hay un boton de cerrar 'X' del anuncio, tambien lo presionamos por si acaso
                    var closeBtn = document.querySelector(".close, [class*='close'], button[aria-label='Close']");
                    if (closeBtn) closeBtn.click();

                    // 2. Localizamos el campo de la placa de forma segura
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.value = "{placa}";
                        // Forzamos eventos para que Angular/React se enteren que ya escribimos
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }})()
            """},
            {"wait": 1000},
            # 3. Presionamos el botón "Aceptar" que envía el formulario
            {"click": "input[type='button'][value='Aceptar'], button, input[type='submit']"},
            {"wait": 5000} # Esperamos 5 segundos a que la página procese y cargue la tabla de adeudos
        ]
    }
    
    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_EDOMEX,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true",  # IP residencial mexicana para que Google no sospeche
        "solve_captcha": "true",  # 🔥 LA LLAVE MAESTRA: Resuelve el 'No soy un robot' en automático
        "js_scenario": json.dumps(js_scenario),
        "return_page_source": "true"
    }
    
    try:
        res = requests.get(SPB, params=params, timeout=80)
        
        if res.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Falla de comunicación con el portal: {res.status_code}")
            
        soup = BeautifulSoup(res.text, "html.parser")
        texto_completo = soup.get_text()
        
        vehiculo = "Vehículo registrado en el Estado de México"
        adeudo = "$0.00"
        
        # Parseo inteligente de los datos impresos en pantalla
        if "total a pagar" in texto_completo.lower():
            for row in soup.find_all("tr"):
                celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(celdas) >= 2:
                    t = " ".join(celdas).lower()
                    if "total" in t or "importe" in t or "pagar" in t:
                        adeudo = celdas[1] if len(celdas[1]) > 1 else celdas[0]
                        break
        elif "no tiene adeudos" in texto_completo.lower() or "vehículo al corriente" in texto_completo.lower():
            adeudo = "$0.00"
            vehiculo = "Vehículo sin adeudos vigentes"
            
        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en procesamiento de Edomex: {str(e)}")

# ==========================================
# ❄️ SECCIÓN VERACRUZ (CONGELADA)
# ==========================================
@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    raise HTTPException(status_code=503, detail="Mantenimiento.")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    raise HTTPException(status_code=503, detail="Mantenimiento.")
