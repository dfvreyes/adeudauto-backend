@app.get("/api/veracruz/captcha")
async def obtener_captcha_veracruz():
    """ Abre la OVH de Veracruz con mejoras de tiempo y User-Agent """
    playwright = await async_playwright().start()
    # Añadimos argumentos para evitar bloqueos por venir de un servidor externo
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    )
    # Le ponemos un User-Agent de una computadora normal para que el gobierno no lo bloquee
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    
    try:
        # Aumentamos el tiempo de espera a 60 segundos (60000ms) en lugar de 30
        await page.goto("https://ovh.veracruz.gob.mx/ovh/consultavehicular", timeout=60000, wait_until="domcontentloaded")
        
        # Esperamos un par de segundos extras por si la página está lenta cargando imágenes
        await page.wait_for_timeout(2000)
        
        # Localizar la imagen del captcha buscando diferentes selectores posibles
        captcha_element = await page.query_selector("img[src*='captcha']") or \
                          await page.query_selector("img#imgCaptcha") or \
                          await page.query_selector("td img")
        
        if not captcha_element:
            await browser.close()
            raise HTTPException(status_code=500, detail="No se pudo localizar el captcha en el HTML de Veracruz.")
        
        # Tomar captura de pantalla al cuadro del captcha
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
        raise HTTPException(status_code=500, detail=f"Error de conexión con Veracruz (Timeout/Bloqueo): {str(e)}")
