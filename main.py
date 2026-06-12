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

sesiones_activas = {}

class ConsultaVeracruzRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

@app.get("/")
async def root():
    return {"status": "ok", "message": "API de Veracruz Activa (Modo Inteligente)"}

@app.get("/api/veracruz/captcha")
async def obtener_captcha_veracruz():
    """ Lee dinámicamente la página de Veracruz, encuentra el captcha real y lo descarga """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.8,en-US;q=0.5,en;q=0.3"
    }
    
    client = httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True)
    
    try:
        # 1. Entrar a la página principal de consulta
        url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        response = await client.get(url_principal)
        
        # 2. Parsear el HTML para buscar la etiqueta <img> del captcha real
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Buscamos cualquier imagen que apunte a 'captcha' o 'jcaptcha'
        img_tag = soup.find("img", src=lambda x: x and ("captcha" in x.lower() or "jcaptcha" in x.lower()))
        
        # Si no la encuentra por nombre, buscamos la imagen que está dentro del formulario vehicular
        if not img_tag:
            form = soup.find("form")
            if form:
                img_tag = form.find("img")
                
        if not img_tag or not img_tag.get("src"):
            await client.aclose()
            raise HTTPException(status_code=500, detail="El sitio de Veracruz cambió la estructura del formulario.")
            
        src_captcha = img_tag["src"]
        
        # Construir la URL absoluta del captcha
        if src_captcha.startswith("http"):
            url_captcha = src_captcha
        else:
            # Si es una ruta relativa (ej: /ovh/jcaptcha), la unimos a la base
            base_url = "https://ovh.veracruz.gob.mx"
            if not src_captcha.startswith("/"):
                src_captcha = "/" + src_captcha
            url_captcha = f"{base_url}{src_captcha}"
            
        # 3. Descargar la imagen usando la misma sesión de cookies
        captcha_response = await client.get(url_captcha)
        
        if captcha_response.status_code != 200:
            await client.aclose()
            raise HTTPException(status_code=500, detail="No se pudo descargar la imagen del captcha desde la OVH.")
            
        # Convertir a Base64
        captcha_base64 = base64.b64encode(captcha_response.content).decode('utf-8')
        
        session_id = str(id(client))
        sesiones_activas[session_id] = client
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=500, detail=f"Error al conectar con la OVH: {str(e)}")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaVeracruzRequest):
    """ Envía los datos simulando el formulario y extrae la tabla final """
    client = sesiones_activas.get(req.session_id)
    if not client:
        raise HTTPException(status_code=400, detail="Sesión inválida o vencida. Recarga el modal.")
        
    try:
        # Enviamos los parámetros exactos del formulario de SEFIPLAN
        payload = {
            "placa": req.placa.upper().strip(),
            "captcha": req.captcha_texto.strip(),
            "botonsubmit": "Consultar"
        }
        
        url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        response = await client.post(url_post, data=payload)
        
        soup = BeautifulSoup(response.text, "html.parser")
        texto_pagina = soup.get_text()
        
        if "incorrecto" in texto_pagina.lower() or "error" in texto_pagina.lower():
            raise HTTPException(status_code=400, detail="El texto de seguridad es incorrecto o expiró.")
            
        datos_vehiculo = "No identificado"
        monto_adeudo = "$0.00"
        
        # Raspado inteligente buscando filas de texto
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) >= 2:
                texto_unido = " ".join(celdas)
                if "Vehículo" in texto_unido or "Modelo" in texto_unido:
                    datos_vehiculo = celdas[1]
                if "Total" in texto_unido or "Adeudo" in texto_unido or "Pagar" in texto_unido:
                    monto_adeudo = celdas[1]
                    
        # Si no lo encuentra en tablas, buscamos por texto plano bruto
        if datos_vehiculo == "No identificado":
            for linea in texto_pagina.split("\n"):
                if "Vehículo:" in linea:
                    datos_vehiculo = linea.replace("Vehículo:", "").strip()
                if "Total a Pagar:" in linea:
                    monto_adeudo = linea.replace("Total a Pagar:", "").strip()

        return {
            "placa": req.placa.upper(),
            "vehiculo": datos_vehiculo,
            "adeudo": monto_adeudo,
            "estado": "Veracruz"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar los adeudos: {str(e)}")
    finally:
        await client.aclose()
        if req.session_id in sesiones_activas:
            del sesiones_activas[req.session_id]
