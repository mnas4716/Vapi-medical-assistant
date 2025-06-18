# main.py (Final Robust Version)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import traceback
from datetime import datetime
# Note: hmac/hashlib are commented out if you're still testing without security
# import hmac
# import hashlib

from clinic_manager import ClinicManager

load_dotenv()
app = FastAPI()

# Initialize ClinicManager
print("\n" + "="*50)
print("🚀 Initializing ClinicManager...")
try:
    manager = ClinicManager()
    print("✅ ClinicManager initialized successfully")
except Exception as e:
    print(f"❌ CRITICAL ERROR: ClinicManager initialization failed: {e}")
    traceback.print_exc()
    raise RuntimeError("ClinicManager initialization failed") from e
print("="*50)


# --- DIagnostic Endpoints (remain unchanged) ---
@app.get("/")
async def root():
    return {"status": "active", "service": "FreeDoc Medical Assistant API"}
# ... (your other /test-* and /env-check endpoints are perfect, keep them) ...


# === Main Vapi Function Call Endpoint ===
@app.post("/")
async def vapi_webhook(request: Request):
    # Security block is commented out for dev, you can re-enable later
    # ...

    try:
        payload = await request.json()
    except Exception as e:
        print(f"❌ JSON parsing error: {e}")
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(e)}"})

    message = payload.get("message")
    if not message or message.get("type") != "function-call":
        return JSONResponse(content={"status": "ignored", "reason": "non-function-call"})

    function_call = message.get("functionCall", {})
    fn = function_call.get("name")
    params = function_call.get("parameters", {})
    
    print("\n" + "="*50)
    print(f"📞 VAPI FUNCTION CALL RECEIVED: {fn}")
    print(f"📋 Parameters: {params}")
    print("="*50)
    
    result = None
    try:
        # --- START: ROBUST ROUTING & RESPONSE LOGIC ---
        if fn == "findPatient":
            patient = manager.find_patient(mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            # If a patient is found, result is their name. If not, it's "Not Found".
            result = patient.get("fullName") if patient else "Not Found"
        
        elif fn == "registerNewPatient":
            status = manager.register_patient(params)
            result = "Success" if status else "Failure"

        elif fn == "checkAvailability":
            # This already returns a string, which is perfect.
            result = manager.check_availability(params.get("dateTime"))
            
        elif fn == "scheduleAppointment":
            confirmation = manager.schedule_appointment(iso_datetime_str=params.get("dateTime"), mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            # The result is the formatted time string, or "Failure".
            result = confirmation.strftime("%A, %B %d at %-I:%M %p") if confirmation else "Failure"
                
        elif fn == "cancelAppointment":
            cancelled = manager.cancel_appointment(iso_datetime_str=params.get("dateTime"), mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            result = "Success" if cancelled else "Not Found"
            
        else:
            print(f"❌ Unknown function called: {fn}")
            result = f"Error: Unknown function name '{fn}'"

        # --- END: ROBUST ROUTING & RESPONSE LOGIC ---

        print(f"✅ Function '{fn}' completed.")
        print(f"📤 Preparing to send result to Vapi: '{result}'")
        # Return the result in a format Vapi is guaranteed to understand.
        return JSONResponse(content={"result": result})
        
    except Exception as e:
        print("\n❌❌❌ UNEXPECTED ERROR IN FUNCTION EXECUTION ❌❌❌")
        traceback.print_exc()
        # Return a clear error message in the correct format
        return JSONResponse(content={"result": f"Error: An internal server error occurred."})

# The rest of your main.py file...
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

# ... (Insert your excellent diagnostic endpoints here: /test-sheets, /test-calendar, etc.) ...
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
    return {"GOOGLE_CREDENTIALS_SET": bool(os.getenv("GOOGLE_CREDENTIALS_JSON")), "VAPI_SECRET_SET": bool(os.getenv("VAPI_SECRET_KEY")), "SHEET_NAME": manager.sheet_name, "TIME_ZONE": str(manager.clinic_tz), "CALENDAR_ID": os.getenv("CALENDAR_ID"), "TEST_MOBILE_NUMBER": os.getenv("TEST_MOBILE_NUMBER", "Not set")}

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
