from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import base64
import urllib.parse

app = FastAPI()

# 🔑 COLOCA AQUÍ TU API KEY REAL DE SCRAPINGBEE
SCRAPINGBEE_API_KEY = "TU_API_KEY_AQUI"

# Memoria global para almacenar las cookies de sesión como texto plano
sesiones_globales = {}

class ConsultaEstadoRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

def extraer_cookies_seguras(response):
    """ Extrae cookies de forma segura para evitar fallas de tipo NoneType """
    cookies_dict = {}
    if hasattr(response, 'cookies') and response.cookies:
        for cookie in response.cookies:
            cookies_dict[cookie.name] = cookie.value
    for header_name, header_value in response.headers.items():
        if header_name.lower() == 'set-cookie':
            partes = header_value.split(';')
            if partes:
                par_cookie = partes[0].split('=', 1)
                if len(par_cookie) == 2:
                    cookies_dict[par_cookie[0].strip()] = par_cookie[1].strip()
    return cookies_dict

# 🛡️ MIDDLEWARE DE CONTROL TOTAL DE CORS (Solución al error del navegador)
@app.middleware("http")
async def cors_interceptor_universal(request: Request, call_next):
    # 1. Responder de inmediato a las peticiones de preflight (OPTIONS) sin tocar ScrapingBee
    if request.method == "OPTIONS":
        response = Response(status_code=204)
        origin = request.headers.get("origin", "*")
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
        return response

    # 2. Procesar la petición real atrapando cualquier posible crash interno
    try:
        response = await call_next(request)
    except Exception as e:
        response = JSONResponse(
            status_code=500,
            content={"status": "error", "detail": f"Falla interna del servidor: {str(e)}"}
        )

    # 3. Inyectar dinámicamente el origen espejo para cumplir las reglas de Lovable
    origin = request.headers.get("origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
    
    return response


@app.get("/")
async def root():
    return {"status": "ok", "message": "Servidor Centralizado Desbloqueado"}


# --- LÓGICA DE EXTRACCIÓN: VERACRUZ ---

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar la API Key de ScrapingBee.")

    url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        # Paso A: Inicializar cookies gubernamentales
        params_inicio = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_principal,
            "country_code": "mx",
            "forward_headers": "true"
        }
        res_inicio = requests.get(spb_endpoint, params=params_inicio, timeout=30)
        
        if res_inicio.status_code in [403, 429]:
            raise HTTPException(status_code=429, detail="Límite de concurrencia en ScrapingBee. Reintenta.")
            
        cookies_recolectadas = extraer_cookies_seguras(res_inicio)
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_recolectadas.items()])

        # Paso B: Descargar la imagen del captcha con la cookie activa
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "forward_headers": "true"
        }
        headers_captcha = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Cookie": cookie_string
        }
        
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_captcha, timeout=30)
        
        if res_captcha.status_code != 200:
            raise HTTPException(status_code=500, detail="La dependencia residencial rechazó la descarga de la imagen.")
            
        cookies_actualizadas = extraer_cookies_seguras(res_captcha)
        cookies_recolectadas.update(cookies_actualizadas)
        
        captcha_base64 = base64.b64encode(res_captcha.content).decode('utf-8')
        session_id = str(id(cookies_recolectadas))
        sesiones_globales[session_id] = cookies_recolectadas
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falla en el puente de transmisión: {str(e)}")


@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    cookies = sesiones_globales.get(req.session_id)
    if not cookies:
        raise HTTPException(status_code=400, detail="Sesión inválida o expirada. Recarga el captcha.")
        
    url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        payload = {
            "pPlaca": req.placa.upper().strip(),
            "pTextoSeguridad": req.captcha_texto.strip()
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        response = requests.post(spb_endpoint, params=params_post, headers=headers_post, data=payload_encoded, timeout=40)
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El código de seguridad introducido es incorrecto.")
            
        datos_vehiculo = "Vehículo sin adeudos vigentes o no registrado en Veracruz"
        monto_adeudo = "$0.00"
        
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) >= 2:
                texto_unido = " ".join(celdas)
                if "Vehículo" in texto_unido or "Modelo" in texto_unido:
                    datos_vehiculo = celdas[1]
                if "Total" in texto_unido or "Pagar" in texto_unido or "Adeudo" in texto_unido:
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
        raise HTTPException(status_code=500, detail=f"Error en procesamiento de datos de SEFIPLAN: {str(e)}")
    finally:
        if req.session_id in sesiones_globales:
            del sesiones_globales[req.session_id]
