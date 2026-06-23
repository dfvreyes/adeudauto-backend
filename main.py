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
    return {"status": "ok", "message": "Servidor Central - Edomex Auditoria Activa"}

# ==========================================
# 🔥 SECCIÓN ESTADO DE MÉXICO (EXTRACTOR REAL)
# ==========================================
@app.post("/api/edomex/consultar")
async def consultar_edomex(req: ConsultaEstadoRequest):
    if not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")
        
    placa = req.placa.upper().strip()
    
    # Escenario JS Refinado: Borra estorbos, simula clics humanos en el input para burlar 
    # las validaciones del framework y ejecuta el click forzado en Aceptar.
    js_scenario = {
        "instructions": [
            {"wait_for": "input"}, 
            {"wait": 3000},        
            {"evaluate": f"""
                (() => {{
                    // 1. Eliminación radical del banner de 'Cumple hoy' y capas oscuras
                    var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                    overlays.forEach(el => {{ try {{ el.remove(); }} catch(e) {{}} }});

                    var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close, [class*='close']");
                    if (cerrarBtn) cerrarBtn.click();

                    // 2. Selección del campo de placa con simulación de foco humano
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.focus();
                        inputPlaca.click();
                        inputPlaca.value = "{placa}";
                        
                        // Forzado de eventos nativos para engañar los candados del formulario
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    }}

                    // 3. Ubicar y ejecutar clic en el botón de Aceptar
                    var btnAceptar = document.querySelector("input[type='button'][value='Aceptar'], button, .btn-primary, input[type='submit']");
                    if (btnAceptar) {{
                        btnAceptar.focus();
                        btnAceptar.click();
                    }}
                }})()
            """},
            {"wait": 6000} # Damos 6 segundos enteros para que procese la consulta y cargue los adeudos
        ]
    }
    
    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_EDOMEX,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true", # Obligatorio para camuflar la IP contra el reCAPTCHA
        "js_scenario": json.dumps(js_scenario),
        "return_page_source": "true"
    }
    
    try:
        res = requests.get(SPB, params=params, timeout=85)
        
        if res.status_code >= 400:
            return JSONResponse(
                status_code=502,
                content={"detail": f"Error en túnel de ScrapingBee (Status {res.status_code})"}
            )
            
        soup = BeautifulSoup(res.text, "html.parser")
        texto_completo = soup.get_text()
        
        # DETECTOR DE MENTIRAS: Si seguimos viendo el botón 'Aceptar', significa que la página NO avanzó
        if "Aceptar" in texto_completo and "Placa" in texto_completo and "Total a Pagar" not in texto_completo:
            return JSONResponse(
                status_code=422,
                content={"detail": "El portal de Edomex rechazó el envío automático o el reCAPTCHA bloqueó el clic. Intenta de nuevo."}
            )
            
        vehiculo = "Vehículo Identificado (Estado de México)"
        adeudo = None
        
        # Busqueda quirúrgica en las celdas de las tablas de adeudos
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) < 2:
                continue
                
            primera_celda = celdas[0].strip().lower()
            texto_fila = " ".join(celdas).lower()
            
            if "vehículo" in primera_celda or "vehiculo" in primera_celda:
                vehiculo = celdas[1].strip()
            
            if "total a pagar" in texto_fila:
                celdas_limpias = [c.strip() for c in celdas if c.strip()]
                if celdas_limpias:
                    adeudo = celdas_limpias[-1] # Pescamos el valor de la última columna ($2,000.00)

        # Si el flujo pasó pero por alguna razón el parser no leyó el monto
        if adeudo is None:
            if "no tiene adeudos" in texto_completo.lower() or "al corriente" in texto_completo.lower():
                adeudo = "$0.00"
                vehiculo = "Vehículo sin adeudos vigentes"
            else:
                # Si estamos en la página correcta pero las celdas cambiaron de nombre, exponemos un fragmento del texto
                return JSONResponse(
                    status_code=502,
                    content={"detail": f"Logramos entrar al Passat pero cambió la estructura del HTML. Texto visto: {texto_completo[:120]}"}
                )

        return {
            "placa": placa,
            "vehiculo": vehiculo,
            "adeudo": adeudo,
            "estado": "Estado de México"
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Falla en lectura del HTML: {str(e)}"}
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
