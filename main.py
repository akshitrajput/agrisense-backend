# import base64
# import requests
# import os
# import json
# import io
# import google.generativeai as genai
# from fastapi import FastAPI, UploadFile, File, Form, HTTPException
# from fastapi.responses import JSONResponse, StreamingResponse
# from fastapi.middleware.cors import CORSMiddleware
# from reportlab.pdfgen import canvas
# from reportlab.lib.pagesizes import letter
# from reportlab.pdfbase import pdfmetrics
# from reportlab.pdfbase.ttfonts import TTFont

# # --- Configuration ---
# KINDWISE_API_KEY = os.getenv("KINDWISE_API_KEY")
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# KINDWISE_API_URL = "https://crop.kindwise.com/api/v1/identification"

# genai.configure(api_key=GEMINI_API_KEY)
# gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# # --- Font Registration for PDF ---
# try:
#     pdfmetrics.registerFont(TTFont('NotoSans', 'fonts/NotoSans-Regular.ttf'))
#     pdfmetrics.registerFont(TTFont('NotoSansDevanagari', 'fonts/NotoSansDevanagari-Regular.ttf'))
# except Exception as e:
#     print(f"Font loading error: {e}. Make sure font files are in the 'fonts' directory.")

# app = FastAPI()

# # --- Middleware ---
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # --- Language & Font Mapping ---
# LANGUAGE_MAP = {
#     "en": {"name": "English", "font": "NotoSans"},
#     "hi": {"name": "Hindi", "font": "NotoSansDevanagari"},
# }

# # --- Reusable Helper Functions ---

# async def perform_full_analysis(image_bytes: bytes, language_code: str) -> dict:
#     """Performs the full Kindwise + Gemini analysis and returns a dictionary."""
#     base64_image = base64.b64encode(image_bytes).decode('utf-8')
#     headers = {"Api-Key": KINDWISE_API_KEY, "Content-Type": "application/json"}
#     kindwise_data = {"images": [base64_image], "similar_images": True}
    
#     print("\n>>> Sending request to Kindwise API...")
#     kindwise_response = requests.post(KINDWISE_API_URL, headers=headers, json=kindwise_data)
#     kindwise_response.raise_for_status()
#     kindwise_result = kindwise_response.json()

#     # <<< CHANGE: ADDED THIS PRINT STATEMENT FOR DEBUGGING >>>
#     print("\n--- KINDWISE API RESPONSE ---")
#     print(json.dumps(kindwise_result, indent=2)) # Pretty-print the JSON
#     print("-----------------------------\n")

#     gemini_analysis = {"root_cause": "N/A", "pesticides": [], "precautions": "The plant appears healthy."}
#     suggestions = kindwise_result.get('result', {}).get('disease', {}).get('suggestions')
#     language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])

#     if suggestions:
#         disease_name = suggestions[0].get('name', 'Unknown Disease')
#         confidence = suggestions[0].get('probability', 0)
#         intensity = "High" if confidence > 0.75 else "Medium" if confidence > 0.4 else "Low"
        
#         prompt = (
#             f"You are an agricultural expert for India. Analyze the following plant disease and provide a response in {language_config['name']}. "
#             f"Your entire output must be a single, valid JSON object. Do not include any text before or after the JSON. "
#             f"Disease: '{disease_name}'. Severity: '{intensity}'. "
#             f"The JSON object must have these exact keys: 'root_cause', 'pesticides', 'precautions'."
#         )
        
#         print(">>> Sending request to Gemini API...")
#         gemini_response = gemini_model.generate_content(prompt)
#         cleaned_response_text = gemini_response.text.strip().lstrip("```json").rstrip("```")
#         gemini_analysis = json.loads(cleaned_response_text)

#     return {"kindwise_analysis": kindwise_result, "gemini_analysis": gemini_analysis}

# def create_pdf_report(analysis_data: dict, language_config: dict) -> io.BytesIO:
#     """Generates a PDF report from the analysis data."""
#     buffer = io.BytesIO()
#     p = canvas.Canvas(buffer, pagesize=letter)
#     width, height = letter
#     font_name = language_config.get("font", "NotoSans")
#     p.setFont("Helvetica-Bold", 20)
#     p.drawCentredString(width / 2.0, height - 50, "AgriSense Plant Health Report")
    
