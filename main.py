import base64
import requests
import os
import json
import io
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import paho.mqtt.client as mqtt
import shutil

# --- Configuration ---
KINDWISE_API_KEY = os.getenv("KINDWISE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KINDWISE_API_URL = "https://crop.kindwise.com/api/v1/identification"
MQTT_HOSTNAME = os.getenv("MQTT_HOSTNAME")
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

# Create directories for temporary storage
os.makedirs("temp_uploads", exist_ok=True)
os.makedirs("reports", exist_ok=True)

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# --- Font Registration ---
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
    print(f"Font loading error: {e}. Make sure font files are in the 'fonts' directory.")

app = FastAPI()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Language & Font Mapping ---
LANGUAGE_MAP = {
    "en": {"name": "English", "font": "NotoSans"},
    "hi": {"name": "Hindi", "font": "NotoSansDevanagari"},
    "ta": {"name": "Tamil", "font": "NotoSansTamil"},
    "bn": {"name": "Bengali", "font": "NotoSansBengali"},
    "te": {"name": "Telugu", "font": "NotoSansTelugu"},
    "mr": {"name": "Marathi", "font": "NotoSansDevanagari"},
    "ur": {"name": "Urdu", "font": "NotoSans"},
    "gu": {"name": "Gujarati", "font": "NotoSansGujarati"},
    "kn": {"name": "Kannada", "font": "NotoSansKannada"},
    "or": {"name": "Odia", "font": "NotoSansOriya"},
    "ml": {"name": "Malayalam", "font": "NotoSansMalayalam"},
    "pa": {"name": "Punjabi", "font": "NotoSansGurmukhi"},
    "as": {"name": "Assamese", "font": "NotoSansBengali"},
}

# --- PDF Design Helper Functions ---
def draw_logo(p, x, y):
    p.saveState()
    p.translate(x, y)
    p.setFillColor(HexColor("#2E7D32"))
    path = p.beginPath()
    path.moveTo(0, 0)
    path.curveTo(10, 20, 30, 25, 40, 0)
    path.curveTo(30, -25, 10, -20, 0, 0)
    p.drawPath(path, fill=1, stroke=0)
    p.setStrokeColor(HexColor("#1B5E20"))
    p.setLineWidth(2)
    p.line(20, 0, 20, -30)
    p.restoreState()

def draw_multiline_text(p, x, y, text_content, max_width):
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

    sections = [("root_cause", labels.get('root_cause', "Root Cause")), ("pesticides", labels.get('pesticides', "Recommended Pesticides")), ("precautions", labels.get('precautions', "Precautions"))]
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

# --- Main Logic Functions ---
def analyze_single_image_data(image_bytes: bytes) -> dict:
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    headers = {"Api-Key": KINDWISE_API_KEY, "Content-Type": "application/json"}
    kindwise_data = {"images": [base64_image], "similar_images": True}
    response = requests.post(KINDWISE_API_URL, headers=headers, json=kindwise_data)
    response.raise_for_status()
    return response.json()

def get_gemini_analysis(disease_summary: str, language_config: dict) -> dict:
    prompt = (
        f"You are an agricultural expert for India. Analyze the following plant disease(s) and provide a response in {language_config['name']}. "
        f"Your entire output must be a single, valid JSON object. "
        f"Diseases found: '{disease_summary}'. "
        f"The JSON object must have two main keys: 'labels' and 'analysis'. "
        f"- 'labels': Translated titles for 'report_title', 'disease_predicted', 'confidence', 'severity', 'root_cause', 'pesticides', 'precautions'. "
        f"- 'analysis': Data for 'root_cause', 'pesticides' (an array), and 'precautions'."
    )
    gemini_response = gemini_model.generate_content(prompt)
    cleaned_response_text = gemini_response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(cleaned_response_text)

def publish_mqtt_notification(topic: str, message: str):
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.tls_set(tls_version=mqtt.ssl.PROTOCOL_TLS)
        client.connect(MQTT_HOSTNAME, MQTT_PORT, 60)
        client.publish(topic, message)
        client.disconnect()
        print(f"Published '{message}' to topic '{topic}'")
    except Exception as e:
        print(f"Failed to publish MQTT message: {e}")

# --- Background Task for Rover Survey ---
def process_survey_report(survey_id: str, language_code: str):
    print(f"Starting background processing for survey: {survey_id}")
    survey_dir = f"temp_uploads/{survey_id}"
    image_files = [f for f in os.listdir(survey_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
    disease_counts = {}
    
    for image_file in image_files:
        with open(os.path.join(survey_dir, image_file), "rb") as f:
            image_bytes = f.read()
        analysis = analyze_single_image_data(image_bytes)
        suggestions = analysis.get('result', {}).get('disease', {}).get('suggestions', [])
        if suggestions:
            disease_name = suggestions[0].get('name', 'Unknown')
            disease_counts[disease_name] = disease_counts.get(disease_name, 0) + 1

    summary = "All plants appear healthy."
    if disease_counts:
        summary = ", ".join([f"{count} plant(s) with {name}" for name, count in disease_counts.items()])
    
    language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])
    gemini_result = get_gemini_analysis(summary, language_config)
    
    consolidated_kindwise = {"result": {"disease": {"suggestions": [{"name": summary, "probability": 1.0}]}}}
    combined_result = {"kindwise_analysis": consolidated_kindwise, "gemini_analysis": gemini_result.get("analysis", {}), "labels": gemini_result.get("labels", {})}
    
    pdf_buffer = create_pdf_report(combined_result, language_config, combined_result["labels"])
    report_path = f"reports/AgriSense_Report_{survey_id}.pdf"
    with open(report_path, "wb") as f:
        f.write(pdf_buffer.getvalue())
    
    shutil.rmtree(survey_dir)
    publish_mqtt_notification("agrisense/user/report_ready", survey_id)

# --- Endpoints ---
@app.get("/")
def read_root():
    return {"message": "AgriSense Backend is running."}

@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...), language_code: str = Form("en"), row: int = Form(...), col: int = Form(...)):
    if not KINDWISE_API_KEY or not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="API keys are not configured.")
    try:
        image_bytes = await image.read()
        kindwise_result = analyze_single_image_data(image_bytes)
        
        gemini_result = {"labels": {}, "analysis": {"root_cause": "N/A", "pesticides": [], "precautions": "Plant is healthy."}}
        suggestions = kindwise_result.get('result', {}).get('disease', {}).get('suggestions')
        language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])
        
        if suggestions:
            disease_name = suggestions[0].get('name', 'Unknown Disease')
            gemini_result = get_gemini_analysis(disease_name, language_config)
            
        combined_result = {"kindwise_analysis": kindwise_result, "gemini_analysis": gemini_result.get("analysis", {}), "labels": gemini_result.get("labels", {})}
        pdf_buffer = create_pdf_report(combined_result, language_config, combined_result["labels"])
        
        return StreamingResponse(pdf_buffer, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="AgriSense_Report_R{row}_C{col}.pdf"'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/rover/upload_image")
async def upload_rover_image(survey_id: str = Form(...), image: UploadFile = File(...)):
    survey_dir = f"temp_uploads/{survey_id}"
    os.makedirs(survey_dir, exist_ok=True)
    file_path = os.path.join(survey_dir, image.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    return {"status": "success", "filename": image.filename, "survey_id": survey_id}

@app.post("/rover/survey_complete")
async def survey_complete(background_tasks: BackgroundTasks, data: dict):
    survey_id = data.get("survey_id")
    language_code = data.get("language_code", "en")
    if not survey_id:
        raise HTTPException(status_code=400, detail="Survey ID is required.")
    background_tasks.add_task(process_survey_report, survey_id, language_code)
    return {"status": "processing_started", "message": f"Analysis for survey {survey_id} has begun."}

@app.get("/reports/{survey_id}")
async def get_report(survey_id: str):
    report_path = f"reports/AgriSense_Report_{survey_id}.pdf"
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found or not yet ready.")
    return FileResponse(report_path, media_type='application/pdf', filename=f"AgriSense_Report_{survey_id}.pdf")

