from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright
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

# Almacenamiento temporal de sesiones en memoria
sesiones_activas = {}

class ConsultaVeracruzRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

@app.get("/")
async def root():
    return {"status": "ok", "message": "API de Veracruz Activa"}

@app.get("/api/veracruz/captcha")
async def obtener_captcha_veracruz():
    """ Abre la OVH de Veracruz, toma captura al texto de seguridad y mantiene la sesión """
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        # Entrar a la URL oficial de consulta vehicular de Veracruz
        await page.goto("https://ovh.veracruz.gob.mx/ovh/consultavehicular")
        await page.wait_for_load_state("networkidle")
        
        # Localizar la imagen del captcha en el HTML de Veracruz
        # El sitio usa un elemento img que renderiza el texto distorsionado
        captcha_element = await page.query_selector("img[src*='captcha']") or await page.query_selector("td img")
        
        if not captcha_element:
            await browser.close()
            raise HTTPException(status_code=500, detail="No se pudo localizar el captcha de Veracruz.")
        
        # Tomar captura de pantalla solo al cuadro del captcha
        captcha_bytes = await captcha_element.screenshot()
        captcha_base64 = base64.b64encode(captcha_bytes).decode('utf-8')
        
        # Guardar la sesión viva
        session_id = str(hash(page))
        sesiones_activas[session_id] = {
            "browser": browser,
            "page": page,
            "playwright": playwright
        }
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except Exception as e:
        await browser.close()
        await playwright.stop()
        raise HTTPException(status_code=500, detail=f"Error en el servidor al abrir Veracruz: {str(e)}")

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaVeracruzRequest):
    """ Envía los datos ingresados por el usuario y raspa la tabla de resultados """
    sesion = sesiones_activas.get(req.session_id)
    if not sesion:
        raise HTTPException(status_code=400, detail="La sesión expiró. Recarga el captcha.")
    
    page = sesion["page"]
    browser = sesion["browser"]
    playwright = sesion["playwright"]
    
    try:
        # 1. Llenar los campos del formulario de Veracruz
        # Buscamos los inputs por su tipo o posición en el formulario
        await page.fill("input[type='text']", req.placa) # Primer input suele ser la placa
        
        # Llenar el campo del captcha (buscando el segundo input de texto)
        inputs_texto = await page.query_selector_all("input[type='text']")
        if len(inputs_texto) > 1:
            await inputs_texto[1].fill(req.captcha_texto)
        
        # 2. Dar clic en el botón "Consultar"
        await page.click("button:has-text('Consultar')") or await page.click("input[type='submit']")
        
        # 3. Esperar que cargue la página de resultados generales
        await page.wait_for_load_state("networkidle")
        
        # 4. Raspado de datos de la pantalla de resultados
        content = await page.content()
        
        # Si la página nos regresa al inicio o muestra error de captcha
        if "Texto de seguridad" in content and req.placa in content:
            raise HTTPException(status_code=400, detail="El captcha ingresado es incorrecto. Inténtalo de nuevo.")

        # Extraer los textos limpios de la pantalla de datos generales
        # Buscamos el texto del contenedor principal
        texto_completo = await page.locator("body").inner_text()
        
        # Lógica para extraer la descripción del vehículo y el adeudo de la pantalla
        # (Esto asume la estructura que vimos en tu captura de pantalla de SEFIPLAN)
        datos_vehiculo = "Vehículo no identificado"
        monto_adeudo = "$0.00"
        
        if "Vehículo:" in texto_completo:
            lineas = texto_completo.split("\n")
            for i, linea in enumerate(lineas):
                if "Vehículo:" in linea:
                    datos_vehiculo = linea.replace("Vehículo:", "").strip()
                if "Adeudo:" in linea:
                    monto_adeudo = linea.replace("Adeudo:", "").strip()

        return {
            "placa": req.placa,
            "vehiculo": datos_vehiculo,
            "adeudo": monto_adeudo,
            "estado": "Veracruz"
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al extraer los datos de Veracruz: {str(e)}")
    finally:
        # Limpieza obligatoria para liberar memoria en Render
        await browser.close()
        await playwright.stop()
        if req.session_id in sesiones_activas:
            del sesiones_activas[req.session_id]