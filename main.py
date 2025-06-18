# main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
from clinic_manager import (
    find_patient_in_sheet,
    register_patient_in_sheet,
    check_calendar_availability,
    schedule_event_in_calendar,
    cancel_appointment_in_calendar
)

load_dotenv()

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "API is live"}

# === Main Vapi Function Call Endpoint ===
@app.post("/")
async def vapi_webhook(request: Request):
    secret = os.getenv("VAPI_SECRET_KEY")
    incoming = request.headers.get("x-vapi-secret")
    if secret and incoming != secret:
        raise HTTPException(status_code=403, detail="Forbidden: invalid secret")

    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    message = payload.get("message")
    if not message or message.get("type") != "function-call":
        return {"message": "Ignored non-function-call"}

    fn = message.get("functionCall", {}).get("name")
    params = message.get("functionCall", {}).get("parameters", {})
    
    print(f"✅ Received function call: {fn} with parameters: {params}")

    try:
        if fn == "findPatient":
            # CORRECTED: Passes mobileNumber or dob as expected by clinic_manager.py
            patient = find_patient_in_sheet(
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            return {"patientName": patient.get("fullName").split(" ")[0] if patient else "Not Found"}

        if fn == "registerNewPatient":
            status = register_patient_in_sheet(params)
            return {"status": "Success" if status else "Failure"}

        if fn == "checkAvailability":
            # This function doesn't need patient details, so it's correct.
            availability = check_calendar_availability(params.get("dateTime"))
            return {"result": availability}

        if fn == "scheduleAppointment":
            # CORRECTED: Passes verification details instead of name/reason.
            # No longer passes 'reason'.
            confirmation = schedule_event_in_calendar(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            return {"confirmationTime": confirmation.strftime("%A, %B %d at %-I:%M %p") if confirmation else "Failure"}

        if fn == "cancelAppointment":
            # CORRECTED: Passes verification details instead of fullName.
            cancelled = cancel_appointment_in_calendar(
                iso_datetime_str=params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            return {"status": "Success" if cancelled else "Not Found"}

        return {"error": f"Unknown function: {fn}"}

    except Exception as e:
        print(f"❌ Exception during function execution: {e}")
        return {"error": f"Exception: {str(e)}"}

# === Optional: /agent endpoint for Vapi (same logic as "/") ===
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

# === Vapi Webhook Endpoints for logging (empty body safe) ===
@app.post("/webhooks/{path:path}")
async def generic_webhook(path: str, request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print(f"✅ Received webhook on /{path}: {data}")
    return {"status": "received"}
