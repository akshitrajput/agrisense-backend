import base64
import requests
import os
import json
import io
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- Configuration ---
KINDWISE_API_KEY = os.getenv("KINDWISE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KINDWISE_API_URL = "https://crop.kindwise.com/api/v1/identification"

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# --- Font Registration for PDF ---
try:
    pdfmetrics.registerFont(TTFont('NotoSans', 'fonts/NotoSans-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari', 'fonts/NotoSansDevanagari-Regular.ttf'))
except Exception as e:
    print(f"Font loading error: {e}. Make sure font files are in the 'fonts' directory.")

app = FastAPI()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Language & Font Mapping ---
LANGUAGE_MAP = {
    "en": {"name": "English", "font": "NotoSans"},
    "hi": {"name": "Hindi", "font": "NotoSansDevanagari"},
}

# --- Reusable Helper Functions ---

async def perform_full_analysis(image_bytes: bytes, language_code: str) -> dict:
    """Performs the full Kindwise + Gemini analysis and returns a dictionary."""
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    headers = {"Api-Key": KINDWISE_API_KEY, "Content-Type": "application/json"}
    kindwise_data = {"images": [base64_image], "similar_images": True}
    
    kindwise_response = requests.post(KINDWISE_API_URL, headers=headers, json=kindwise_data)
    kindwise_response.raise_for_status()
    kindwise_result = kindwise_response.json()

    gemini_analysis = {"root_cause": "N/A", "pesticides": [], "precautions": "The plant appears healthy."}
    suggestions = kindwise_result.get('result', {}).get('disease', {}).get('suggestions')
    language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])

    if suggestions:
        disease_name = suggestions[0].get('name', 'Unknown Disease')
        confidence = suggestions[0].get('probability', 0)
        intensity = "High" if confidence > 0.75 else "Medium" if confidence > 0.4 else "Low"
        
        prompt = (
            f"You are an agricultural expert for India. Analyze the following plant disease and provide a response in {language_config['name']}. "
            f"Your entire output must be a single, valid JSON object. Do not include any text before or after the JSON. "
            f"Disease: '{disease_name}'. Severity: '{intensity}'. "
            f"The JSON object must have these exact keys: 'root_cause', 'pesticides', 'precautions'."
        )
        
        gemini_response = gemini_model.generate_content(prompt)
        cleaned_response_text = gemini_response.text.strip().lstrip("```json").rstrip("```")
        gemini_analysis = json.loads(cleaned_response_text)

    return {"kindwise_analysis": kindwise_result, "gemini_analysis": gemini_analysis}

def create_pdf_report(analysis_data: dict, language_config: dict) -> io.BytesIO:
    """Generates a PDF report from the analysis data."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    font_name = language_config.get("font", "NotoSans")
    p.setFont("Helvetica-Bold", 20)
    p.drawCentredString(width / 2.0, height - 50, "AgriSense Plant Health Report")
    
    text = p.beginText(40, height - 100)
    text.setFont(font_name, 12, leading=18)

    suggestions = analysis_data.get("kindwise_analysis", {}).get("result", {}).get("disease", {}).get("suggestions", [])
    gemini = analysis_data.get("gemini_analysis", {})
    
    disease_name = "Healthy"
    if suggestions:
        disease_name = suggestions[0].get('name', 'Unknown')

    text.textLine(f"Disease Predicted: {disease_name}")
    text.textLine(f"Root Cause: {gemini.get('root_cause', 'N/A')}")
    text.textLine("")
    text.textLine("Recommended Pesticides:")
    for pesticide in gemini.get('pesticides', []):
        text.textLine(f"  • {pesticide}")
    text.textLine("")
    text.textLine(f"Precautions: {gemini.get('precautions', 'N/A')}")
    
    p.drawText(text)
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# --- API Endpoints ---

@app.get("/")
def read_root():
    return {"message": "AgriSense Backend is running."}

@app.post("/analyze", response_class=JSONResponse)
async def analyze_image_for_map(
    image: UploadFile = File(...), 
    language_code: str = Form("en"),
    row: int = Form(...),
    col: int = Form(...)
):
    """
    Endpoint for the ROVER.
    Analyzes the plant image and returns JSON for the app's real-time map.
    """
    if not KINDWISE_API_KEY or not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="API keys are not configured.")
    try:
        image_bytes = await image.read()
        analysis_result = await perform_full_analysis(image_bytes, language_code)
        analysis_result['coordinates'] = {'row': row, 'col': col}
        return JSONResponse(content=analysis_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/generate_report")
async def generate_pdf_report(
    image: UploadFile = File(...), 
    language_code: str = Form("en")
):
    """
    Endpoint for the APP.
    Generates a downloadable PDF report for a specific plant.
    """
    if not KINDWISE_API_KEY or not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="API keys are not configured.")
    try:
        image_bytes = await image.read()
        analysis_result = await perform_full_analysis(image_bytes, language_code)
        language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])
        
        pdf_buffer = create_pdf_report(analysis_result, language_config)
        
        return StreamingResponse(pdf_buffer, media_type='application/pdf', headers={
            'Content-Disposition': 'attachment; filename="AgriSense_Report.pdf"'
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")