from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import json, time, random, urllib.parse

app = FastAPI()

# 🔑 TU API KEY DE SCRAPINGBEE ACTIVA
SCRAPINGBEE_API_KEY = "YXCMEMCHIH28ATRP4YVX4RK3J0P9DR3EYAR622BAH9JATN16PLPPP84LDZ6V487NK6JKOR9S0F14WARV"
SPB = "https://app.scrapingbee.com/api/v1/"
URL_OVH = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"

sesiones_globales = {}  # session_id local -> {"spb_session": int, "cookies": str}

class ConsultaEstadoRequest(BaseModel):
    session_id: str | None = None
    sessionId: str | None = None
    placa: str
    captcha_texto: str | None = None
    captchaTexto: str | None = None

@app.middleware("http")
async def cors(request: Request, call_next):
    if request.method == "OPTIONS":
        r = Response(status_code=204)
    else:
        try:
            r = await call_next(request)
        except Exception as e:
            r = JSONResponse(status_code=500, content={"detail": f"Falla interna: {e}"})
    origin = request.headers.get("origin", "*")
    r.headers["Access-Control-Allow-Origin"] = origin
    r.headers["Access-Control-Allow-Credentials"] = "true"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept"
    return r

@app.get("/")
async def root():
    return {"status": "ok"}

def _extract_spb_cookies(headers) -> str:
    """ScrapingBee devuelve las cookies del sitio destino en Spb-Cookies o spb-cookies."""
    return headers.get("Spb-Cookies") or headers.get("spb-cookies") or ""

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    # Creamos un ID de sesión numérico para que ScrapingBee fije la IP residencial fija
    spb_session = random.randint(100000, 999999)

    # El plan maestro de Lovable: Inyectar código JS para extraer la imagen sin recargar
    js_scenario = {
        "instructions": [
            {"wait_for": "img[src*='jcaptcha']"},
            {"wait": 2000}, # Le damos 2 segundos enteros para que Radware termine de validar y pinte las letras
            {
                "evaluate": (
                    "(() => {"
                    "  var img = document.querySelector(\"img[src*='jcaptcha']\");"
                    "  if (!img) return 'ERR_NO_IMG';"
                    "  var c = document.createElement('canvas');"
                    "  c.width = img.naturalWidth || img.width || 200;"
                    "  c.height = img.naturalHeight || img.height || 50;"
                    "  var ctx = c.getContext('2d');"
                    "  ctx.drawImage(img, 0, 0);"
                    "  return c.toDataURL('image/png');"
                    "})()"
                )
            },
        ]
    }

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_OVH,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true",
        "stealth_proxy": "true",    # Bloqueador anti-Radware activado
        "session_id": spb_session,  # Garantiza usar la misma IP para el POST posterior
        "js_scenario": json.dumps(js_scenario),
        "json_response": "true"     # 🔥 OBLIGATORIO: Fuerza a ScrapingBee a regresar un JSON con el resultado del evaluate
    }

    try:
        res = requests.get(SPB, params=params, timeout=120)
    except requests.Timeout:
        raise HTTPException(502, "ScrapingBee timeout cargando OVH. Reintenta.")

    if res.status_code >= 400:
        raise HTTPException(502, f"ScrapingBee error {res.status_code}: {res.text[:200]}")

    # 🕵️‍♂️ Extracción corregida del JSON de respuesta de ScrapingBee
    try:
        response_data = res.json()
        # ScrapingBee guarda las respuestas de JavaScript dentro de esta estructura:
        captcha_b64 = response_data.get("js_scenario", {}).get("evaluate_result") or response_data.get("js_scenario", {}).get("result")
    except Exception:
        raise HTTPException(502, "No se pudo interpretar el formato de respuesta del proxy.")

    if not captcha_b64 or "data:image" not in str(captcha_b64):
        raise HTTPException(502, f"Radware bloqueó el Canvas o la imagen no cargó. Respuesta interna: {str(captcha_b64)[:200]}")

    spb_cookies = _extract_spb_cookies(res.headers)
    session_id = str(int(time.time() * 1000))
    sesiones_globales[session_id] = {"spb_session": spb_session, "cookies": spb_cookies}

    return {
        "session_id": session_id, 
        "sessionId": session_id,
        "captcha_image": captcha_b64, 
        "captchaImage": captcha_b64,
    }

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    sid = req.session_id or req.sessionId
    captcha = (req.captcha_texto or req.captchaTexto or "").strip()
    sess = sesiones_globales.get(sid)
    if not sess:
        raise HTTPException(400, "Sesión expirada o inválida. Recarga el captcha.")

    placa = req.placa.upper().strip()

    # Rellenamos el formulario simulando escritura humana y damos clic en enviar
    js_scenario = {
        "instructions": [
            {"wait_for": "input[name='pPlaca']"},
            {"evaluate": (
                f"document.querySelector(\"input[name='pPlaca']\").value = '{placa}';"
                f"document.querySelector(\"input[name='pTextoSeguridad']\").value = '{captcha}';"
                "''"
            )},
            {"click": "input[type='submit'], button[type='submit']"},
            {"wait": 4000}, # Le damos 4 segundos a la página gubernamental para procesar los datos
        ]
    }

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_OVH,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true",
        "stealth_proxy": "true",
        "session_id": sess["spb_session"],   # Conexión exacta a la misma IP del Captcha
        "js_scenario": json.dumps(js_scenario),
        "return_page_source": "true",
    }
    
    headers_req = {}
    if sess["cookies"]:
        headers_req["Spb-Cookies"] = sess["cookies"]

    try:
        res = requests.get(SPB, params=params, headers=headers_req, timeout=120)
    except requests.Timeout:
        raise HTTPException(502, "ScrapingBee timeout en consulta.")

    if res.status_code >= 400:
        raise HTTPException(502, f"ScrapingBee error {res.status_code}: {res.text[:200]}")

    html = res.text
    if "Texto de seguridad incorrecto" in html or "incorrecto" in html.lower():
        raise HTTPException(400, "El código de seguridad (Captcha) es incorrecto.")

    soup = BeautifulSoup(html, "html.parser")
    vehiculo = "Vehículo sin adeudos o no registrado en Veracruz"
    adeudo = "$0.00"
    
    for row in soup.find_all("tr"):
        celdas = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(celdas) >= 2:
            t = " ".join(celdas)
            if "Vehículo" in t or "Modelo" in t or "Marca" in t:
                vehiculo = celdas[1] or vehiculo
            if "Total" in t or "Pagar" in t or "Adeudo" in t:
                adeudo = celdas[1] or adeudo

    return {"placa": placa, "vehiculo": vehiculo, "adeudo": adeudo, "estado": "Veracruz"}
