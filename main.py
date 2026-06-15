from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import json
import base64
import time

app = FastAPI()

# 🔑 COLOCA AQUÍ TU API KEY REAL DE SCRAPINGBEE
SCRAPINGBEE_API_KEY = "YXCMEMCHIH28ATRP4YVX4RK3J0P9DR3EYAR622BAH9JATN16PLPPP84LDZ6V487NK6JKOR9S0F14WARV"

sesiones_globales = {}

class ConsultaEstadoRequest(BaseModel):
    session_id: str = None
    sessionId: str = None
    placa: str
    captcha_texto: str = None
    captchaTexto: str = None

@app.middleware("http")
async def cors_interceptor_universal(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=204)
        origin = request.headers.get("origin", "*")
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
        return response

    try:
        response = await call_next(request)
    except Exception as e:
        response = JSONResponse(
            status_code=500,
            content={"status": "error", "detail": f"Falla interna: {str(e)}"}
        )

    origin = request.headers.get("origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
    return response

@app.get("/")
async def root():
    return {"status": "ok", "message": "Servidor Centralizado - Extractor por Canvas Activo"}


@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")

    url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    # 🎭 ESCENARIO JAVASCRIPT: Le ordenamos al navegador invisible de ScrapingBee 
    # que dibuje la imagen del captcha en un lienzo virtual (Canvas) y extraiga el Base64 puro.
    # Así evitamos hacer la segunda petición que bloquea Radware.
    instrucciones_js = {
        "instructions": [
            {"wait_for": "img[src*='jcaptcha']"}, # Espera a que la imagen del captcha aparezca en pantalla
            {"wait": 2000}, # Espera 2 segundos extra para asegurar que se rendericen los píxeles
            {
                "evaluate": """
                (() => {
                    var img = document.querySelector("img[src*='jcaptcha']");
                    if (!img) return "ERROR: No se encontro el elemento img del captcha";
                    
                    var canvas = document.createElement("canvas");
                    canvas.width = img.naturalWidth || img.width;
                    canvas.height = img.naturalHeight || img.height;
                    
                    var ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0);
                    
                    return canvas.toDataURL("image/png");
                })()
                """
            }
        ]
    }
    
    try:
        params_inicio = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_principal,
            "country_code": "mx",
            "render_js": "true",          # Abre navegador realheadless
            "premium_proxy": "true",       # Forzar IPs residenciales limpias de alta reputación
            "js_scenario": json.dumps(instrucciones_js), # Inyectamos nuestro script extractor de pixeles
            "forward_headers": "true"
        }
        
        # Esta consulta puede tardar de 15 a 25 segundos ya que ScrapingBee abre el sitio entero
        res_inicio = requests.get(spb_endpoint, params=params_inicio, timeout=55)
        
        # Validamos si Radware bloqueó el navegador antes del script
        if b"Radware Captcha Page" in res_inicio.content or b"hcaptcha" in res_inicio.content:
            raise HTTPException(status_code=503, detail="Radware bloqueó el navegador simulado. Reintenta la consulta.")

        # Buscamos la respuesta de nuestro script JS en los headers especiales de ScrapingBee
        captcha_base64_puro = res_inicio.headers.get("X-ScrapingBee-Js-Scenario-Result")
        
        # Fallback: Si no vino en el header, buscamos si ScrapingBee la escupió en el cuerpo de la respuesta JSON
        if not captcha_base64_puro:
            try:
                datos_json = res_inicio.json()
                captcha_base64_puro = datos_json.get("js_scenario", {}).get("result")
            except:
                pass

        if not captcha_base64_puro or "ERROR" in str(captcha_base64_puro) or "data:image" not in str(captcha_base64_puro):
            raise HTTPException(status_code=502, detail="No se pudo extraer los pixeles del captcha. Reintenta la recarga.")

        # Recolectamos las cookies vivas de la sesión para poder hacer la consulta posterior
        cookies_dict = {}
        if res_inicio.cookies:
            for cookie in res_inicio.cookies:
                cookies_dict[cookie.name] = cookie.value
                
        session_id = str(int(time.time()))
        sesiones_globales[session_id] = cookies_dict
        
        return {
            "session_id": session_id,
            "sessionId": session_id,
            "captcha_image": captcha_base64_puro, # Ya viene con el formato "data:image/png;base64,..."
            "captchaImage": captcha_base64_puro
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falla en extracción por Canvas: {str(e)}")


@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    id_sesion = req.session_id or req.sessionId
    texto_captcha = req.captcha_texto or req.captchaTexto
    
    cookies = sesiones_globales.get(id_sesion)
    if not cookies:
        raise HTTPException(status_code=400, detail="Sesión expirada. Recarga el captcha.")
        
    url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        payload = {
            "pPlaca": req.placa.upper().strip(),
            "pTextoSeguridad": texto_captcha.strip() if texto_captcha else ""
        }
        payload_encoded = urllib.parse.urlencode(payload)
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        
        params_post = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_post,
            "country_code": "mx",
            "render_js": "true",
            "premium_proxy": "true",
            "forward_headers": "true"
        }
        
        headers_post = {
            "Cookie": cookie_string,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.post(spb_endpoint, params=params_post, headers=headers_post, data=payload_encoded, timeout=50)
        
        if b"Radware" in response.content:
            raise HTTPException(status_code=502, detail="Radware interceptó el envío del formulario.")
            
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El captcha ingresado es incorrecto.")
            
        datos_vehiculo = "Vehículo sin adeudos o no registrado en Veracruz"
        monto_adeudo = "$0.00"
        
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) >= 2:
                texto_unido = " ".join(celdas)
                if "Vehículo" in texto_unido or "Modelo" in texto_unido:
                    datos_vehiculo = celdas[1]
                if "Total" in texto_unido or "Pagar" in texto_unido:
                    monto_adeudo = celdas[1]

        return {
            "placa": req.placa.upper(),
            "vehiculo": datos_vehiculo,
            "adeudo": monto_adeudo,
            "estado": "Veracruz"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en procesamiento final: {str(e)}")
