@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    """
    Descarga el captcha de Veracruz leyendo y encadenando las cookies 
    nativas que ScrapingBee extrae del portal del gobierno.
    """
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar la API Key de ScrapingBee.")

    url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        # PASO 1: Tocamos la página principal para despertar el JSESSIONID del gobierno
        params_inicio = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_principal,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        res_inicio = requests.get(spb_endpoint, params=params_inicio, timeout=30)
        
        if res_inicio.status_code in [403, 429]:
            raise HTTPException(status_code=429, detail="Límite simultáneo de ScrapingBee alcanzado. Espera 10 segundos.")
            
        if res_inicio.status_code != 200:
            raise HTTPException(status_code=500, detail="El portal de Veracruz no respondió a la petición inicial.")

        # 🍪 Extracción Segura de Cookies: ScrapingBee las envía a veces en los headers de respuesta
        cookie_header = res_inicio.headers.get("Set-Cookie", "")
        if not cookie_header and res_inicio.cookies:
            cookie_header = "; ".join([f"{k}={v}" for k, v in res_inicio.cookies.items()])

        # PASO 2: Descargar el captcha inyectando la cookie recolectada
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        headers_captcha = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if cookie_header:
            headers_captcha["Cookie"] = cookie_header
        
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_captcha, timeout=30)
        
        if res_captcha.status_code != 200:
            raise HTTPException(status_code=500, detail="No se pudo descargar la imagen del captcha a través del túnel residencial.")
            
        # Convertimos la imagen limpia a Base64
        captcha_base64 = base64.b64encode(res_captcha.content).decode('utf-8')
        
        # Guardamos las cookies finales asociadas a esta sesión para el POST posterior
        session = requests.Session()
        if cookie_header:
            # Rehidratamos una sesión falsa con las cookies de texto para que el POST las use
            for c in cookie_header.split(";"):
                if "=" in c:
                    partes = c.strip().split("=", 1)
                    session.cookies.set(partes[0], partes[1])
        if res_captcha.cookies:
            session.cookies.update(res_captcha.cookies)

        session_id = str(id(session))
        sesiones_globales[session_id] = session
        
        return {
            "session_id": session_id,
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el puente de cookies: {str(e)}")
