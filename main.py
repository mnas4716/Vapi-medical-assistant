# main.py (Corrected with Standardized String Returns)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse # Import PlainTextResponse
from dotenv import load_dotenv
import os
import traceback
import hmac
import hashlib
from datetime import datetime, timedelta

from clinic_manager import ClinicManager

# Load environment variables
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
    print("="*50)
    raise RuntimeError("ClinicManager initialization failed") from e
print("="*50)


@app.get("/")
async def root():
    return {"status": "active", "service": "FreeDoc Medical Assistant API"}


@app.post("/")
async def vapi_webhook(request: Request):
    # Note: Security check is commented out for development
    # try...except blocks for payload parsing...

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
    
    try:
        # --- START: CORRECTED RETURN LOGIC ---
        if fn == "findPatient":
            patient = manager.find_patient(mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            # Return a simple string, which the AI will use to get the first name.
            return PlainTextResponse(content=patient.get("fullName") if patient else "Not Found")
        
        elif fn == "registerNewPatient":
            status = manager.register_patient(params)
            return PlainTextResponse(content="Success" if status else "Failure")

        elif fn == "checkAvailability":
            availability = manager.check_availability(params.get("dateTime"))
            # This already returns a string ("AVAILABLE" or "Suggestions: ..."), which is perfect.
            return PlainTextResponse(content=availability)
            
        elif fn == "scheduleAppointment":
            confirmation = manager.schedule_appointment(iso_datetime_str=params.get("dateTime"), mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            # Return the confirmation time directly as a string.
            return PlainTextResponse(content=confirmation.strftime("%A, %B %d at %-I:%M %p") if confirmation else "Failure")
                
        elif fn == "cancelAppointment":
            cancelled = manager.cancel_appointment(iso_datetime_str=params.get("dateTime"), mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            return PlainTextResponse(content="Success" if cancelled else "Not Found")
            
        else:
            print(f"❌ Unknown function called: {fn}")
            return PlainTextResponse(content=f"Error: Unknown function name '{fn}'", status_code=400)
        # --- END: CORRECTED RETURN LOGIC ---
        
    except Exception as e:
        print("\n❌❌❌ UNEXPECTED ERROR IN FUNCTION EXECUTION ❌❌❌")
        traceback.print_exc()
        return PlainTextResponse(content=f"Error: An internal server error occurred while executing {fn}.", status_code=500)

# The rest of your file (diagnostic endpoints etc.) is excellent and remains unchanged.
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
    # ... your existing env_check code ...
    return {"GOOGLE_CREDENTIALS_SET": bool(os.getenv("GOOGLE_CREDENTIALS_JSON")), "VAPI_SECRET_SET": bool(os.getenv("VAPI_SECRET_KEY")), "SHEET_NAME": manager.sheet_name, "TIME_ZONE": str(manager.clinic_tz)}

@app.get("/test-schedule")
async def test_schedule(mobile: str = "0414364374"):
    # ... your existing test_schedule code ...
    try:
        test_time = (datetime.now(manager.clinic_tz) + timedelta(hours=2)).isoformat()
        patient = manager.find_patient(mobile_number=mobile)
        if not patient: return {"status": "failure", "reason": "Test patient not found"}
        confirmation = manager.schedule_appointment(iso_datetime_str=test_time, mobile_number=mobile, dob=patient.get("dob"))
        return {"status": "success", "scheduled_at": confirmation.isoformat()} if confirmation else {"status": "failure"}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}
