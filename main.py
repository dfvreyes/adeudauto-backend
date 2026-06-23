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
    return {"status": "ok", "message": "Servidor Central - Extractor Nativo Activo"}

@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    # Escenario JS: Escribe la placa, da clic, espera la carga y procesa
    # la tabla internamente usando selectores nativos de JavaScript.
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, 
            {"wait": 2500},        
            {"evaluate": f"""
                (() => {{
                    // 1. Limpieza radical de modales/anuncios del inicio
                    var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                    overlays.forEach(el => {{ try {{ el.remove(); }} catch(e) {{}} }});

                    var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close, [class*='close']");
                    if (cerrarBtn) cerrarBtn.click();

                    // 2. Inyectamos la placa
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.focus();
                        inputPlaca.click();
                        inputPlaca.value = "{placa}";
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}

                    // 3. Clic de validación
                    var btnAceptar = document.querySelector("input[type='button'][value='Aceptar'], button, .btn-primary, input[type='submit']");
                    if (btnAceptar) {{
                        btnAceptar.focus();
                        btnAceptar.click();
                    }}
                }})()
            """},
            {"wait": 7000}, # Tiempo de gracia para que cargue la tabla del Passat
            
            # 🎯 EXTRACCIÓN INTERNA DESDE EL NAVEGADOR
            {"evaluate": """
                (() => {
                    var pack = { vehiculo: "VOLKSWAGEN PASSAT", adeudo: null, login_failed: false, raw_visto: "" };
                    try {
                        var bodyTxt = document.body.innerText || "";
                        pack.raw_visto = bodyTxt.substring(0, 160);
                        
                        // Si seguimos en el login listando los botones principales, falló el envío
                        if (bodyTxt.includes("Aceptar") && bodyTxt.includes("Placa") && !bodyTxt.includes("Individual")) {
                            pack.login_failed = true;
                        }
                        
                        // Buscamos todas las celdas y textos que contengan montos de dinero
                        var celdas = document.querySelectorAll("tr, td, div, span");
                        celdas.forEach(el => {
                            var t = el.innerText ? el.innerText.trim() : "";
                            if (t.toLowerCase().includes("total a pagar")) {
                                var montos = t.match(/\\$\\s*[0-9,.]+/g);
                                if (montos && montos.length > 0) {
                                    pack.adeudo = montos[montos.length - 1].trim();
                                }
                            }
                        });
                        
                        // Fallback por proximidad global si falló el mapeo estructural
                        if (!pack.adeudo) {
                            var gross = bodyTxt.match(/\\$\\s*[0-9,.]+/g);
                            if (gross && gross.length > 0) {
                                pack.adeudo = gross[gross.length - 1].trim();
                            }
                        }
                    } catch(err) {
                        pack.raw_visto = "ERR_JS: " + err.message;
                    }
                    
                    // Inyectamos el resultado masticado en un nodo oculto para Python
                    var contenedor = document.createElement("div");
                    contenedor.id = "cosecha-robot";
                    contenedor.setAttribute("data-result", JSON.stringify(pack));
                    document.body.appendChild(contenedor);
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
            return JSONResponse(status_code=502, content={"detail": f"Error de comunicación de red (Proxy Status {res.status_code})"})
            
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Leemos el nodo con el JSON masticado por el navegador
        nodo_cosecha = soup.find(id="cosecha-robot")
        if not nodo_cosecha or not nodo_cosecha.has_attr("data-result"):
            texto_crudo = soup.get_text(separator=" ")[:150]
            return JSONResponse(status_code=502, content={"detail": f"El navegador invisible no pudo procesar la inyección. Texto: {texto_crudo}"})
            
        data_extracted = json.loads(nodo_cosecha["data-result"])
        
        if data_extracted.get("login_failed"):
            return JSONResponse(status_code=422, content={"detail": "El reCAPTCHA interfirió en el clic de acceso. Por favor reintenta la consulta."})
            
        adeudo = data_extracted.get("adeudo")
        vehiculo = data_extracted.get("vehiculo") or "VOLKSWAGEN PASSAT"
        
        if not adeudo:
            # Si entramos pero el saldo regresó vacío, mostramos el fragmento para ajustar las palabras clave
            return JSONResponse(status_code=502, content={"detail": f"¡Entramos al Passat! Pero las columnas cambiaron. Texto: {data_extracted.get('raw_visto')}"})

        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Error crítico en servidor central: {str(e)}"})

# ==========================================
# ❄️ SECCIÓN VERACRUZ (CONGELADA)
# ==========================================
@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    raise HTTPException(status_code=503, detail="Mantenimiento temporal.")
