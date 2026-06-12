from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cloudscraper
from bs4 import BeautifulSoup
import base64
import random

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

def obtener_proxies_mexico():
    """ Obtiene una lista de proxies públicos de México para burlar el baneo de IP """
    try:
        # Consultamos una API pública de proxies gratuitos
        res = cloudscraper.create_scraper().get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=MX&ssl=all&anonymity=all", timeout=5)
        if res.status_code == 200 and res.text:
            proxies = [p.strip() for p in res.text.split("\n") if p.strip()]
            return proxies
    except:
        pass
    # Lista de respaldo por si la API externa falla en ese segundo
    return []

@app.get("/")
async def root():
    return {"status": "ok", "message": "Motor Real Veracruz Sin Bloqueos"}

@app.get("/api/veracruz/captcha")
async def obtener_captcha_veracruz():
    # Creamos un scraper avanzado que imita comportamiento humano y salta Cloudflare/Firewalls
    scraper = cloudscraper.create_scraper()
    
    # Intentamos conseguir proxies de México para enmascarar a Render
    lista_proxies = obtener_proxies_mexico()
    if lista_proxies:
        proxy_elegido = random.choice(lista_proxies)
        scraper.proxies = {"http": f"http://{proxy_elegido}", "https": f"http://{proxy_elegido}"}
    
    try:
        # 1. Petición inicial para activar las cookies del gobierno
        url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        res_inicio = scraper.get(url_principal, timeout=12)
        
        # 2. Descargar el captcha real de la sesión
        url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
        captcha_res = scraper.get(url_captcha, timeout=12)
        
        if captcha_res.status_code != 200:
            raise HTTPException(status_code=500, detail="El portal de Veracruz rechazó la conexión. Intenta recargar.")
            
        captcha_base64 = base64.b64encode(captcha_res.content).decode('utf-8')
        
        # Guardamos el objeto scraper completo en memoria para heredar las cookies en el POST
        session_id = str(id(scraper))
        sesiones_cookies[session_id] = scraper
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Saturación en el portal del gobierno. Reintenta en 5 segundos.")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaVeracruzRequest):
    scraper = sesiones_cookies.get(req.session_id)
    if not scraper:
        raise HTTPException(status_code=400, detail="La sesión expiró. Recarga el captcha.")
        
    try:
        # Campos analizados reales del formulario del estado de Veracruz
        payload = {
            "pPlaca": req.placa.upper().strip(),
            "pTextoSeguridad": req.captcha_texto.strip()
        }
        
        url_post = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
        response = scraper.post(url_post, data=payload, timeout=15)
        
        soup = BeautifulSoup(response.text, "html.parser")
        texto_completo = soup.get_text()
        
        if "Texto de seguridad incorrecto" in texto_completo:
            raise HTTPException(status_code=400, detail="El código de seguridad es incorrecto.")
            
        datos_vehiculo = "No identificado o sin registro en Veracruz"
        monto_adeudo = "$0.00"
        
        # Raspado exacto de las celdas de SEFIPLAN
        for row in soup.find_all("tr"):
            celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(celdas) >= 2:
                texto_unido = " ".join(celdas)
                if "Vehículo" in texto_unido or "Modelo" in texto_unido:
                    datos_vehiculo = celdas[1]
                if "Total" in texto_unido or "Pagar" in texto_unido or "Adeudo" in texto_unido:
                    monto_adeudo = celdas[1]

        if datos_vehiculo == "No identificado o sin registro en Veracruz":
            for linea in texto_completo.split("\n"):
                if "Vehículo" in linea:
                    datos_vehiculo = linea.replace("Vehículo:", "").strip()
                if "Total a Pagar" in linea:
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
        raise HTTPException(status_code=500, detail="Error de procesamiento de datos con el estado.")
    finally:
        if req.session_id in sesiones_cookies:
            del sesiones_cookies[req.session_id]
