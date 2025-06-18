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
    ctx = message.get("context", {})

    try:
        if fn == "findPatient":
            patient = find_patient_in_sheet(
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            return {"patientName": patient.get("fullName") if patient else "Not Found"}

        if fn == "registerNewPatient":
            status = register_patient_in_sheet(params)
            return {"status": "Success" if status else "Failure"}

        if fn == "checkAvailability":
            result = check_calendar_availability(
                params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            return {"result": result}

        if fn == "scheduleAppointment":
            confirmation = schedule_event_in_calendar(
                params.get("dateTime"),
                params.get("reason"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            return {
                "confirmationTime": confirmation.strftime("%A, %B %d at %-I:%M %p") if confirmation else "Failure"
            }

        if fn == "cancelAppointment":
            cancelled = cancel_appointment_in_calendar(
                params.get("dateTime"),
                mobile_number=params.get("mobileNumber"),
                dob=params.get("dob")
            )
            return {"status": "Success" if cancelled else "Not Found"}

        return {"error": f"Unknown function: {fn}"}

    except Exception as e:
        return {"error": f"Exception: {str(e)}"}

# === Optional: /agent endpoint for Vapi (same logic as "/") ===
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

# === Vapi Webhook Endpoints (empty body safe) ===
@app.post("/webhooks/status-update")
async def status_update(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print("✅ Received status-update:", data)
    return {"status": "received"}

@app.post("/webhooks/speech-update")
async def speech_update(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print("✅ Received speech-update:", data)
    return {"status": "received"}

@app.post("/webhooks/conversation-update")
async def conversation_update(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print("✅ Received conversation-update:", data)
    return {"status": "received"}
