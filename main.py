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
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

# --- Configuration ---
KINDWISE_API_KEY = os.getenv("KINDWISE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KINDWISE_API_URL = "https://crop.kindwise.com/api/v1/identification"

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# --- Font Registration ---
# **FIX 1:** Register every font file you have downloaded.
# Each font is given a unique name that we can refer to later.
try:
    pdfmetrics.registerFont(TTFont('NotoSans', 'fonts/NotoSans-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansDevanagari', 'fonts/NotoSansDevanagari-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansTamil', 'fonts/NotoSansTamil-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansBengali', 'fonts/NotoSansBengali-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansTelugu', 'fonts/NotoSansTelugu-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansGujarati', 'fonts/NotoSansGujarati-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansKannada', 'fonts/NotoSansKannada-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansOriya', 'fonts/NotoSansOriya-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansMalayalam', 'fonts/NotoSansMalayalam-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansGurmukhi', 'fonts/NotoSansGurmukhi-Regular.ttf'))
except Exception as e:
    print(f"Font loading error: {e}. Make sure all font files are in the 'fonts' directory.")

app = FastAPI()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Language & Font Mapping ---
# **FIX 2:** Update the map to use the newly registered font for each language.
LANGUAGE_MAP = {
    "en": {"name": "English", "font": "NotoSans"},
    "hi": {"name": "Hindi", "font": "NotoSansDevanagari"},
    "ta": {"name": "Tamil", "font": "NotoSansTamil"},
    "bn": {"name": "Bengali", "font": "NotoSansBengali"},
    "te": {"name": "Telugu", "font": "NotoSansTelugu"},
    "mr": {"name": "Marathi", "font": "NotoSansDevanagari"},
    "ur": {"name": "Urdu", "font": "NotoSans"}, # Placeholder: Requires a specific Urdu font like Noto Nastaliq Urdu
    "gu": {"name": "Gujarati", "font": "NotoSansGujarati"},
    "kn": {"name": "Kannada", "font": "NotoSansKannada"},
    "or": {"name": "Odia", "font": "NotoSansOriya"},
    "ml": {"name": "Malayalam", "font": "NotoSansMalayalam"},
    "pa": {"name": "Punjabi", "font": "NotoSansGurmukhi"},
    "as": {"name": "Assamese", "font": "NotoSansBengali"}, # Assamese uses the Bengali script font
}

# --- PDF Design Helper Functions ---
def draw_logo(p, x, y):
    """Draws a simple, elegant leaf logo for the report."""
    p.saveState()
    p.translate(x, y)
    p.setFillColor(HexColor("#2E7D32")) # Dark Green
    path = p.beginPath()
    path.moveTo(0, 0)
    path.curveTo(10, 20, 30, 25, 40, 0)
    path.curveTo(30, -25, 10, -20, 0, 0)
    p.drawPath(path, fill=1, stroke=0)
    p.setStrokeColor(HexColor("#1B5E20")) # Darker Green for the stem
    p.setLineWidth(2)
    p.line(20, 0, 20, -30)
    p.restoreState()

def draw_multiline_text(p, x, y, text_content, max_width):
    """Draws text that wraps automatically."""
    lines = []
    text_content = str(text_content)
    for line in text_content.split('\n'):
        words = line.split()
        current_line = ""
        for word in words:
            if p.stringWidth(current_line + " " + word, p._fontname, p._fontsize) < max_width:
                current_line += " " + word
            else:
                lines.append(current_line.strip())
                current_line = word
        lines.append(current_line.strip())

    for line in lines:
        p.drawString(x, y, line)
        y -= p._leading
    return y


def create_pdf_report(analysis_data: dict, language_config: dict, labels: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    font_name = language_config.get("font", "NotoSans")

    draw_logo(p, 0.5 * inch, height - 0.7 * inch)
    p.setFont("Helvetica-Bold", 22)
    p.drawString(1.2 * inch, height - 0.65 * inch, "AgriSense")
    p.setFont(font_name, 14)
    p.drawString(1.2 * inch, height - 0.9 * inch, labels.get('report_title', "Plant Health Report"))
    p.setStrokeColorRGB(0.8, 0.8, 0.8)
    p.line(0.5 * inch, height - 1.2 * inch, width - 0.5 * inch, height - 1.2 * inch)

    kindwise_suggestions = analysis_data.get("kindwise_analysis", {}).get("result", {}).get("disease", {}).get("suggestions", [])
    gemini_analysis = analysis_data.get("gemini_analysis", {})
    disease_name = "Healthy"
    confidence = 1.0
    if kindwise_suggestions:
        disease_name = kindwise_suggestions[0].get('name', 'Unknown')
        confidence = kindwise_suggestions[0].get('probability', 0.0)
    severity = "High" if confidence > 0.75 else "Medium" if confidence > 0.4 else "Low"

    y_position = height - 1.8 * inch
    p.setFont(font_name, 11)

    p.drawString(0.7 * inch, y_position, f"{labels.get('disease_predicted', 'Disease Predicted')}: {disease_name}")
    p.drawString(0.7 * inch, y_position - 20, f"{labels.get('confidence', 'Confidence')}: {(confidence * 100):.1f}%")
    p.drawString(0.7 * inch, y_position - 40, f"{labels.get('severity', 'Severity')}: {severity}")
    y_position -= 80

    sections = [
        ("root_cause", labels.get('root_cause', "Root Cause")),
        ("pesticides", labels.get('pesticides', "Recommended Pesticides")),
        ("precautions", labels.get('precautions', "Precautions"))
    ]

    for key, title in sections:
        p.setFont(font_name, 14)
        p.setFillColor(HexColor("#1B5E20"))
        p.drawString(0.7 * inch, y_position, title)
        y_position -= 25

        p.setFont(font_name, 11)
        p.setFillColorRGB(0, 0, 0)
        content = gemini_analysis.get(key, 'N/A')

        if isinstance(content, list):
            for item in content:
                y_position = draw_multiline_text(p, 0.9 * inch, y_position, f"• {item}", width - 1.4 * inch)
                y_position -= 5
        else:
            y_position = draw_multiline_text(p, 0.9 * inch, y_position, content, width - 1.4 * inch)

        y_position -= 20

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# --- Endpoints ---
@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...), language_code: str = Form("en"), row: int = Form(...), col: int = Form(...)):
    if not KINDWISE_API_KEY or not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="API keys are not configured on the server.")

    try:
        image_bytes = await image.read()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        headers = {"Api-Key": KINDWISE_API_KEY, "Content-Type": "application/json"}
        kindwise_data = {"images": [base64_image], "similar_images": True}

        kindwise_response = requests.post(KINDWISE_API_URL, headers=headers, json=kindwise_data)
        kindwise_response.raise_for_status()
        kindwise_result = kindwise_response.json()

        language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])

        gemini_result = {
            "labels": {
                "report_title": "Plant Health Report", "disease_predicted": "Disease Predicted",
                "confidence": "Confidence", "severity": "Severity", "root_cause": "Root Cause",
                "pesticides": "Recommended Pesticides", "precautions": "Precautions"
            },
            "analysis": {
                "root_cause": "N/A", "pesticides": [],
                "precautions": "The plant appears healthy. No special precautions are needed."
            }
        }

        suggestions = kindwise_result.get('result', {}).get('disease', {}).get('suggestions')
        if suggestions:
            disease_name = suggestions[0].get('name', 'Unknown Disease')
            confidence = suggestions[0].get('probability', 0)
            intensity = "High" if confidence > 0.75 else "Medium" if confidence > 0.4 else "Low"

            prompt = (
                f"You are an agricultural expert for India. Analyze the following plant disease and provide a response in {language_config['name']}. "
                f"Your entire output must be a single, valid JSON object. Do not include any text before or after the JSON. "
                f"Disease: '{disease_name}'. Severity: '{intensity}'. "
                f"The JSON object must have two main keys: 'labels' and 'analysis'. "
                f"- The 'labels' key must contain a JSON object with translated titles for: 'report_title', 'disease_predicted', 'confidence', 'severity', 'root_cause', 'pesticides', 'precautions'. "
                f"- The 'analysis' key must contain a JSON object with the analysis data for: 'root_cause' (one sentence), 'pesticides' (an array of 2-3 names), and 'precautions' (one sentence)."
            )

            gemini_response = gemini_model.generate_content(prompt)
            cleaned_response_text = gemini_response.text.strip().replace("```json", "").replace("```", "")
            gemini_result = json.loads(cleaned_response_text)

        combined_result = {
            "kindwise_analysis": kindwise_result,
            "gemini_analysis": gemini_result.get("analysis", {}),
            "labels": gemini_result.get("labels", {})
        }

        pdf_buffer = create_pdf_report(combined_result, language_config, combined_result["labels"])

        return StreamingResponse(pdf_buffer, media_type='application/pdf', headers={
            'Content-Disposition': f'attachment; filename="AgriSense_Report_{row}_{col}.pdf"'
        })

    except Exception as e:
        print(f"An internal server error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