#     text = p.beginText(40, height - 100)
#     text.setFont(font_name, 12, leading=18)

#     suggestions = analysis_data.get("kindwise_analysis", {}).get("result", {}).get("disease", {}).get("suggestions", [])
#     gemini = analysis_data.get("gemini_analysis", {})
    
#     disease_name = "Healthy"
#     if suggestions:
#         disease_name = suggestions[0].get('name', 'Unknown')

#     text.textLine(f"Disease Predicted: {disease_name}")
#     text.textLine(f"Root Cause: {gemini.get('root_cause', 'N/A')}")
#     text.textLine("")
#     text.textLine("Recommended Pesticides:")
#     for pesticide in gemini.get('pesticides', []):
#         text.textLine(f"  • {pesticide}")
#     text.textLine("")
#     text.textLine(f"Precautions: {gemini.get('precautions', 'N/A')}")
    
#     p.drawText(text)
#     p.showPage()
#     p.save()
#     buffer.seek(0)
#     return buffer

# # --- API Endpoints ---

# @app.get("/")
# def read_root():
#     return {"message": "AgriSense Backend is running."}

# @app.post("/analyze", response_class=JSONResponse)
# async def analyze_image_for_map(
#     image: UploadFile = File(...), 
#     language_code: str = Form("en"),
#     row: int = Form(...),
#     col: int = Form(...)
# ):
#     """
#     Endpoint for the ROVER.
#     Analyzes the plant image and returns JSON for the app's real-time map.
#     """
#     if not KINDWISE_API_KEY or not GEMINI_API_KEY:
#         raise HTTPException(status_code=500, detail="API keys are not configured.")
#     try:
#         image_bytes = await image.read()
#         analysis_result = await perform_full_analysis(image_bytes, language_code)
#         analysis_result['coordinates'] = {'row': row, 'col': col}
#         return JSONResponse(content=analysis_result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# @app.post("/generate_report")
# async def generate_pdf_report(
#     image: UploadFile = File(...), 
#     language_code: str = Form("en")
# ):
#     """
#     Endpoint for the APP.
#     Generates a downloadable PDF report for a specific plant.
#     """
#     if not KINDWISE_API_KEY or not GEMINI_API_KEY:
#         raise HTTPException(status_code=500, detail="API keys are not configured.")
#     try:
#         image_bytes = await image.read()
#         analysis_result = await perform_full_analysis(image_bytes, language_code)
#         language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])
        
#         pdf_buffer = create_pdf_report(analysis_result, language_config)
        
#         return StreamingResponse(pdf_buffer, media_type='application/pdf', headers={
#             'Content-Disposition': 'attachment; filename="AgriSense_Report.pdf"'
#         })
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")





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

# ... (Font Registration, Middleware, and Language Mapping remain the same) ...
# ... (PDF Helper Functions like draw_logo and create_pdf_report remain the same) ...

# --- Main Logic Functions ---

def analyze_single_image_data(image_bytes: bytes) -> dict:
    """Analyzes a single image using Kindwise and returns the result."""
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    headers = {"Api-Key": KINDWISE_API_KEY, "Content-Type": "application/json"}
    kindwise_data = {"images": [base64_image], "similar_images": True}
    response = requests.post(KINDWISE_API_URL, headers=headers, json=kindwise_data)
    response.raise_for_status()
    return response.json()

def get_gemini_analysis(disease_summary: str, language_config: dict) -> dict:
    """Gets detailed analysis from Gemini based on a summary of diseases."""
    prompt = (
        f"You are an agricultural expert for India. A farm survey has found plants with the following diseases: {disease_summary}. "
        f"Provide a consolidated report in {language_config['name']}. Your entire output must be a single, valid JSON object. "
        f"The JSON object must have two main keys: 'labels' and 'analysis'. "
        f"- The 'labels' key must contain a JSON object with translated titles for: 'report_title', 'disease_predicted', 'confidence', 'severity', 'root_cause', 'pesticides', 'precautions'. "
        f"- The 'analysis' key must contain a JSON object with the analysis data for: 'root_cause' (a summary of common causes for these diseases), "
        f"'pesticides' (a list of 2-3 general-purpose pesticides for these issues), and 'precautions' (a summary of preventative measures)."
    )
    gemini_response = gemini_model.generate_content(prompt)
    cleaned_response_text = gemini_response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(cleaned_response_text)

