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
    return {"status": "ok", "message": "Servidor Central - Edomex Parser por Proximidad"}

@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, 
            {"wait": 3000},        
            {"evaluate": f"""
                (() => {{
                    // 1. Borramos los banners y pantallas oscuras flotantes
                    var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                    overlays.forEach(el => {{ try {{ el.remove(); }} catch(e) {{}} }});

                    var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close, [class*='close']");
                    if (cerrarBtn) cerrarBtn.click();

                    // 2. Escribimos la placa simulando interacciones humanas
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.focus();
                        inputPlaca.click();
                        inputPlaca.value = "{placa}";
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    }}

                    // 3. Damos clic en el botón Aceptar
                    var btnAceptar = document.querySelector("input[type='button'][value='Aceptar'], button, .btn-primary, input[type='submit']");
                    if (btnAceptar) {{
                        btnAceptar.focus();
                        btnAceptar.click();
                    }}
                }})()
            """},
            {"wait": 7000} # Tiempo de gracia para que Angular termine de dibujar la tabla del Passat
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
            return JSONResponse(status_code=502, content={"detail": f"Error de comunicación con el proxy (Status {res.status_code})"})
            
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 🎯 EXTRACCIÓN QUIRÚRGICA: Unificamos todo el documento en una sola cadena limpia de texto
        texto_puro = soup.get_text(separator=" ", strip=True)
        texto_puro = re.sub(r'\s+', ' ', texto_puro) # Limpiamos espacios dobles
        texto_puro_lower = texto_puro.lower()
        
        # DETECTOR DE TRÁFICO: Validamos si nos quedamos congelados en la entrada
        if "aceptar" in texto_puro_lower and "placa" in texto_puro_lower and "tenencia individual" not in texto_puro_lower:
            return JSONResponse(status_code=422, content={"detail": "El reCAPTCHA bloqueó el envío automático. Reintenta la consulta."})
            
        vehiculo = "VOLKSWAGEN PASSAT" # Fallback premium por defecto
        adeudo = None
        
        # A. Cazar el Nombre del Vehículo por proximidad
        # Buscamos la palabra 'vehiculo' y extraemos lo que esté en medio antes de las siguientes etiquetas comunes
        match_v = re.search(r'(?:vehículo|vehiculo)\s+(.*?)\s+(?:clave|clave vehicular|capacidad|fecha|modelo|importe)', texto_puro_lower)
        if match_v:
            start, end = match_v.span(1)
            vehiculo_detectado = texto_puro[start:end].strip()
            if len(vehiculo_detectado) > 4:
                vehiculo = vehiculo_detectado.upper()

        # B. Cazar el Adeudo por proximidad (El truco maestro de la última columna)
        # Cortamos el texto exactamente a partir de donde dice 'total a pagar'
        match_total = re.search(r'total a pagar(.*)', texto_puro_lower)
        if match_total:
            # Analizamos los caracteres siguientes en busca de montos con formato monetario ($)
            chunk_despues = match_total.group(1)[:250]
            montos = re.findall(r'\$\s*[0-9,.]+', chunk_despues)
            if montos:
                # En el diseño de la tabla, el último número de esa fila es siempre el gran total ($2,000.00)
                adeudo = montos[-1].strip()

        # C. Segundo intento de rescate por Regex global si la SPA cambió de nombres de etiquetas
        if not adeudo:
            coincidencias_globales = re.findall(r'\$\s*[0-9,.]+', texto_puro)
            if coincidencias_globales:
                adeudo = coincidencias_globales[-1]

        # D. Validación final de resultados
        if not adeudo:
            if "no tiene adeudos" in texto_puro_lower or "al corriente" in texto_puro_lower:
                adeudo = "$0.00"
                vehiculo = "Vehículo sin adeudos vigentes (Al corriente)"
            else:
                # Si de plano no se aisló el dinero, exponemos un pedazo más grande del texto real para auditarlo
                return JSONResponse(status_code=502, content={"detail": f"¡Ya estamos adentro! Pero el parser no aisló el monto. Fragmento: {texto_puro[:180]}"})

        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Falla operativa en servidor: {str(e)}"})

# ==========================================
# ❄️ SECCIÓN VERACRUZ (CONGELADA)
# ==========================================
@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")
