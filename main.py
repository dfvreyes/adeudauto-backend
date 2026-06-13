from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import base64

app = FastAPI()

# Permitir conexiones desde Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diccionario centralizado para guardar sesiones de cualquier estado
sesiones_globales = {}

class ConsultaEstadoRequest(BaseModel):
    session_id: str
    placa: str
    captcha_texto: str

@app.get("/")
async def root():
    return {"status": "ok", "message": "Servidor Central de Adeudos Activo"}

# --- SECCIÓN: VERACRUZ ---

@app.get("/api/veracruz/captcha")
async def captcha_veracruz():
    # Aquí meteremos la lógica del Proxy Residencial para obtener el Captcha real
    return {"message": "Listo para conectar el proxy residencial"}

@app.post("/api/veracruz/consultar")
async def consultar_veracruz(req: ConsultaEstadoRequest):
    # Aquí meteremos la lógica del Proxy Residencial para enviar los datos a SEFIPLAN
    return {"message": "Listo para enviar formulario con proxy"}
