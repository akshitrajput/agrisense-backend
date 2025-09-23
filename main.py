import base64
import requests
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- Configuration ---
KINDWISE_API_KEY = os.getenv("KINDWISE_API_KEY")
KINDWISE_API_URL = "https://crop.kindwise.com/api/v1/identification"

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
    """Root endpoint for basic connectivity check."""
    return {"message": "AgriSense Backend is running."}

@app.get("/ping")
def ping():
    """Dedicated health check endpoint for uptime monitoring."""
    return {"status": "ok", "message": "AgriSense server is healthy."}

@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...)):
    # Check if the API key is set
    if not KINDWISE_API_KEY:
        raise HTTPException(status_code=500, detail="API key is not configured on the server.")

    try:
        image_bytes = await image.read()
        print(f"Received image with size: {len(image_bytes)} bytes")
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        headers = {
            "Api-Key": KINDWISE_API_KEY,
            "Content-Type": "application/json"
        }
        
        # --- FIX IS HERE ---
        # The 'details' parameter has been removed as it's not supported by the API.
        data = {
            "images": [base64_image] 
        }

        print("Forwarding request to Kindwise API...")
        response = requests.post(KINDWISE_API_URL, headers=headers, json=data)
        
        # Adding more detailed error logging
        if response.status_code != 200:
            print("\n--- KINDWISE API ERROR ---")
            print(f"Status Code: {response.status_code}")
            print(f"Error Body (Raw): {response.text}")
            print("--- END KINDWISE API ERROR ---\n")

        response.raise_for_status()

        return JSONResponse(content=response.json())

    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error from Kindwise: {err}")
        raise HTTPException(status_code=response.status_code, detail=response.text)
    except Exception as e:
        print(f"An internal error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")