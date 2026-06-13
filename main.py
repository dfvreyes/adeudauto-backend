from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import base64
import urllib.parse

app = FastAPI()

# Permitir conexiones desde tu frontend en Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 COLOCA AQUÍ TU API KEY REAL DE SCRAPINGBEE
SCRAPINGBEE_API_KEY = "YXCMEMCHIH28ATRP4YVX4RK3J0P9DR3EYAR622BAH9JATN16PLPPP84LDZ6V487NK6JKOR9S0F14WARV"

# Diccionario centralizado para mantener las cookies de sesión vivas
sesiones_globales = {}

class ConsultaEstadoRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

@app.get("/")
async def root():
    return {"status": "ok", "message": "Servidor Central de Adeudos Activo con ScrapingBee"}


# --- SECCIÓN: VERACRUZ (OVH) ---

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    """ 
    Usa ScrapingBee con IP de México para abrir la sesión en la OVH 
    y descargar el jcaptcha real con sus cookies correspondientes.
    """
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar la API Key de ScrapingBee en el backend.")

    # 1. Creamos una sesión normal de requests para retener las cookies que nos asigne el gobierno
    session = requests.Session()
    
    # 2. Preparamos las URLs oficiales de Veracruz
    url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    
    # 3. Configuramos los parámetros para que ScrapingBee use una IP residencial de México
    # Usamos la URL de renderizado de ScrapingBee
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        # PASO A: Tocar la página inicial a través de ScrapingBee para pescar la Cookie de Sesión (JSESSIONID)
        params_inicio = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_principal,
            "country_code": "mx", # <--- Forzamos IP de México residencial
            "forward_headers": "true"
        }
        res_inicio = requests.get(spb_endpoint, params=params_inicio, timeout=30)
        
        if res_inicio.status_code != 200:
            raise HTTPException(status_code=500, detail=f"ScrapingBee no pudo acceder a la OVH. Status: {res_inicio.status_code}")
            
        # Guardamos las cookies que Veracruz le regresó a ScrapingBee y ScrapingBee nos mandó a nosotros
        session.cookies.update(res_inicio.cookies)
        
        # PASO B: Descargar el captcha usando exactamente la misma sesión de cookies
        # Para que Veracruz sepa qué cookies queremos usar, se las mandamos en los headers a ScrapingBee
        cookie_string = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])
        
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        headers_captcha = {
            "Cookie": cookie_string,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_captcha, timeout=30)
        
        if res_captcha.status_code != 200:
            raise HTTPException(status_code=500, detail="Error al descargar el captcha real a través del túnel residencial.")
            
        # Convertimos la imagen recibida a Base64 para mandarla directo al diseño oscuro de Lovable
        captcha_base64 = base64.b64encode(res_captcha.content).decode('utf-8')
        
        # Vinculamos la sesión de cookies a un ID único para usarlo en el paso de consulta
        session_id = str(id(session))
        sesiones_globales[session_id] = session
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falla en el puente residencial de Veracruz: {str(e)}")


@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    """
    Recupera la sesión con la cookie viva y envía el formulario por ScrapingBee
    usando los nombres de campos nativos (pPlaca y pTextoSeguridad).
    """
    session = sesiones_globales.get(req.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="La sesión expiró o es inválida. Recarga el captcha.")
        
    url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        # Cuerpo exacto que requiere el servidor de Veracruz
        payload = {
            "pPlaca": req.placa.upper().strip(),
            "pTextoSeguridad": req.captcha_texto.strip()
        }
        
        # Formateamos el payload como x-www-form-urlencoded para enviarlo dentro de la URL de ScrapingBee
        payload_encoded = urllib.parse.urlencode(payload)
        
        cookie_string = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])
        
        # Configuramos ScrapingBee para que haga un POST enviando el payload codificado
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
        
        # Hacemos la petición POST a ScrapingBee, pasando el cuerpo en data
        response = requests.post(spb_endpoint, params=params_post, headers=headers_post, data=payload_encoded, timeout=40)
        
        # Analizamos el HTML real que nos devolvió el gobierno de Veracruz
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El código de seguridad (Captcha) es incorrecto o ya venció.")
            
        datos_vehiculo = "Vehículo no identificado o sin adeudos vigentes en Veracruz"
        monto_adeudo = "$0.00"
        
        # Raspado analítico de las celdas y filas de la OVH
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) >= 2:
                texto_unido = " ".join(celdas)
                if "Vehículo" in texto_unido or "Modelo" in texto_unido:
                    datos_vehiculo = celdas[1]
                if "Total" in texto_unido or "Pagar" in texto_unido or "Adeudo" in texto_unido:
                    monto_adeudo = celdas[1]

        # Respaldo por si la estructura cambia a texto plano libre
        if datos_vehiculo == "Vehículo no identificado o sin adeudos vigentes en Veracruz":
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
        raise HTTPException(status_code=500, detail=f"Error al procesar la respuesta del estado: {str(e)}")
    finally:
        # Limpieza de memoria
        if req.session_id in sesiones_globales:
            del sesiones_globales[req.session_id]
