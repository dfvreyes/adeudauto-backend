from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import json, time, random, urllib.parse

app = FastAPI()

SCRAPINGBEE_API_KEY = "LMYGEFZL35211YDJEFNK30DSG9CYRSMRYZ5JQUQTXW10WC3QO6GXJ7DPLNPEBF1EHWPIQ4FOCOFUA8IG"
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

def _extract_evaluate_result(headers) -> str | None:
    """ScrapingBee devuelve el resultado del evaluate en Spb-Js-Scenario-Report (JSON)."""
    report = headers.get("Spb-Js-Scenario-Report") or headers.get("spb-js-scenario-report")
    if not report:
        return None
    try:
        data = json.loads(report)
        for task in data.get("tasks", []):
            if task.get("task") == "evaluate" and task.get("result"):
                return task["result"]
    except Exception:
        return None
    return None

def _extract_spb_cookies(headers) -> str:
    """ScrapingBee devuelve las cookies del sitio destino en Spb-Cookies."""
    return headers.get("Spb-Cookies") or headers.get("spb-cookies") or ""

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    spb_session = random.randint(100000, 999999)

    js_scenario = {
        "instructions": [
            {"wait_for": "img[src*='jcaptcha']"},
            {"wait": 1500},
            {"evaluate": (
                "(() => {"
                "  var img = document.querySelector(\"img[src*='jcaptcha']\");"
                "  if (!img) return 'ERR_NO_IMG';"
                "  var c = document.createElement('canvas');"
                "  c.width = img.naturalWidth || img.width || 200;"
                "  c.height = img.naturalHeight || img.height || 50;"
                "  c.getContext('2d').drawImage(img, 0, 0);"
                "  return c.toDataURL('image/png');"
                "})()"
            )},
        ]
    }

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_OVH,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true",
        "stealth_proxy": "true",   # extra anti-Radware
        "session_id": spb_session, # MISMA IP en la 2da llamada
        "js_scenario": json.dumps(js_scenario),
        "return_page_source": "true",
    }

    try:
        res = requests.get(SPB, params=params, timeout=120)
    except requests.Timeout:
        raise HTTPException(502, "ScrapingBee timeout cargando OVH. Reintenta.")

    if res.status_code >= 400:
        raise HTTPException(502, f"ScrapingBee {res.status_code}: {res.text[:200]}")

    captcha_b64 = _extract_evaluate_result(res.headers)
    if not captcha_b64 or "data:image" not in captcha_b64:
        raise HTTPException(502, f"No se obtuvo el captcha (evaluate vacío). Headers report: {res.headers.get('Spb-Js-Scenario-Report','')[:300]}")

    spb_cookies = _extract_spb_cookies(res.headers)
    session_id = str(int(time.time() * 1000))
    sesiones_globales[session_id] = {"spb_session": spb_session, "cookies": spb_cookies}

    return {
        "session_id": session_id, "sessionId": session_id,
        "captcha_image": captcha_b64, "captchaImage": captcha_b64,
    }

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    sid = req.session_id or req.sessionId
    captcha = (req.captcha_texto or req.captchaTexto or "").strip()
    sess = sesiones_globales.get(sid)
    if not sess:
        raise HTTPException(400, "Sesión expirada. Recarga el captcha.")

    placa = req.placa.upper().strip()

    # Llenamos los inputs y enviamos el form DENTRO del mismo navegador donde se generó el captcha.
    js_scenario = {
        "instructions": [
            {"wait_for": "input[name='pPlaca']"},
            {"evaluate": (
                f"document.querySelector(\"input[name='pPlaca']\").value = '{placa}';"
                f"document.querySelector(\"input[name='pTextoSeguridad']\").value = '{captcha}';"
                "''"
            )},
            {"click": "input[type='submit'], button[type='submit']"},
            {"wait": 3500},
        ]
    }

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": URL_OVH,
        "country_code": "mx",
        "render_js": "true",
        "premium_proxy": "true",
        "stealth_proxy": "true",
        "session_id": sess["spb_session"],   # MISMA IP/sesión que el GET
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
        raise HTTPException(502, f"ScrapingBee {res.status_code}: {res.text[:200]}")

    html = res.text
    if "Texto de seguridad incorrecto" in html or "captcha" in html.lower() and "incorrecto" in html.lower():
        raise HTTPException(400, "El código de seguridad es incorrecto.")

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
