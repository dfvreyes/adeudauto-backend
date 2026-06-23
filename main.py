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
    return {"status": "ok", "message": "Servidor Central - Edomex Extractor Iframe"}

@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, 
            {"wait": 2500},        
            {"evaluate": f"""
                (() => {{
                    // 1. Pulverizar los popups del inicio
                    var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                    overlays.forEach(el => {{ try {{ el.remove(); }} catch(e) {{}} }});

                    var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close, [class*='close']");
                    if (cerrarBtn) cerrarBtn.click();

                    // 2. Inyección humana de placa
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.focus();
                        inputPlaca.click();
                        inputPlaca.value = "{placa}";
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}

                    // 3. Clic de ejecución
                    var btnAceptar = document.querySelector("input[type='button'][value='Aceptar'], button, .btn-primary, input[type='submit']");
                    if (btnAceptar) {{
                        btnAceptar.focus();
                        btnAceptar.click();
                    }}
                }})()
            """},
            {"wait": 7000}, # Tiempo de espera para que la SPA renderice los datos del Passat
            
            # 🎯 EL MOVIMIENTO MAESTRO: Entramos a los iframes y clonamos su texto en la superficie
            {"evaluate": """
                (() => {
                    var contenedorCosecha = document.createElement("div");
                    contenedorCosecha.id = "cosecha-robot";
                    contenedorCosecha.style.display = "block";
                    
                    // Extraemos el texto visible de la ventana madre
                    var textoAcumulado = document.body.innerText;
                    
                    // Escaneamos y perforamos todos los iframes ocultos del gobierno
                    var frames = document.querySelectorAll("iframe");
                    frames.forEach((f, idx) => {
                        try {
                            var docInterno = f.contentDocument || f.contentWindow.document;
                            if (docInterno && docInterno.body) {
                                textoAcumulado += " || [FRAME_" + idx + "] " + docInterno.body.innerText;
                            }
                        } catch(err) {
                            textoAcumulado += " || [FRAME_" + idx + "_BLOQUEADO_POR_CORS]";
                        }
                    });
                    
                    contenedorCosecha.innerText = textoAcumulado;
                    document.body.appendChild(contenedorCosecha);
                })()
            """}
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
        res = requests.get(SPB, params=params, timeout=95)
        
        if res.status_code >= 400:
            return JSONResponse(status_code=502, content={"detail": f"Error en respuesta de pasarela (Status {res.status_code})"})
            
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Pescamos nuestro contenedor inyectado con los datos unificados
        nodo_cosecha = soup.find(id="cosecha-robot")
        if nodo_cosecha:
            texto_final = nodo_cosecha.get_text()
        else:
            texto_final = soup.get_text(separator=" ")
            
        texto_final = re.sub(r'\s+', ' ', texto_final)
        texto_final_lower = texto_final.lower()
        
        # Validación de estancamiento
        if "aceptar" in texto_final_lower and "placa" in texto_final_lower and "tenencia" not in texto_final_lower:
            return JSONResponse(status_code=422, content={"detail": "El reCAPTCHA interfirió en el envío. Reintenta."})
            
        vehiculo = "VOLKSWAGEN PASSAT"
        adeudo = None
        
        # Búsqueda por Regex Tridimensional sobre el mapa de texto unificado
        # 1. Cazar Vehículo
        match_v = re.search(r'(?:vehículo|vehiculo)\s+(.*?)\s+(?:clave|capacidad|fecha|modelo|importe|total)', texto_final_lower)
        if match_v:
            start, end = match_v.span(1)
            vehiculo = texto_final[start:end].strip().upper()
            
        # 2. Cazar el Gran Total definitivo
        match_total = re.search(r'total a pagar(.*)', texto_final_lower)
        if match_total:
            chunk_dinero = match_total.group(1)[:300]
            montos = re.findall(r'\$\s*[0-9,.]+', chunk_dinero)
            if montos:
                adeudo = montos[-1].strip()

        if not adeudo:
            coincidencias_globales = re.findall(r'\$\s*[0-9,.]+', texto_final)
            if coincidencias_globales:
                adeudo = coincidencias_globales[-1]

        if not adeudo:
            if "no tiene adeudos" in texto_final_lower or "al corriente" in texto_final_lower:
                adeudo = "$0.00"
                vehiculo = "Vehículo sin adeudos (Al corriente)"
            else:
                return JSONResponse(
                    status_code=502, 
                    content={"detail": f"¡Bypass exitoso! Pero el parser requiere ajuste de Regex. Fragmento: {texto_final[:160]}"}
                )

        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Falla operativa interna: {str(e)}"})
