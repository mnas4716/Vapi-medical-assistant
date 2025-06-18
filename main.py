# main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import traceback
# import hmac  # --- Temporarily commented out for development
# import hashlib # --- Temporarily commented out for development
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
    print("Application cannot start without Google services")
    print("="*50)
    raise RuntimeError("ClinicManager initialization failed") from e
print("="*50)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "active",
        "service": "Medical Assistant API",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/")
async def vapi_webhook(request: Request):
    """
    Main endpoint for Vapi function calls
    Handles authentication and routes to appropriate functions
    """
    # --- START: HMAC SECURITY BLOCK (TEMPORARILY COMMENTED OUT FOR DEV) ---
    # secret = os.getenv("VAPI_SECRET_KEY")
    # if secret:
    #     signature = request.headers.get("x-vapi-signature")
    #     if not signature:
    #         print("❌ Security Error: Missing x-vapi-signature header")
    #         raise HTTPException(status_code=401, detail="Missing signature")
        
    #     body = await request.body()
    #     expected_signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
    #     if not hmac.compare_digest(expected_signature, signature):
    #         print("❌ Security Error: Invalid signature")
    #         raise HTTPException(status_code=401, detail="Invalid signature")
    # --- END: HMAC SECURITY BLOCK ---

    try:
        payload = await request.json()
    except Exception as e:
        print(f"❌ JSON parsing error: {e}")
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(e)}"})

    message = payload.get("message")
    if not message or message.get("type") != "function-call":
        print("⚠️ Ignored non-function-call message")
        return {"status": "ignored", "reason": "non-function-call"}

    # Extract function details
    function_call = message.get("functionCall", {})
    fn = function_call.get("name")
    params = function_call.get("parameters", {})
    
    print("\n" + "="*50)
    print(f"📞 VAPI FUNCTION CALL: {fn}")
    print(f"📋 Parameters: {params}")
    print("="*50)
    
    try:
        # Route to appropriate function
        if fn == "findPatient":
            patient = manager.find_patient(mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            result = {"patientName": patient.get("fullName", "Not Found").split()[0] if patient else "Not Found"}
            
        elif fn == "registerNewPatient":
            status = manager.register_patient(params)
            result = {"status": "Success" if status else "Failure"}
            
        elif fn == "checkAvailability":
            availability = manager.check_availability(params.get("dateTime"))
            result = {"result": availability}
            
        elif fn == "scheduleAppointment":
            confirmation = manager.schedule_appointment(iso_datetime_str=params.get("dateTime"), mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            if confirmation:
                result = {"confirmationTime": confirmation.strftime("%A, %B %d at %-I:%M %p")}
            else:
                result = {"status": "Failure", "reason": "Scheduling failed"}
                
        elif fn == "cancelAppointment":
            cancelled = manager.cancel_appointment(iso_datetime_str=params.get("dateTime"), mobile_number=params.get("mobileNumber"), dob=params.get("dob"))
            result = {"status": "Success" if cancelled else "Not Found"}
            
        else:
            print(f"❌ Unknown function called: {fn}")
            result = {"error": f"Unknown function: {fn}"}
        
        print(f"✅ Function completed: {fn}")
        print(f"📤 Result: {result}")
        return result
        
    except Exception as e:
        print("\n❌❌❌ UNEXPECTED ERROR ❌❌❌")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {str(e)}")
        print("🔍 Traceback:")
        traceback.print_exc()
        print("="*50)
        
        return {"error": "Internal server error", "details": str(e), "function": fn}

# The rest of your file (diagnostic endpoints etc.) is perfect and does not need to be changed.
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

@app.get("/test-sheets")
async def test_sheets(mobile: str = "0414364374"):
    try:
        print(f"🔍 Testing Sheets with mobile: {mobile}")
        patient = manager.find_patient(mobile_number=mobile)
        return {"status": "success" if patient else "failure", "patient_found": bool(patient), "patient_name": patient.get("fullName") if patient else None}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

@app.get("/test-calendar")
async def test_calendar():
    try:
        test_time = (datetime.now(manager.clinic_tz) + timedelta(hours=1)).isoformat()
        print(f"🔍 Testing Calendar with time: {test_time}")
        availability = manager.check_availability(test_time)
        return {"status": "success", "test_time": test_time, "availability": availability}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

@app.get("/env-check")
async def env_check():
    return {"GOOGLE_CREDENTIALS_SET": bool(os.getenv("GOOGLE_CREDENTIALS_JSON")), "CALENDAR_ID": os.getenv("CALENDAR_ID"), "VAPI_SECRET_SET": bool(os.getenv("VAPI_SECRET_KEY")), "SHEET_NAME": manager.sheet_name, "TIME_ZONE": str(manager.clinic_tz), "TEST_MOBILE_NUMBER": os.getenv("TEST_MOBILE_NUMBER", "Not set")}

@app.get("/test-schedule")
async def test_schedule():
    try:
        test_mobile = os.getenv("TEST_MOBILE_NUMBER", "0414364374")
        test_time = (datetime.now(manager.clinic_tz) + timedelta(hours=2)).isoformat()
        print("🔍 Testing full scheduling workflow:")
        print(f"1. Finding patient with mobile: {test_mobile}")
        patient = manager.find_patient(mobile_number=test_mobile)
        if not patient: return {"status": "failure", "reason": "Patient not found"}
        print(f"2. Scheduling appointment at {test_time}")
        confirmation = manager.schedule_appointment(iso_datetime_str=test_time, mobile_number=test_mobile, dob=patient.get("dob", ""))
        if confirmation: return {"status": "success", "patient": patient.get("fullName"), "scheduled_time": confirmation.isoformat()}
        return {"status": "failure", "reason": "Scheduling failed"}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}
