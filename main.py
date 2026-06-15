from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import base64
import urllib.parse
import time

app = FastAPI()

# 🔑 COLOCA AQUÍ TU API KEY REAL DE SCRAPINGBEE
SCRAPINGBEE_API_KEY = "TU_API_KEY_AQUI"

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
    return {"status": "ok", "message": "Servidor Centralizado - Modo Camuflaje Activo"}

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta la API Key de ScrapingBee.")

    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    # 🕵️‍♂️ ESTRATEGIA DE CAMUFLAJE: 
    # Desactivamos render_js para que Radware no detecte las funciones de automatización,
    # y en su lugar inyectamos encabezados de comportamiento humano ultra-comunes.
    try:
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        headers_stealth = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive"
        }
        
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_stealth, timeout=30)
        
        # Si ScrapingBee se topa con Radware, nos daremos cuenta por el tipo de contenido
        content_type = res_captcha.headers.get("Content-Type", "").lower()
        if "html" in content_type or b"Radware" in res_captcha.content or b"<!DOCTYPE" in res_captcha.content[:50]:
            raise HTTPException(status_code=502, detail="Radware bloqueó el acceso residencial. Por favor intenta de nuevo.")

        # Si el contenido es una imagen real, extraemos las cookies que Veracruz le asignó a ScrapingBee
        cookies_dict = {}
        if res_captcha.cookies:
            for cookie in res_captcha.cookies:
                cookies_dict[cookie.name] = cookie.value
                
        # Estructuramos el formato Base64 limpio
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
        raise HTTPException(status_code=500, detail=f"Falla en el camuflaje del túnel: {str(e)}")

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
            "forward_headers": "true"
        }
        
        headers_post = {
            "Cookie": cookie_string,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://ovh.veracruz.gob.mx",
            "Referer": "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        }
        
        response = requests.post(spb_endpoint, params=params_post, headers=headers_post, data=payload_encoded, timeout=40)
        
        # Validar si el post fue bloqueado por Radware
        if b"Radware" in response.content:
            raise HTTPException(status_code=502, detail="El escudo bloqueó el envío de la consulta. Reintenta.")
            
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
        raise HTTPException(status_code=500, detail=f"Error en consulta: {str(e)}")
    finally:
        if id_sesion in sesiones_globales:
            del sesiones_globales[id_sesion]
