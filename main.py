from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import base64

app = FastAPI()

# Permitir la conexión desde Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diccionario para guardar las sesiones de cookies activas
sesiones_cookies = {}

class ConsultaVeracruzRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

@app.get("/")
async def root():
    return {"status": "ok", "message": "API Veracruz - Formulario Analizado"}

@app.get("/api/veracruz/captcha")
async def obtener_captcha_veracruz():
    """ Abre la sesión oficial y extrae el jcaptcha exacto de la OVH """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        # 1. Petición inicial para activar las cookies del gobierno
        url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        session.get(url_principal, timeout=15)
        
        # 2. Descargar la imagen del captcha con la cookie activa
        url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
        captcha_res = session.get(url_captcha, timeout=15)
        
        if captcha_res.status_code != 200:
            raise HTTPException(status_code=500, detail="La OVH de Veracruz denegó la imagen del captcha.")
            
        # Convertir los bytes de la imagen a texto Base64
        captcha_base64 = base64.b64encode(captcha_res.content).decode('utf-8')
        
        # Guardar la sesión viva en memoria
        session_id = str(id(session))
        sesiones_cookies[session_id] = session
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fallo al mapear el Captcha de Veracruz: {str(e)}")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaVeracruzRequest):
    """ Envía los parámetros reales analizados del formulario de Veracruz """
    session = sesiones_cookies.get(req.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="La sesión expiró. Recarga el captcha de nuevo.")
        
    try:
        # PARÁMETROS REALES DEL FORMULARIO DE VERACRUZ: pPlaca y pTextoSeguridad
        payload = {
            "pPlaca": req.placa.upper().strip(),
            "pTextoSeguridad": req.captcha_texto.strip()
        }
        
        url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        response = session.post(url_post, data=payload, timeout=20)
        
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        # Validación de errores devueltos por la OVH
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El código de seguridad ingresado es incorrecto.")
            
        datos_vehiculo = "No identificado o sin registro en Veracruz"
        monto_adeudo = "$0.00"
        
        # Buscamos en el HTML las etiquetas específicas donde Veracruz plasma los resultados
        # Buscamos la tabla con la clase o textos clave que viste en tu consulta exitosa
        for td in soup.find_all("td"):
            texto_td = td.get_text(strip=True)
            if "Vehículo:" in texto_td or "Vehiculo:" in texto_td:
                datos_vehiculo = texto_td.replace("Vehículo:", "").replace("Vehiculo:", "").strip()
                
        # Extraer el monto total de la tabla de adeudos
        for span in soup.find_all(["span", "td", "th"]):
            texto_span = span.get_text(strip=True)
            if "Total a Pagar" in texto_span or "Total:" in texto_span:
                # Intentamos agarrar el elemento de al lado o el texto directo
                monto_adeudo = texto_span.split(":")[-1].strip()

        # Si el raspado por etiquetas falla, usamos la búsqueda por líneas brutas de respaldo
        if datos_vehiculo == "No identificado o sin registro en Veracruz":
            for linea in texto_completo.split("\n"):
                if "Vehículo" in linea or "Descripción" in linea:
                    datos_vehiculo = linea.strip()
                if "Total a Pagar" in linea or "Adeudo" in linea:
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
        raise HTTPException(status_code=500, detail=f"Error al extraer los datos finales: {str(e)}")
    finally:
        # Cerramos la sesión para no dejar procesos colgados en Render
        if req.session_id in sesiones_cookies:
            del sesiones_cookies[req.session_id]
