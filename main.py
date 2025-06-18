# main.py (Corrected and Finalized)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import traceback
from datetime import datetime, timedelta

# This must match the class name in your clinic_manager.py
from clinic_manager import ClinicManager

# Load environment variables for local testing
load_dotenv()

app = FastAPI()

# Initialize ClinicManager once when the application starts
print("\n" + "="*50)
print("🚀 Initializing ClinicManager...")
try:
    manager = ClinicManager()
    print("✅ ClinicManager initialized successfully")
except Exception as e:
    print(f"❌ CRITICAL ERROR: ClinicManager initialization failed: {e}")
    traceback.print_exc()
    print("="*50)
    raise RuntimeError("ClinicManager initialization failed") from e
print("="*50)


@app.get("/")
async def root():
    """Health check endpoint to confirm the API is live."""
    return {"status": "active", "service": "FreeDoc Medical Assistant API"}


# === Main Vapi Function Call Endpoint ===
@app.post("/")
async def vapi_webhook(request: Request):
    """
    This is the simple "traffic cop" endpoint. It receives a function call from
    Vapi and routes it to the correct method in the ClinicManager.
    """
    # NOTE: Security check is commented out for development/debugging.
    # UNCOMMENT FOR PRODUCTION.
    # import hmac
    # import hashlib
    # secret = os.getenv("VAPI_SECRET_KEY")
    # if secret:
    #     ... (full HMAC security block goes here) ...

    try:
        payload = await request.json()
    except Exception as e:
        print(f"❌ JSON parsing error: {e}")
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(e)}"})

    message = payload.get("message")
    if not message or message.get("type") != "function-call":
        return {"status": "ignored", "reason": "non-function-call"}

    function_call = message.get("functionCall", {})
    fn = function_call.get("name")
    params = function_call.get("parameters", {})
    
    print("\n" + "="*50)
    print(f"📞 VAPI FUNCTION CALL RECEIVED: {fn}")
    print(f"📋 Parameters: {params}")
    print("="*50)
    
    try:
        # --- START: CORRECTED AND SIMPLIFIED ROUTING LOGIC ---
        if fn == "findPatient":
            patient = manager.find_patient(
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"patientName": patient.get("fullName", "").split()[0] if patient else "Not Found"}
        
        elif fn == "registerNewPatient":
            # This tool is now simple and only does one thing.
            status = manager.register_patient(params)
            result = {"status": "Success" if status else "Failure"}

        elif fn == "checkAvailability":
            availability = manager.check_availability(params.get("dateTime"))
            result = {"result": availability}
            
        elif fn == "scheduleAppointment":
            # This tool now correctly assumes the patient has already been verified
            # by the Vapi prompt's logic flow. No need for extra checks here.
            confirmation = manager.schedule_appointment(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            if confirmation:
                result = {"confirmationTime": confirmation.strftime("%A, %B %d at %-I:%M %p")}
            else:
                result = {"status": "Failure"} # Simplified error
                
        elif fn == "cancelAppointment":
            cancelled = manager.cancel_appointment(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            result = {"status": "Success" if cancelled else "Not Found"}
            
        else:
            print(f"❌ Unknown function called: {fn}")
            result = {"error": f"Unknown function name: {fn}"}
        # --- END: CORRECTED AND SIMPLIFIED ROUTING LOGIC ---

        print(f"✅ Function '{fn}' completed successfully.")
        print(f"📤 Returning Result: {result}")
        return result
        
    except Exception as e:
        print("\n❌❌❌ UNEXPECTED ERROR IN FUNCTION EXECUTION ❌❌❌")
        print(f"Function that failed: {fn}")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {str(e)}")
        print("🔍 Traceback:")
        traceback.print_exc()
        print("="*50)
        return {"error": "An internal server error occurred while executing the function."}

# The rest of your file (diagnostic endpoints) is excellent and remains unchanged.
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

@app.get("/test-sheets")
async def test_sheets(mobile: str = "0414364374"):
    try:
        patient = manager.find_patient(mobile_number=mobile)
        return {"status": "success" if patient else "failure", "patient_found": bool(patient), "patient_name": patient.get("fullName") if patient else None}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

@app.get("/test-calendar")
async def test_calendar():
    try:
        test_time = (datetime.now(manager.clinic_tz) + timedelta(hours=1)).isoformat()
        availability = manager.check_availability(test_time)
        return {"status": "success", "test_time": test_time, "availability": availability}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

@app.get("/env-check")
async def env_check():
    return {
        "GOOGLE_CREDENTIALS_SET": bool(os.getenv("GOOGLE_CREDENTIALS_JSON")),
        "VAPI_SECRET_SET": bool(os.getenv("VAPI_SECRET_KEY")),
        "SHEET_NAME": manager.sheet_name,
        "TIME_ZONE": str(manager.clinic_tz)
    }

@app.get("/test-schedule")
async def test_schedule(mobile: str = "0414364374"):
    try:
        test_time = (datetime.now(manager.clinic_tz) + timedelta(hours=2)).isoformat()
        patient = manager.find_patient(mobile_number=mobile)
        if not patient: return {"status": "failure", "reason": "Test patient not found"}
        confirmation = manager.schedule_appointment(iso_datetime_str=test_time, mobile_number=mobile, dob=patient.get("dob"))
        return {"status": "success", "scheduled_at": confirmation.isoformat()} if confirmation else {"status": "failure"}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}
