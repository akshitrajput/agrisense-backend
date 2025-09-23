import base64
import requests
import os # <--- Import the 'os' module
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- Configuration ---
# **FIX:** Get the API key from an environment variable
KINDWISE_API_KEY = os.getenv("KINDWISE_API_KEY") 
KINDWISE_API_URL = "https://crop.kindwise.com/api/v1/identification"

app = FastAPI()

# CORS middleware is fine for production as well
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "AgriSense Backend is running."}

@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...)):
    # **Check if the API key is set**
    if not KINDWISE_API_KEY:
        raise HTTPException(status_code=500, detail="API key is not configured on the server.")

    try:
        image_bytes = await image.read()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        headers = {
            "Api-Key": KINDWISE_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "images": [base64_image],
            "details": ["url", "disease_description"]
        }

        print("Forwarding request to Kindwise API...")
        response = requests.post(KINDWISE_API_URL, headers=headers, json=data)
        response.raise_for_status()

        return JSONResponse(content=response.json())

    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error from Kindwise: {err}")
        raise HTTPException(status_code=response.status_code, detail=response.text)
    except Exception as e:
        print(f"An internal error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
