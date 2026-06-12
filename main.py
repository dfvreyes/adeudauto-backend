from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import base64
import sys

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sesiones_cookies = {}

class ConsultaVeracruzRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

@app.get("/")
async def root():
    return {"status": "ok", "message": "API Veracruz con Rastreo Activo"}

@app.get("/api/veracruz/captcha")
async def obtener_captcha_veracruz():
    session = requests.Session()
    
    # Encabezados ultra realistas para simular un navegador Chrome de Windows
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    })
    
    try:
        # Paso 1: Obtener cookies abriendo la página principal
        url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        print(f"--> [DEBUG] Abriendo página principal: {url_principal}", flush=True)
        
        res_inicio = session.get(url_principal, timeout=20)
        print(f"--> [DEBUG] Respuesta inicio: Código {res_inicio.status_code}", flush=True)
        print(f"--> [DEBUG] Cookies obtenidas: {session.cookies.get_dict()}", flush=True)
        
        # Paso 2: Intentar descargar el jcaptcha usando la misma sesión
        url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
        print(f"--> [DEBUG] Solicitando captcha en: {url_captcha}", flush=True)
        
        captcha_res = session.get(url_captcha, timeout=20)
        print(f"--> [DEBUG] Respuesta captcha: Código {captcha_res.status_code}, Tipo Contenido: {captcha_res.headers.get('Content-Type')}", flush=True)
        
        # Si el servidor del gobierno nos da un error, imprimimos qué nos está diciendo
        if captcha_res.status_code != 200:
            print(f"--> [DEBUG] ERROR DEL GOBIERNO TEXTO: {captcha_res.text[:500]}", flush=True)
            raise HTTPException(
                status_code=500, 
                detail=f"Veracruz respondió con código de error {captcha_res.status_code} al pedir el captcha."
            )
            
        # Comprobamos si realmente lo que se descargó es una imagen
        if "image" not in captcha_res.headers.get('Content-Type', '').lower():
            print(f"--> [DEBUG] ALERTA: Lo descargado no es una imagen. Contenido bruto: {captcha_res.text[:300]}", flush=True)
            raise HTTPException(
                status_code=500, 
                detail="El portal de Veracruz no envió una imagen válida, envió texto o HTML de bloqueo."
            )
            
        # Convertir la imagen a Base64
        captcha_base64 = base64.b64encode(captcha_res.content).decode('utf-8')
        
        session_id = str(id(session))
        sesiones_cookies[session_id] = session
        print(f"--> [DEBUG] Sesión {session_id} guardada con éxito.", flush=True)
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        # Esto imprimirá el error exacto en tu consola de Render con detalles de la línea de falla
        print(f"--> [DEBUG] EXCEPCIÓN DETECTADA: {str(e)}", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=f"Fallo en el servidor intermedio: {str(e)}")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaVeracruzRequest):
    session = sesiones_cookies.get(req.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="La sesión expiró. Recarga el captcha.")
        
    try:
        payload = {
            "pPlaca": req.placa.upper().strip(),
            "pTextoSeguridad": req.captcha_texto.strip()
        }
        
        url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        response = session.post(url_post, data=payload, timeout=20)
        
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El código de seguridad es incorrecto.")
            
        datos_vehiculo = "No identificado o sin registro en Veracruz"
        monto_adeudo = "$0.00"
        
        for td in soup.find_all("td"):
            texto_td = td.get_text(strip=True)
            if "Vehículo:" in texto_td or "Vehiculo:" in texto_td:
                datos_vehiculo = texto_td.replace("Vehículo:", "").replace("Vehiculo:", "").strip()
                
        for span in soup.find_all(["span", "td", "th"]):
            texto_span = span.get_text(strip=True)
            if "Total a Pagar" in texto_span or "Total:" in texto_span:
                monto_adeudo = texto_span.split(":")[-1].strip()

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
        raise HTTPException(status_code=500, detail=f"Error al procesar la consulta final: {str(e)}")
    finally:
        if req.session_id in sesiones_cookies:
            del sesiones_cookies[req.session_id]
