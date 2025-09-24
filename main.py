import base64
import requests
import os
import google.generativeai as genai # Import the Gemini library
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- Configuration ---
KINDWISE_API_KEY = os.getenv("KINDWISE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Get the new Gemini key
KINDWISE_API_URL = "https://crop.kindwise.com/api/v1/identification"

# Configure the Gemini client
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

app = FastAPI()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Endpoints ---
@app.get("/")
def read_root():
    return {"message": "AgriSense Backend is running."}

@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...)):
    if not KINDWISE_API_KEY or not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="API keys are not configured on the server.")

    try:
        # --- Step 1: Call Kindwise API (Existing Logic) ---
        image_bytes = await image.read()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        headers = {"Api-Key": KINDWISE_API_KEY, "Content-Type": "application/json"}
        kindwise_data = {"images": [base64_image], "similar_images": True}

        print("Forwarding request to Kindwise API...")
        kindwise_response = requests.post(KINDWISE_API_URL, headers=headers, json=kindwise_data)
        kindwise_response.raise_for_status()
        kindwise_result = kindwise_response.json()

        # --- Step 2: Extract Disease Info & Call Gemini API ---
        pesticide_recommendation = "No specific recommendation available." # Default value
        suggestions = kindwise_result.get('result', {}).get('disease', {}).get('suggestions')

        if suggestions:
            disease_name = suggestions[0].get('name', 'Unknown Disease')
            confidence = suggestions[0].get('probability', 0)
            intensity = "High" if confidence > 0.75 else "Medium" if confidence > 0.4 else "Low"

            # Create a specific prompt for Gemini
            prompt = (
                f"As an agricultural expert, suggest a specific, commonly available pesticide "
                f"in India for the following crop disease. Be concise and practical. "
                f"Disease: {disease_name}. Intensity: {intensity}."
            )

            print(f"Generating recommendation for: {disease_name}")
            gemini_response = gemini_model.generate_content(prompt)
            pesticide_recommendation = gemini_response.text

        # --- Step 3: Combine Results ---
        # Create a new, combined response to send back to the Flutter app
        combined_result = {
            "kindwise_analysis": kindwise_result,
            "pesticide_recommendation": pesticide_recommendation.strip()
        }

        return JSONResponse(content=combined_result)

    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error from Kindwise: {err.response.text}")
        raise HTTPException(status_code=err.response.status_code, detail=err.response.text)
    except Exception as e:
        print(f"An internal server error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
