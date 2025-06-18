@app.post("/")
async def vapi_webhook(request: Request):
    print("\n--- Incoming request ---")
    secret = os.getenv("VAPI_SECRET_KEY")
    incoming = request.headers.get("x-vapi-secret")
    print("Headers:", dict(request.headers))
    if secret and incoming != secret:
        print("❌ Secret mismatch!")
        raise HTTPException(status_code=403, detail="Forbidden: invalid secret")
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

    try:
        if fn == "findPatient":
            patient = find_patient_in_sheet(params.get("dob"), params.get("initials"))
            print("Patient found:", patient)
            return {"patientName": patient.get("fullName").split(" ")[0] if patient else "Not Found"}

        if fn == "registerNewPatient":
            status = register_patient_in_sheet(params)
            print("Register status:", status)
            return {"status": "Success" if status else "Failure"}

        if fn == "checkAvailability":
            availability = check_calendar_availability(params.get("dateTime"))
            print("Availability:", availability)
            return {"result": availability}

        if fn == "scheduleAppointment":
            name = params.get("fullName") or ctx.get("patientName")
            time = params.get("dateTime")
            reason = params.get("reason")
            confirmation = schedule_event_in_calendar(name, time, reason)
            print("Confirmation:", confirmation)
            return {"confirmationTime": confirmation.strftime("%A, %B %d at %-I:%M %p") if confirmation else "Failure"}

        if fn == "cancelAppointment":
            cancelled = cancel_appointment_in_calendar(params.get("fullName"), params.get("dateTime"))
            print("Cancelled:", cancelled)
            return {"status": "Success" if cancelled else "Not Found"}

        print("❌ Unknown function:", fn)
        return {"error": f"Unknown function: {fn}"}

    except Exception as e:
        print("❌ Exception in function:", str(e))
        return {"error": f"Exception: {str(e)}"}
