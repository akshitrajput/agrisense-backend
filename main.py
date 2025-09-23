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
    """Receives an image, forwards it to Kindwise, and returns the analysis."""
    if not KINDWISE_API_KEY:
        raise HTTPException(status_code=500, detail="API key is not configured on the server.")

    try:
        # 1. Read and log the size of the incoming image
        image_bytes = await image.read()
        print(f"Received image with size: {len(image_bytes)} bytes")

        # 2. Encode the image for the JSON payload
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        # 3. Prepare the request for the Kindwise API
        headers = {
            "Api-Key": KINDWISE_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "images": [base64_image],
            "details": ["url", "disease_description"]
        }

        # 4. Call the external API
        print("Forwarding request to Kindwise API...")
        response = requests.post(KINDWISE_API_URL, headers=headers, json=data)
        response.raise_for_status()  # Raise an exception for non-2xx status codes

        # 5. Return the successful response
        return JSONResponse(content=response.json())

    except requests.exceptions.HTTPError as err:
        # --- ENHANCED LOGGING BLOCK ---
        # This will print the specific error message from Kindwise
        print("--- KINDWISE API ERROR ---")
        print(f"Status Code: {response.status_code}")
        try:
            # Try to print the JSON error response for more details
            print(f"Error Body: {response.json()}")
        except ValueError:
            # If the response is not JSON, print the raw text
            print(f"Error Body (Raw): {response.text}")
        print("--- END KINDWISE API ERROR ---")
        # --- END OF LOGGING BLOCK ---

        # Re-raise the exception to send the error back to the Flutter app
        raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except Exception as e:
        print(f"An internal server error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")