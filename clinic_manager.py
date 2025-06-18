# clinic_manager.py

import os
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# --- CONFIG ---
SHEET_NAME = "WellnessGroveClinic_Patients"
CALENDAR_ID = "primary"  # Or your full calendar email like xyz@project.iam.gserviceaccount.com
APPOINTMENT_DURATION_MINUTES = 30
CLINIC_OPEN_HOUR = 9
CLINIC_CLOSE_HOUR = 17

def get_google_services():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/calendar"
    ]

    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable not set.")

    import json, base64
    creds_dict = json.loads(base64.b64decode(creds_json))
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)

    sheets_service = gspread.authorize(creds)
    calendar_service = build('calendar', 'v3', credentials=creds)
    return sheets_service, calendar_service

def find_patient_in_sheet(dob, initials):
    try:
        sheets_service, _ = get_google_services()
        sheet = sheets_service.open(SHEET_NAME).sheet1
        all_patients = sheet.get_all_records()

        for patient in all_patients:
            name_parts = patient.get('fullName', '').split(' ')
            if len(name_parts) >= 2:
                patient_initials = f"{name_parts[0][0]}{name_parts[-1][0]}".upper()
            else:
                continue
            if patient.get('dob') == dob and patient_initials == initials.upper():
                print(f"✅ Found patient: {patient.get('fullName')}")
                return patient
        print("❌ Patient not found.")
        return None
    except Exception as e:
        print(f"❌ Error finding patient in sheet: {e}")
        return None

def register_patient_in_sheet(details):
    try:
        sheets_service, _ = get_google_services()
        sheet = sheets_service.open(SHEET_NAME).sheet1
        headers = sheet.row_values(1)
        new_row = [details.get(h, '') for h in headers]
        sheet.append_row(new_row)
        print(f"✅ Successfully registered: {details.get('fullName')}")
        return True
    except Exception as e:
        print(f"❌ Error registering patient: {e}")
        return False

def check_calendar_availability(iso_datetime_str):
    try:
        _, calendar_service = get_google_services()
        requested_time = datetime.fromisoformat(iso_datetime_str)
        if not (CLINIC_OPEN_HOUR <= requested_time.hour < CLINIC_CLOSE_HOUR):
            return "Sorry, that time is outside our clinic hours (9 AM – 5 PM)."

        time_min_iso = requested_time.isoformat() + 'Z'
        time_max_iso = (requested_time + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)).isoformat() + 'Z'

        events_result = calendar_service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            singleEvents=True
        ).execute()

        if not events_result.get('items', []):
            print(f"✅ Slot at {requested_time} is available.")
            return "AVAILABLE"

        suggestions = []
        search_time = requested_time
        day_end = requested_time.replace(hour=CLINIC_CLOSE_HOUR, minute=0, second=0)

        while len(suggestions) < 3 and search_time < day_end:
            search_time += timedelta(minutes=APPOINTMENT_DURATION_MINUTES)
            if search_time >= day_end:
                break
            next_min = search_time.isoformat() + 'Z'
            next_max = (search_time + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)).isoformat() + 'Z'
            check = calendar_service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=next_min,
                timeMax=next_max,
                singleEvents=True
            ).execute()
            if not check.get('items', []):
                suggestions.append(search_time.strftime('%-I:%M %p'))

        if suggestions:
            return f"Suggestions: {', '.join(suggestions)}"
        else:
            return "I'm sorry, no free slots found later today."
    except Exception as e:
        print(f"❌ Error checking calendar availability: {e}")
        return "There was an error checking the calendar."

def schedule_event_in_calendar(full_name, iso_datetime_str, reason):
    try:
        _, calendar_service = get_google_services()
        start_time = datetime.fromisoformat(iso_datetime_str)
        end_time = start_time + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

        event = {
            'summary': f'Appointment: {full_name}',
            'description': f'Reason: {reason}',
            'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
        }

        calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        print(f"✅ Scheduled: {full_name} at {start_time}")
        return start_time
    except Exception as e:
        print(f"❌ Error scheduling appointment: {e}")
        return None

def cancel_appointment_in_calendar(full_name, iso_datetime_str):
    try:
        _, calendar_service = get_google_services()
        target_time = datetime.fromisoformat(iso_datetime_str)
        time_min = target_time.isoformat() + 'Z'
        time_max = (target_time + timedelta(minutes=1)).isoformat() + 'Z'

        events = calendar_service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True
        ).execute().get('items', [])

        for event in events:
            if full_name.lower() in event.get('summary', '').lower():
                calendar_service.events().delete(calendarId=CALENDAR_ID, eventId=event['id']).execute()
                print(f"✅ Cancelled event for {full_name}")
                return True

        print(f"❌ No matching event found for {full_name}")
        return False
    except Exception as e:
        print(f"❌ Error cancelling appointment: {e}")
        return False
