import os
import json
import base64
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# --- CONFIG ---
SHEET_NAME = "WellnessGroveClinic_Patients"
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")
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
    creds_dict = json.loads(base64.b64decode(creds_json))
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    sheets_service = gspread.authorize(creds)
    calendar_service = build('calendar', 'v3', credentials=creds)
    return sheets_service, calendar_service

def find_patient_in_sheet(mobile_number=None, dob=None):
    try:
        sheets_service, _ = get_google_services()
        sheet = sheets_service.open(SHEET_NAME).sheet1
        all_patients = sheet.get_all_records()

        if mobile_number:
            for patient in all_patients:
                if str(patient.get('mobileNumber', '')).strip() == str(mobile_number).strip():
                    print(f"\u2705 Found patient by mobile: {patient.get('fullName')}")
                    return patient

        if dob:
            for patient in all_patients:
                if str(patient.get('dob', '')).strip() == str(dob).strip():
                    print(f"\u2705 Found patient by DOB: {patient.get('fullName')}")
                    return patient

        print("\u274C Patient not found by mobile or DOB.")
        return None
    except Exception as e:
        print(f"\u274C Error finding patient in sheet: {e}")
        return None

def register_patient_in_sheet(details):
    try:
        sheets_service, _ = get_google_services()
        sheet = sheets_service.open(SHEET_NAME).sheet1
        headers = sheet.row_values(1)
        new_row = [details.get(h, '') for h in headers]
        sheet.append_row(new_row)
        print(f"\u2705 Successfully registered: {details.get('fullName')}")
        return True
    except Exception as e:
        print(f"\u274C Error registering patient: {e}")
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
            print(f"\u2705 Slot at {requested_time} is available.")
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
        print(f"\u274C Error checking calendar availability: {e}")
        return "There was an error checking the calendar."

def schedule_event_in_calendar(mobile_number=None, dob=None, full_name=None, iso_datetime_str=None, reason=None):
    try:
        # Try to look up patient details if not given
        patient = None
        if not full_name and (mobile_number or dob):
            patient = find_patient_in_sheet(mobile_number, dob)
            if patient:
                full_name = patient.get('fullName')
        elif full_name:
            patient = {"fullName": full_name}

        if not (full_name and iso_datetime_str):
            return None

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
        print(f"\u2705 Scheduled: {full_name} at {start_time}")
        return start_time
    except Exception as e:
        print(f"\u274C Error scheduling appointment: {e}")
        return None

def cancel_appointment_in_calendar(mobile_number=None, dob=None, full_name=None, iso_datetime_str=None):
    try:
        # Try to look up patient details if not given
        patient = None
        if not full_name and (mobile_number or dob):
            patient = find_patient_in_sheet(mobile_number, dob)
            if patient:
                full_name = patient.get('fullName')
        elif full_name:
            patient = {"fullName": full_name}

        if not (full_name and iso_datetime_str):
            return False

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
                print(f"\u2705 Cancelled event for {full_name}")
                return True

        print(f"\u274C No matching event found for {full_name}")
        return False
    except Exception as e:
        print(f"\u274C Error cancelling appointment: {e}")
        return False
