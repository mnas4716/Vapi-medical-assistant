from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import os
from datetime import datetime

from clinic_manager import (
    find_patient_in_sheet,
    register_patient_in_sheet,
    check_calendar_availability,
    schedule_event_in_calendar,
    cancel_appointment_in_calendar
)

app = FastAPI()

# Optional: use environment variable for secret verification
VAPI_SECRET_KEY = os.getenv("VAPI_SECRET_KEY")


@app.get("/")
async def root():
    return {"message": "API is live"}


@app.post("/")
async def vapi_webhook(request: Request):
    # Verify secret header if it's set
    if VAPI_SECRET_KEY:
        incoming_secret = request.headers.get("x-vapi-secret")
        if incoming_secret != VAPI_SECRET_KEY:
            raise HTTPException(status_code=403, detail="Forbidden: invalid secret")

    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse(
            content={"error": "Invalid JSON payload", "details": str(e)},
            status_code=400
        )

    message = payload.get("message")
    if not message or message.get("type") != "function-call":
        return {"message": "Ignored non-function-call"}

    function_call = message.get("functionCall", {})
    function_name = function_call.get("name")
    parameters = function_call.get("parameters", {}) or {}
    context = message.get("context", {}) or {}

    print(f"[Vapi] Function: {function_name} | Parameters: {parameters}")

    result = {}

    try:
        if function_name == "findPatient":
            dob = parameters.get("dob")
            initials = parameters.get("initials")
            patient = find_patient_in_sheet(dob, initials)
            result = {"patientName": patient.get("fullName").split(" ")[0]} if patient else {"patientName": "Not Found"}

        elif function_name == "registerNewPatient":
            success = register_patient_in_sheet(parameters)
            result = {"status": "Success" if success else "Failure"}

        elif function_name == "checkAvailability":
            availability = check_calendar_availability(parameters.get("dateTime"))
            result = {"result": availability}

        elif function_name == "scheduleAppointment":
            full_name = parameters.get("fullName") or context.get("patientName")
            dt = parameters.get("dateTime")
            reason = parameters.get("reason")
            confirmed = schedule_event_in_calendar(full_name, dt, reason)
            result = {
                "confirmationTime": confirmed.strftime("%A, %B %d at %-I:%M %p")
            } if confirmed else {"confirmationTime": "Failure"}

        elif function_name == "cancelAppointment":
            cancelled = cancel_appointment_in_calendar(parameters.get("fullName"), parameters.get("dateTime"))
            result = {"status": "Success" if cancelled else "Not Found"}

        else:
            result = {"error": f"Unknown function: {function_name}"}

    except Exception as e:
        result = {"error": f"Exception during processing: {str(e)}"}

    return JSONResponse(content=result)
