from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import traceback

# Import your manager class or direct functions
from clinic_manager import ClinicManager
# If you want to support direct function calls as fallback:
# from clinic_manager import (
#     find_patient_in_sheet,
#     register_patient_in_sheet,
#     check_calendar_availability,
#     schedule_event_in_calendar,
#     cancel_appointment_in_calendar
# )

load_dotenv()

app = FastAPI()

print("🚀 Initializing ClinicManager...")
manager = ClinicManager()
print("✅ ClinicManager is ready.")

@app.get("/")
async def root():
    return {"message": "API is live and running."}

# === Main Vapi Function Call Endpoint ===
@app.post("/")
async def vapi_webhook(request: Request):
    print("\n--- Incoming request ---")
    # === Security Block (toggle on/off as needed) ===
    secret = os.getenv("VAPI_SECRET_KEY")
    incoming = request.headers.get("x-vapi-secret")
    print("Headers:", dict(request.headers))
    if secret and incoming != secret:
        print("❌ Secret mismatch!")
        raise HTTPException(status_code=403, detail="Forbidden: invalid secret")

    # === Robust JSON Body Parsing ===
    try:
        payload = await request.json()
        print("Payload:", payload)
    except Exception as e:
        print("❌ JSON decode error:", str(e))
        return JSONResponse(status_code=400, content={"error": str(e)})

    message = payload.get("message")
    print("Message:", message)
    if not message or message.get("type") != "function-call":
        print("❌ Ignored non-function-call")
        return {"message": "Ignored non-function-call"}

    fn = message.get("functionCall", {}).get("name")
    params = message.get("functionCall", {}).get("parameters", {})
    ctx = message.get("context", {})

    print("Function:", fn)
    print("Parameters:", params)
    print("Context:", ctx)

    # === MAIN FUNCTION ROUTING ===
    try:
        # Use ClinicManager object for all logic
        if fn == "findPatient":
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

# === Optional: /agent endpoint for Vapi (same logic as "/") ===
@app.post("/agent")
async def vapi_agent(request: Request):
    return await vapi_webhook(request)

# === Catch-All for Vapi Webhooks (empty-body safe) ===
@app.post("/webhooks/{path:path}")
async def generic_webhook_handler(path: str, request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print(f"ℹ️ Received webhook on '/webhooks/{path}': {data}")
    return {"status": "received"}