def publish_mqtt_notification(topic: str, message: str):
    """Connects to MQTT broker and publishes a message."""
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
    """
    This function runs in the background. It gathers all images for a survey,
    analyzes them, generates a consolidated PDF, and sends a notification.
    """
    print(f"Starting background processing for survey: {survey_id}")
    survey_dir = f"temp_uploads/{survey_id}"
    image_files = [f for f in os.listdir(survey_dir) if f.endswith('.jpg')]
    
    disease_counts = {}
    total_images = len(image_files)
    
    for image_file in image_files:
        with open(os.path.join(survey_dir, image_file), "rb") as f:
            image_bytes = f.read()
        analysis = analyze_single_image_data(image_bytes)
        suggestions = analysis.get('result', {}).get('disease', {}).get('suggestions', [])
        if suggestions:
            disease_name = suggestions[0].get('name', 'Unknown')
            disease_counts[disease_name] = disease_counts.get(disease_name, 0) + 1

    # Create a summary of found diseases
    if not disease_counts:
        summary = "All plants appear healthy."
    else:
        summary = ", ".join([f"{count} plant(s) with {name}" for name, count in disease_counts.items()])
    
    print(f"Survey Summary: {summary}")
    
    # Get analysis from Gemini
    language_config = LANGUAGE_MAP.get(language_code, LANGUAGE_MAP["en"])
    gemini_result = get_gemini_analysis(summary, language_config)
    
    # Create a dummy Kindwise result for the PDF generator
    consolidated_kindwise = {"result": {"disease": {"suggestions": [{"name": summary, "probability": 1.0}]}}}
    
    combined_result = {
        "kindwise_analysis": consolidated_kindwise,
        "gemini_analysis": gemini_result.get("analysis", {}),
        "labels": gemini_result.get("labels", {})
    }
    
    # Generate and save the PDF
    pdf_buffer = create_pdf_report(combined_result, language_config, combined_result["labels"])
    report_path = f"reports/AgriSense_Report_{survey_id}.pdf"
    with open(report_path, "wb") as f:
        f.write(pdf_buffer.getvalue())
    
    print(f"Consolidated report saved at: {report_path}")
    
    # Clean up temporary images
    shutil.rmtree(survey_dir)
    
    # Notify the app that the report is ready
    notification_topic = "agrisense/user/report_ready" # In a real app, this would be user-specific
    publish_mqtt_notification(notification_topic, survey_id)

# --- Endpoints ---

@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...), language_code: str = Form("en"), row: int = Form(...), col: int = Form(...)):
    """Endpoint for single-image analysis by the user."""
    # ... This endpoint's logic remains the same ...

# **NEW ENDPOINT**
@app.post("/rover/upload_image")
async def upload_rover_image(survey_id: str = Form(...), image: UploadFile = File(...)):
    """Endpoint for the rover to upload images one by one."""
    survey_dir = f"temp_uploads/{survey_id}"
    os.makedirs(survey_dir, exist_ok=True)
    
    file_path = os.path.join(survey_dir, image.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
        
    return {"status": "success", "filename": image.filename, "survey_id": survey_id}

# **NEW ENDPOINT**
@app.post("/rover/survey_complete")
async def survey_complete(background_tasks: BackgroundTasks, data: dict):
    """Endpoint for the rover to call when it's finished uploading all images."""
    survey_id = data.get("survey_id")
    language_code = data.get("language_code", "en") # Assume a default or pass from rover
    if not survey_id:
        raise HTTPException(status_code=400, detail="Survey ID is required.")
    
    # Start the long-running analysis process in the background
    background_tasks.add_task(process_survey_report, survey_id, language_code)
    
    return {"status": "processing_started", "message": f"Analysis for survey {survey_id} has begun."}

# **NEW ENDPOINT**
@app.get("/reports/{survey_id}")
async def get_report(survey_id: str):
    """Endpoint for the Flutter app to download a generated report."""
    report_path = f"reports/AgriSense_Report_{survey_id}.pdf"
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found or not yet ready.")
    return FileResponse(report_path, media_type='application/pdf', filename=f"AgriSense_Report_{survey_id}.pdf")

