# main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import hmac
import hashlib
import traceback

# Import your custom logic from the other file
from clinic_manager import (
    find_patient_in_sheet,
    register_patient_in_sheet,
    check_calendar_availability,
    schedule_event_in_calendar,
    cancel_appointment_in_calendar
)

# Load environment variables from a .env file for local testing
load_dotenv()

# Initialize the FastAPI application
app = FastAPI()

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
    
    # --- Security Check: HMAC Signature Verification (CRITICAL IMPROVEMENT) ---
    # This ensures the request is genuinely from Vapi and hasn't been tampered with.
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

    # --- Payload Processing ---
    try:
        payload = await request.json()
    except Exception as e:
        print(f"❌ Error parsing request JSON: {e}")
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(e)}"})

    message = payload.get("message")
    if not message or message.get("type") != "function-call":
        # This is normal for many Vapi messages (e.g., transcript updates). We just ignore them.
        return {"message": "Ignored non-function-call message"}

    fn = message.get("functionCall", {}).get("name")
    params = message.get("functionCall", {}).get("parameters", {})
    
    # --- Enhanced Logging ---
    print("\n--- Vapi Function Call Received ---")
    print(f"✅ Function Name: {fn}")
    print(f"✅ Parameters: {params}")

    # --- Function Routing ---
    try:
        if fn == "findPatient":
            # FIXED: Now correctly passes mobileNumber and dob
            patient = find_patient_in_sheet(
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"patientName": patient.get("fullName").split(" ")[0] if patient else "Not Found"}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "registerNewPatient":
            status = register_patient_in_sheet(params)
            result = {"status": "Success" if status else "Failure"}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "checkAvailability":
            availability = check_calendar_availability(params.get("dateTime"))
            result = {"result": availability}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "scheduleAppointment":
            # FIXED: Passes verification details and no longer uses 'reason'
            confirmation = schedule_event_in_calendar(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"confirmationTime": confirmation.strftime("%A, %B %d at %-I:%M %p") if confirmation else "Failure"}
            print(f"➡️ Returning result: {result}")
            return result

        if fn == "cancelAppointment":
            # FIXED: Passes verification details instead of fullName
            cancelled = cancel_appointment_in_calendar(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"status": "Success" if cancelled else "Not Found"}
            print(f"➡️ Returning result: {result}")
            return result

        # If the function name doesn't match any known functions
        print(f"❌ Unknown function called: {fn}")
        return {"error": f"Unknown function: {fn}"}

    except Exception as e:
        # --- Enhanced Error Logging (CRITICAL FOR DEBUGGING) ---
        print("\n❌❌❌ AN UNEXPECTED ERROR OCCURRED ❌❌❌")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {str(e)}")
        print("--- Full Traceback ---")
        traceback.print_exc() # This prints the exact line number of the error
        print("----------------------\n")
        return {"error": f"An internal server error occurred."}

# === Optional: /agent endpoint for Vapi (forwards to the main endpoint) ===
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

# === Vapi Webhook Catch-All for Logging (CLEANUP) ===
@app.post("/webhooks/{path:path}")
async def generic_webhook_handler(path: str, request: Request):
    """A single endpoint to catch all status webhooks from Vapi for logging purposes."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    print(f"ℹ️ Received webhook on '/webhooks/{path}': {data}")
    return {"status": "received"}
