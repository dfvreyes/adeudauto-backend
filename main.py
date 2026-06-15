from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import base64
import urllib.parse
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
    return {"status": "ok", "message": "Servidor Centralizado - Rompemuros Activo"}

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")

    url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        # 💣 ACTIVACIÓN DE RESOLVEDOR DE CAPTCHAS NATIVO
        # Este bloque obliga a ScrapingBee a romper el hCaptcha de Radware antes de entregarnos la página
        params_inicio = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_principal,
            "country_code": "mx",
            "render_js": "true",          # Abre navegador invisible real
            "premium_proxy": "true",       # Forzar IPs residenciales limpias
            "solve_captcha": "true",       # <--- LA LLAVE MAESTRA: Resuelve el hCaptcha de Radware en automático
            "forward_headers": "true"
        }
        
        # Le damos un timeout de 60 segundos porque resolver el hCaptcha toma tiempo de procesamiento
        res_inicio = requests.get(spb_endpoint, params=params_inicio, timeout=60)
        
        # Si a pesar de todo nos regresa el muro de hCaptcha de Radware, tiramos error controlado
        if b"Radware Captcha Page" in res_inicio.content or b"hcaptcha" in res_inicio.content:
            raise HTTPException(status_code=503, detail="ScrapingBee no logró resolver el hCaptcha de Radware a tiempo. Reintenta la ráfaga.")

        cookies_dict = {}
        if res_inicio.cookies:
            for cookie in res_inicio.cookies:
                cookies_dict[cookie.name] = cookie.value
                
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])

        # PASO B: Descargar la imagen real con el bypass de galletas activo
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "premium_proxy": "true",
            "forward_headers": "true"
        }
        
        headers_captcha = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": cookie_string
        }
        
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_captcha, timeout=30)
        
        if b"html" in res_captcha.content[:50] or b"<!DOCTYPE" in res_captcha.content[:50]:
            raise HTTPException(status_code=502, detail="Radware interceptó la descarga final. Presiona recargar.")

        captcha_base64 = base64.b64encode(res_captcha.content).decode('utf-8')
        session_id = str(int(time.time()))
        sesiones_globales[session_id] = cookies_dict
        
        return {
            "session_id": session_id,
            "sessionId": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}",
            "captchaImage": f"data:image/png;base64,{captcha_base64}"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en procesamiento de Rompemuros: {str(e)}")

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
            "render_js": "true",          # Forzamos render_js también al enviar para que ejecute el envío de forma humana
            "premium_proxy": "true",
            "forward_headers": "true"
        }
        
        headers_post = {
            "Cookie": cookie_string,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        response = requests.post(spb_endpoint, params=params_post, headers=headers_post, data=payload_encoded, timeout=50)
        
        if b"Radware" in response.content:
            raise HTTPException(status_code=502, detail="Radware bloqueó el envío final de datos.")
            
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El captcha es incorrecto.")
            
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
        raise HTTPException(status_code=500, detail=f"Error en consulta final: {str(e)}")
    finally:
        if id_sesion in sesiones_globales:
            del sesiones_globales[id_sesion]
