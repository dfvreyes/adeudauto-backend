@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    """ Descarga el captcha directamente usando una sola petición de ScrapingBee """
    if SCRAPINGBEE_API_KEY == "TU_API_KEY_AQUI" or not SCRAPINGBEE_API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar la API Key de ScrapingBee.")

    # Una sola petición directa al captcha con cookies limpias
    session = requests.Session()
    url_captcha = "https://ovh.veracruz.gob.mx/ovh/jcaptcha"
    spb_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    try:
        params_captcha = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url_captcha,
            "country_code": "mx",
            "forward_headers": "true"
        }
        
        headers_captcha = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Hacemos una sola petición en lugar de dos seguidas
        res_captcha = requests.get(spb_endpoint, params=params_captcha, headers=headers_captcha, timeout=30)
        
        if res_captcha.status_code == 403:
            raise HTTPException(status_code=429, detail="Límite simultáneo de ScrapingBee alcanzado. Espera 10 segundos.")
            
        if res_captcha.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Error en proxy residencial. Status: {res_captcha.status_code}")
            
        captcha_base64 = base64.b64encode(res_captcha.content).decode('utf-8')
        
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
        raise HTTPException(status_code=500, detail=f"Falla en el puente: {str(e)}")
