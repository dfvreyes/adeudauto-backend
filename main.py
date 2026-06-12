from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
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

# Guardamos las cookies de sesión para simular que somos el mismo usuario
sesiones_activas = {}

class ConsultaVeracruzRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

@app.get("/")
async def root():
    return {"status": "ok", "message": "API de Veracruz Activa (Modo Ligero)"}

@app.get("/api/veracruz/captcha")
async def obtener_captcha_veracruz():
    """ Descarga directamente el captcha y guarda las cookies de sesión """
    # Simulamos un navegador real de una computadora normal
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.8,en-US;q=0.5,en;q=0.3"
    }
    
    # Usamos un cliente HTTP que maneja las cookies automáticamente
    client = httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True)
    
    try:
        # 1. Entrar a la página principal para que nos asigne cookies de Veracruz
        url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        response = await client.get(url_principal)
        
        # 2. Descargar la imagen del captcha usando la misma sesión
        url_captcha = "https://ovh.veracruz.gob.mx/ovh/captcha"
        captcha_response = await client.get(url_captcha)
        
        if captcha_response.status_code != 200:
            await client.aclose()
            raise HTTPException(status_code=500, detail="El servidor de Veracruz rechazó la descarga del captcha.")
            
        # Convertir los bytes de la imagen a Base64 para enviarla a Lovable
        captcha_base64 = base64.b64encode(captcha_response.content).decode('utf-8')
        
        # Guardar el cliente activo en memoria para el siguiente paso
        session_id = str(id(client))
        sesiones_activas[session_id] = client
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=500, detail=f"No se pudo conectar con Veracruz (Cerró conexión): {str(e)}")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaVeracruzRequest):
    """ Envía los datos imitando el formulario oficial y extrae los adeudos """
    client = sesiones_activas.get(req.session_id)
    if not client:
        raise HTTPException(status_code=400, detail="La sesión expiró o es inválida. Recarga el captcha.")
        
    try:
        # Estructura de los datos que espera el formulario de Veracruz al hacer POST
        # Modificamos los nombres de los campos para coincidir con el formulario de SEFIPLAN
        payload = {
            "placa": req.placa.upper(),
            "captcha": req.captcha_texto,
            "botonsubmit": "Consultar"
        }
        
        url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        response = await client.post(url_post, data=payload)
        
        # Procesar el HTML de respuesta
        soup = BeautifulSoup(response.text, "html.parser")
        texto_pagina = soup.get_text()
        
        # Si el captcha falló, la página suele decírnoslo en el texto
        if "Texto de seguridad incorrecto" in texto_pagina or "error" in texto_pagina.lower():
            raise HTTPException(status_code=400, detail="El texto de seguridad no coincide. Inténtalo de nuevo.")
            
        # Extraer los datos buscando las etiquetas o textos clave
        datos_vehiculo = "No especificado (Veracruz)"
        monto_adeudo = "$0.00"
        
        # Buscamos tablas o textos dentro del HTML que contengan los datos que viste en tu captura
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) >= 2:
                texto_unido = " ".join(celdas)
                if "Vehículo" in texto_unido:
                    datos_vehiculo = celdas[1]
                if "Total a Pagar" in texto_unido or "Adeudo" in texto_unido:
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
        raise HTTPException(status_code=500, detail=f"Error al leer la respuesta de Veracruz: {str(e)}")
    finally:
        # Cerrar el cliente para liberar memoria
        await client.aclose()
        if req.session_id in sesiones_activas:
            del sesiones_activas[req.session_id]
