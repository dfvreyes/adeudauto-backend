from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import json, time, random, urllib.parse

app = FastAPI()

# 🔑 TU NUEVA API KEY DE SCRAPINGBEE DE RESPALDO
SCRAPINGBEE_API_KEY = "LMYGEFZL35211YDJEFNK30DSG9CYRSMRYZ5JQUQTXW10WC3QO6GXJ7DPLNPEBF1EHWPIQ4FOCOFUA8IG"
SPB = "https://app.scrapingbee.com/api/v1/"
URL_OVH = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"

sesiones_globales = {}  # session_id local -> {"spb_session": int}

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
    return {"status": "ok", "message": "Servidor Central - Operacion Veracruz Activa"}

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    # Identificador único numérico para congelar el nodo de IP en ScrapingBee
    spb_session = random.randint(100000, 999999)

    # 🕵️‍♂️ Promesa asíncrona avanzada en JS: Monitorea la presencia y carga real de los píxeles del captcha
    js_extractor = """
    new Promise((resolve) => {
        var startTime = Date.now();
        function checkImage() {
            var img = document.querySelector("img[src*='jcaptcha']");
            // Validamos que el elemento exista, esté completo y tenga dimensiones reales en pantalla
            if (img && img.complete && img.naturalWidth > 0) {
                var canvas = document.createElement("canvas");
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                var ctx = canvas.getContext("2d");
                ctx.drawImage(img, 0, 0);
                resolve(canvas.toDataURL("image/png"));
            } else if (Date.now() - startTime > 15000) {
                // Si pasan 15 segundos y Radware congeló el render gráfico, salimos con error
                resolve("ERROR_TIMEOUT_RADWARE");
            } else {
                // Reintentar cíclicamente cada 400 milisegundos
                setTimeout(checkImage, 400);
            }
        }
        checkImage();
    });
    """

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_OVH,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true",
        "stealth_proxy": "true",       # Forzar algoritmos de camuflaje anti-Radware
        "session_id": spb_session,     # Fija la IP residencial para el POST de la consulta
        "evaluate": js_extractor       # ScrapingBee ejecutará la promesa y nos devolverá el texto puro
    }

    try:
        # Timeout preventivo extendido para darle tiempo a la promesa de ejecutarse sin prisa
        res = requests.get(SPB, params=params, timeout=65)
    except requests.Timeout:
        raise HTTPException(502, "Tiempo de espera agotado con el proxy residencial premium.")

    if res.status_code >= 400:
        raise HTTPException(502, f"Error de infraestructura residencial ({res.status_code}): {res.text[:150]}")

    captcha_b64 = res.text.strip()

    # Si Radware ganó esta ronda y congeló la carga del elemento gráfico
    if "ERROR" in captcha_b64 or "data:image" not in captcha_b64:
        raise HTTPException(502, "El escudo Radware interceptó la carga gráfica. Presiona recargar para rotar el nodo.")

    session_id = str(int(time.time() * 1000))
    sesiones_globales[session_id] = {"spb_session": spb_session}

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
        raise HTTPException(400, "La sesión de consulta expiró o es inválida. Recarga el captcha.")

    placa = req.placa.upper().strip()

    # Escenario de inyección para rellenar campos y dar clic usando la misma máquina física
    js_scenario = {
        "instructions": [
            {"wait_for": "input[name='pPlaca']"},
            {"evaluate": (
                f"document.querySelector(\"input[name='pPlaca']\").value = '{placa}';"
                f"document.querySelector(\"input[name='pTextoSeguridad']\").value = '{captcha}';"
                "''"
            )},
            {"click": "input[type='submit'], button[type='submit']"},
            {"wait": 5000}, # Le damos 5 segundos enteros a SEFIPLAN para procesar y pintar la tabla
        ]
    }

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_OVH,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true",
        "stealth_proxy": "true",
        "session_id": sess["spb_session"], # Clave absoluta: Usamos la misma IP exacta que generó el captcha
        "js_scenario": json.dumps(js_scenario),
        "return_page_source": "true",
    }

    try:
        res = requests.get(SPB, params=params, timeout=65)
    except requests.Timeout:
        raise HTTPException(502, "Exceso de tiempo esperando respuesta del portal estatal.")

    if res.status_code >= 400:
        raise HTTPException(502, f"Falla en comunicación de consulta: {res.text[:150]}")

    html = res.text
    if "Texto de seguridad incorrecto" in html or "incorrecto" in html.lower():
        raise HTTPException(400, "El código de seguridad (Captcha) es incorrecto.")

    soup = BeautifulSoup(html, "html.parser")
    vehiculo = "Vehículo identificado sin adeudos vigentes en Veracruz"
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
