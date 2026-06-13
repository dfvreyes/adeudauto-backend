from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import base64
import urllib.parse

app = FastAPI()

# Permitir conexiones desde tu frontend en Lovable
# Permitir conexiones desde tu frontend en Lovable
from fastapi import FastAPI, HTTPException, Request, Response
# ... conserva tus otros imports arriba (base64, requests, etc.) ...

app = FastAPI()

# 🛡️ MOTOR INDESTRUCTIBLE CONTRA CORS (Reemplaza el bloque viejo con esto)
@app.middleware("http")
async def interceptor_cors_seguro(request: Request, call_next):
    # Si el navegador envía una petición de reconocimiento (OPTIONS), le respondemos con éxito inmediato
    if request.method == "OPTIONS":
        response = Response()
    else:
        response = await call_next(request)
    
    # Leemos la URL exacta desde donde Lovable está llamando
    origen_solicitante = request.headers.get("origin", "*")
    
    # Inyectamos los encabezados espejo que desarman cualquier bloqueo del navegador
    response.headers["Access-Control-Allow-Origin"] = origen_solicitante
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
    
    return response

# 🔑 COLOCA AQUÍ TU API KEY REAL DE SCRAPINGBEE
SCRAPINGBEE_API_KEY = "YXCMEMCHIH28ATRP4YVX4RK3J0P9DR3EYAR622BAH9JATN16PLPPP84LDZ6V487NK6JKOR9S0F14WARV"

# Memoria centralizada ultra-segura (Guardamos diccionarios de texto, no objetos mutables)
sesiones_globales = {}

class ConsultaEstadoRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

def extraer_cookies_seguras(response):
    """ Extrae cookies de forma 100% segura sin importar cómo las envíe ScrapingBee """
    cookies_dict = {}
    
    # 1. Intentar extraer del frasco de cookies estándar de requests
    if hasattr(response, 'cookies') and response.cookies:
        for cookie in response.cookies:
            cookies_dict[cookie.name] = cookie.value
            
    # 2. Intentar extraer manualmente de los encabezados (Set-Cookie) por si vienen ocultas
    for header_name, header_value in response.headers.items():
        if header_name.lower() == 'set-cookie':
            partes = header_value.split(';')
            if partes:
                par_cookie = partes[0].split('=', 1)
                if len(par_cookie) == 2:
                    cookies_dict[par_cookie[0].strip()] = par_cookie[1].strip()
                    
    return cookies_dict

@app.get("/")
async def root():
    return {"status": "ok", "message": "Servidor Central de Adeudos Activo y Optimizado"}


# --- SECCIÓN: VERACRUZ ---

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar la API Key de ScrapingBee.")

    url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        # PASO A: Visita inicial obligatoria para despertar el JSESSIONID del gobierno mexicano
        params_inicio = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_principal,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        res_inicio = requests.get(spb_endpoint, params=params_inicio, timeout=30)
        
        if res_inicio.status_code in [403, 429]:
            raise HTTPException(status_code=429, detail="ScrapingBee está procesando otra petición. Espera 5 segundos.")
            
        if res_inicio.status_code != 200:
            raise HTTPException(status_code=500, detail="El portal de Veracruz no respondió a la sesión inicial.")

        # Extraemos las cookies del paso A de forma segura
        cookies_recolectadas = extraer_cookies_seguras(res_inicio)
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_recolectadas.items()])

        # PASO B: Descargar la imagen del captcha inyectando la cookie del paso anterior
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        headers_captcha = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if cookie_string:
            headers_captcha["Cookie"] = cookie_string
            
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_captcha, timeout=30)
        
        if res_captcha.status_code != 200:
            raise HTTPException(status_code=500, detail="No se pudo descargar la imagen del captcha a través del túnel.")
            
        # Actualizamos las cookies por si el captcha generó una nueva secuencia
        cookies_actualizadas = extraer_cookies_seguras(res_captcha)
        cookies_recolectadas.update(cookies_actualizadas)
        
        # Convertimos la imagen limpia a Base64 para Lovable
        captcha_base64 = base64.b64encode(res_captcha.content).decode('utf-8')
        
        # Guardamos el diccionario de cookies plano usando un ID único de sesión
        session_id = str(id(cookies_recolectadas))
        sesiones_globales[session_id] = cookies_recolectadas
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falla en el puente de comunicación: {str(e)}")


@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    # Recuperamos el diccionario de cookies plano de la memoria
    cookies = sesiones_globales.get(req.session_id)
    if not cookies:
        raise HTTPException(status_code=400, detail="La sesión expiró. Recarga el captcha de nuevo.")
        
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.post(spb_endpoint, params=params_post, headers=headers_post, data=payload_encoded, timeout=40)
        
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El código de seguridad (Captcha) es incorrecto.")
            
        datos_vehiculo = "Vehículo no identificado o sin adeudos en Veracruz"
        monto_adeudo = "$0.00"
        
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) >= 2:
                texto_unido = " ".join(celdas)
                if "Vehículo" in texto_unido or "Modelo" in texto_unido:
                    datos_vehiculo = celdas[1]
                if "Total" in texto_unido or "Pagar" in texto_unido or "Adeudo" in texto_unido:
                    monto_adeudo = celdas[1]

        if datos_vehiculo == "Vehículo no identificado o sin adeudos en Veracruz":
            for linea in texto_completo.split("\n"):
                if "Vehículo" in linea or "Descripción" in linea:
                    datos_vehiculo = linea.strip()
                if "Total a Pagar" in linea:
                    monto_adeudo = linea.strip()

        return {
            "placa": req.placa.upper(),
            "vehiculo": datos_vehiculo,
            "adeudo": monto_adeudo,
            "estado": "Veracruz"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar la respuesta final: {str(e)}")
    finally:
        if req.session_id in sesiones_globales:
            del sesiones_globales[req.session_id]
