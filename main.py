# main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import hmac
import hashlib
import traceback

# --- 1. IMPORT THE CLASS, NOT THE INDIVIDUAL FUNCTIONS ---
from clinic_manager import ClinicManager

# Load environment variables from a .env file for local testing
load_dotenv()

# Initialize the FastAPI application
app = FastAPI()

# --- 2. CREATE A SINGLE, SHARED INSTANCE OF THE MANAGER ---
# This happens once when your application starts up.
print("🚀 Initializing ClinicManager...")
manager = ClinicManager()
print("✅ ClinicManager is ready.")


@app.get("/")
async def root():
    """A simple endpoint to confirm the API is live."""
    return {"message": "API is live and running."}

# === Main Vapi Function Call Endpoint ===
@app.post("/")
async def vapi_webhook(request: Request):
    """
    This is the primary endpoint that handles all function calls from Vapi.
    It includes security verification and routes requests to the correct function.
    """
    
    # Security Check: HMAC Signature Verification
    secret = os.getenv("VAPI_SECRET_KEY")
    if secret:
        signature = request.headers.get("x-vapi-signature")
        if not signature:
            print("❌ Security Error: Missing x-vapi-signature header.")
            raise HTTPException(status_code=401, detail="Missing signature")
        
        body = await request.body()
        expected_signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(expected_signature, signature):
            print("❌ Security Error: Invalid signature.")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Payload Processing
    try:
        payload = await request.json()
    except Exception as e:
        print(f"❌ Error parsing request JSON: {e}")
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(e)}"})

    message = payload.get("message")
    if not message or message.get("type") != "function-call":
        return {"message": "Ignored non-function-call message"}

    fn = message.get("functionCall", {}).get("name")
    params = message.get("functionCall", {}).get("parameters", {})
    
    print("\n--- Vapi Function Call Received ---")
    print(f"✅ Function Name: {fn}")
    print(f"✅ Parameters: {params}")

    # Function Routing
    try:
        if fn == "findPatient":
            # --- 3. UPDATED TO USE THE MANAGER INSTANCE ---
            patient = manager.find_patient(
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"patientName": patient.get("fullName").split(" ")[0] if patient else "Not Found"}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "registerNewPatient":
            status = manager.register_patient(params)
            result = {"status": "Success" if status else "Failure"}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "checkAvailability":
            availability = manager.check_availability(params.get("dateTime"))
            result = {"result": availability}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "scheduleAppointment":
            confirmation = manager.schedule_appointment(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"confirmationTime": confirmation.strftime("%A, %B %d at %-I:%M %p") if confirmation else "Failure"}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "cancelAppointment":
            cancelled = manager.cancel_appointment(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"status": "Success" if cancelled else "Not Found"}
            print(f"➡️ Returning result: {result}")
            return result

        print(f"❌ Unknown function called: {fn}")
        return {"error": f"Unknown function: {fn}"}

    except Exception as e:
        print("\n❌❌❌ AN UNEXPECTED ERROR OCCURRED ❌❌❌")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {str(e)}")
        print("--- Full Traceback ---")
        traceback.print_exc()
        print("----------------------\n")
        return {"error": f"An internal server error occurred."}

# === Optional: /agent endpoint for Vapi ===
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

# === Vapi Webhook Catch-All for Logging ===
@app.post("/webhooks/{path:path}")
async def generic_webhook_handler(path: str, request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print(f"ℹ️ Received webhook on '/webhooks/{path}': {data}")
    return {"status": "received"}
