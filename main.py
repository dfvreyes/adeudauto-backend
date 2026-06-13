@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    """ 
    Abre la sesión de forma correcta (Página principal -> Captcha)
    respetando el flujo de Java pero evitando la concurrencia en ScrapingBee.
    """
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar la API Key de ScrapingBee.")

    # Inicializamos la sesión para recolectar las cookies de forma interna
    session = requests.Session()
    url_principal = "https://ovh.veracruz.gob.mx/ovh/consultavehicular"
    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        # PASO 1: Tocar la página de inicio para que el servidor genere el JSESSIONID
        params_inicio = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_principal,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        res_inicio = requests.get(spb_endpoint, params=params_inicio, timeout=30)
        
        if res_inicio.status_code == 403 or res_inicio.status_code == 429:
            raise HTTPException(status_code=429, detail="Límite simultáneo de ScrapingBee. Espera 10 segundos.")
            
        if res_inicio.status_code != 200:
            raise HTTPException(status_code=500, detail="La OVH no asignó cookies iniciales.")

        # Guardamos las cookies obtenidas de la página principal
        session.cookies.update(res_inicio.cookies)
        
        # Preparamos la cadena de cookies para enviársela a ScrapingBee en el segundo paso
        cookie_string = "; ".join([f"{k}={v}" for k, v in session.cookies.items()]) if session.cookies else ""

        # PASO 2: Descargar el captcha inyectando la cookie del Paso 1
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        headers_captcha = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": cookie_string
        }
        
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_captcha, timeout=30)
        
        if res_captcha.status_code != 200:
            raise HTTPException(status_code=500, detail="No se pudo descargar la imagen del captcha con la cookie activa.")
            
        # Convertimos los bytes de la imagen a Base64
        captcha_base64 = base64.b64encode(res_captcha.content).decode('utf-8')
        
        # Guardamos la cookie final actualizada
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
        raise HTTPException(status_code=500, detail=f"Error en el puente de comunicación: {str(e)}")
