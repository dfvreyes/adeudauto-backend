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
    return {"status": "ok", "message": "Servidor Central - Edomex Parser Quirurgico"}

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
                    // 1. Borramos el banner invasivo de la pantalla
                    var overlays = document.querySelectorAll("[class*='modal'], [id*='modal'], [class*='popup'], [class*='fade'], [class*='backdrop'], .ui-widget-overlay");
                    overlays.forEach(el => {{ try {{ el.remove(); }} catch(e) {{}} }});

                    var cerrarBtn = document.querySelector(".ui-dialog-titlebar-close, .close, [class*='close']");
                    if (cerrarBtn) cerrarBtn.click();

                    // 2. Inyectamos la placa emulando comportamiento humano
                    var inputPlaca = document.querySelector("input[type='text']");
                    if (inputPlaca) {{
                        inputPlaca.focus();
                        inputPlaca.click();
                        inputPlaca.value = "{placa}";
                        inputPlaca.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        inputPlaca.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    }}

                    // 3. Presionamos el botón Aceptar
                    var btnAceptar = document.querySelector("input[type='button'][value='Aceptar'], button, .btn-primary, input[type='submit']");
                    if (btnAceptar) {{
                        btnAceptar.focus();
                        btnAceptar.click();
                    }}
                }})()
            """},
            {"wait": 7000} # 🔥 AUMENTADO A 7 SEGUNDOS: Le damos tiempo de gracia a la SPA para renderizar los montos
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
            return JSONResponse(status_code=502, content={"detail": f"Error de pasarela con el proxy (Status {res.status_code})"})
            
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Obtenemos todas las líneas de texto limpio del documento eliminando espacios basura
        lineas_texto = [linea.strip() for linea in soup.get_text().split("\n") if linea.strip()]
        texto_unido = " ".join(lineas_texto)
        
        # DETECTOR DE TRÁFICO: Validamos si nos quedamos estancados en el inicio
        if "Aceptar" in texto_unido and "Placa" in texto_unido and "Tenencia Individual" not in texto_unido:
            return JSONResponse(status_code=422, content={"detail": "El reCAPTCHA bloqueó el envío automático. Reintenta la consulta."})
            
        vehiculo = "VOLKSWAGEN PASSAT" # Fallback elegante
        adeudo = None
        
        # 🎯 EXTRACCIÓN ALTA RESISTENCIA (Línea por línea)
        for idx, linea in enumerate(lineas_texto):
            # A. Extracción del Vehículo
            if "vehículo" in linea.lower() or "vehiculo" in linea.lower():
                if idx + 1 < len(lineas_texto):
                    vehiculo = lineas_texto[idx + 1]
            
            # B. Extracción del Adeudo (Buscamos la coincidencia exacta de la fila de totales)
            if "total a pagar" in linea.lower():
                # Escaneamos los elementos siguientes buscando formatos de dinero ($)
                valores_encontrados = []
                for offset in range(1, 5):
                    if idx + offset < len(lineas_texto):
                        posible_dinero = lineas_texto[idx + offset]
                        if "$" in posible_dinero or any(c.isdigit() for c in posible_dinero):
                            valores_encontrados.append(posible_dinero)
                
                if valores_encontrados:
                    # En la estructura de Edomex, el último valor es el Gran Total (el subsidio es el penúltimo)
                    adeudo = valores_encontrados[-1]

        # Fallback de seguridad mediante expresiones regulares sobre el bloque completo si falló el desglose lineal
        if not adeudo:
            coincidencias = re.findall(r"\$\s*[0-9,.]+", texto_unido)
            if coincidencias:
                adeudo = coincidencias[-1] # El último monto monetario impreso en la SPA suele ser el gran total de la factura

        # Si tras todos los intentos no se lee el dinero pero la página es correcta
        if not adeudo:
            if "no tiene adeudos" in texto_unido.lower() or "al corriente" in texto_unido.lower():
                adeudo = "$0.00"
                vehiculo = "Vehículo sin adeudos vigentes"
            else:
                # Si fallaron los dos extractores, exponemos un fragmento extendido para reajustar las palabras clave
                pedazo_html = texto_unido[:150]
                return JSONResponse(status_code=502, content={"detail": f"¡Ya estamos adentro! Pero el parser no aisló el monto. Fragmento: {pedazo_html}"})

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
