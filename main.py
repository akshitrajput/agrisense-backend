import base64
import requests
import os
import json
import io
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
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
# This allows the PDF to be written in different languages.
# Ensure the .ttf files are in a 'fonts' directory.
try:
    pdfmetrics.registerFont(TTFont('NotoSans', 'fonts/NotoSans-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari', 'fonts/NotoSansDevanagari-Regular.ttf'))
    # Add more font registrations here as you download them, e.g., for Tamil, Bengali, etc.
except Exception as e:
    print(f"Font loading error: {e}. Make sure font files are in the 'fonts' directory.")

app = FastAPI()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Language & Font Mapping ---
# Maps language codes from Flutter to full names and the correct font file for the PDF.
LANGUAGE_MAP = {
    "en": {"name": "English", "font": "NotoSans"},
    "hi": {"name": "Hindi", "font": "NotoSansDevanagari"},
    "ta": {"name": "Tamil", "font": "NotoSans"}, # Placeholder: Requires a specific Tamil font
    "bn": {"name": "Bengali", "font": "NotoSans"}, # Placeholder
    "te": {"name": "Telugu", "font": "NotoSans"}, # Placeholder
    "mr": {"name": "Marathi", "font": "NotoSansDevanagari"},
    "ur": {"name": "Urdu", "font": "NotoSans"}, # Placeholder
    "gu": {"name": "Gujarati", "font": "NotoSans"}, # Placeholder
    "kn": {"name": "Kannada", "font": "NotoSans"}, # Placeholder
    "or": {"name": "Odia", "font": "NotoSans"}, # Placeholder
    "ml": {"name": "Malayalam", "font": "NotoSans"}, # Placeholder
    "pa": {"name": "Punjabi", "font": "NotoSans"}, # Placeholder
    "as": {"name": "Assamese", "font": "NotoSans"}, # Placeholder
}

# --- PDF Generation Helper Function ---
def create_pdf_report(analysis_data: dict, language_config: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    font_name = language_config.get("font", "NotoSans")
    
    # Title
    p.setFont("Helvetica-Bold", 20)
    p.drawCentredString(width / 2.0, height - 50, "AgriSense Plant Health Report")
    
    # Content
    text = p.beginText(40, height - 100)
    text.setFont(font_name, 12, leading=18) # Set font and line spacing

    # Extract data with fallbacks
    kindwise_suggestions = analysis_data.get("kindwise_analysis", {}).get("result", {}).get("disease", {}).get("suggestions", [])
    gemini_analysis = analysis_data.get("gemini_analysis", {})
    
    disease_name = "Healthy"
    confidence = 1.0
    if kindwise_suggestions:
        disease_name = kindwise_suggestions[0].get('name', 'Unknown')
        confidence = kindwise_suggestions[0].get('probability', 0.0)

    severity = "High" if confidence > 0.75 else "Medium" if confidence > 0.4 else "Low"

    # Write data to PDF
    text.textLine(f"Disease Predicted: {disease_name}")
    text.textLine(f"Confidence: {(confidence * 100):.1f}%")
    text.textLine(f"Severity: {severity}")
    text.textLine("") # Spacer
    
    text.setFont(font_name, 14, leading=20) # Bolder font for subtitles
    text.textLine("Root Cause:")
    text.setFont(font_name, 12, leading=18)
    text.textLine(f"  {gemini_analysis.get('root_cause', 'N/A')}")
    text.textLine("") # Spacer
    
    text.setFont(font_name, 14, leading=20)
    text.textLine("Recommended Pesticides (Indian Market):")
    text.setFont(font_name, 12, leading=18)
    for pesticide in gemini_analysis.get('pesticides', []):
        text.textLine(f"  • {pesticide}")
    text.textLine("") # Spacer

    text.setFont(font_name, 14, leading=20)
    text.textLine("Precautions:")
    text.setFont(font_name, 12, leading=18)
    text.textLine(f"  {gemini_analysis.get('precautions', 'N/A')}")
    
    p.drawText(text)
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer

# --- Endpoints ---
@app.get("/")
def read_root():
    return {"message": "AgriSense Backend is running."}

@app.api_route("/ping", methods=["GET", "HEAD"])
def ping():
    """Dedicated health check endpoint for uptime monitoring."""
    return {"status": "ok", "message": "AgriSense server is healthy."}

@app.post("/analyze")
async def analyze_image(
    image: UploadFile = File(...),
    language_code: str = Form("en"),
    row: int = Form(...),
    col: int = Form(...)
):
    print(f"Received image for coordinate ({row}, {col}) in language: {language_code}")
    if not KINDWISE_API_KEY or not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="API keys are not configured on the server.")

    try:
        image_bytes = await image.read()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        headers = {"Api-Key": KINDWISE_API_KEY, "Content-Type": "application/json"}
        kindwise_data = {"images": [base64_image], "similar_images": True}
        
        print("Forwarding request to Kindwise API...")
        kindwise_response = requests.post(KINDWISE_API_URL, headers=headers, json=kindwise_data)
        kindwise_response.raise_for_status()
        kindwise_result = kindwise_response.json()

        gemini_analysis = {"root_cause": "N/A", "pesticides": [], "precautions": "The plant appears healthy. No special precautions are needed."}
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
                f"The JSON object must have these exact keys: 'root_cause', 'pesticides', 'precautions'. "
                f"- 'root_cause': A concise, one-sentence explanation. "
                f"- 'pesticides': A JSON array of 2-3 specific pesticide names. "
                f"- 'precautions': A concise, one-sentence summary."
            )
            
            print(f"Generating detailed analysis for: {disease_name} in {language_config['name']}")
            gemini_response = gemini_model.generate_content(prompt)
            cleaned_response_text = gemini_response.text.strip().replace("```json", "").replace("```", "")
            gemini_analysis = json.loads(cleaned_response_text)

        combined_result = {"kindwise_analysis": kindwise_result, "gemini_analysis": gemini_analysis}
        
        # Generate and return a PDF file instead of JSON.
        pdf_buffer = create_pdf_report(combined_result, language_config)
        
        return StreamingResponse(pdf_buffer, media_type='application/pdf', headers={
            'Content-Disposition': 'attachment; filename="AgriSense_Report.pdf"'
        })

    except Exception as e:
        print(f"An internal server error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

