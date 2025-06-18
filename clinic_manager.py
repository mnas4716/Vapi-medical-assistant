# clinic_manager.py

import os
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# --- IMPORTANT: CONFIGURE THESE CONSTANTS ---
SHEET_NAME = "WellnessGroveClinic_Patients"
CALENDAR_ID = "primary"
APPOINTMENT_DURATION_MINUTES = 30
CLINIC_OPEN_HOUR = 9
CLINIC_CLOSE_HOUR = 17

# --- AUTHENTICATION HELPER ---
def get_google_services():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/calendar"
    ]

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")

    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    sheets_service = gspread.authorize(creds)
    calendar_service = build('calendar', 'v3', credentials=creds)

    return sheets_service, calendar_service

# --- PATIENT MANAGEMENT FUNCTIONS (GOOGLE SHEETS) ---
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
                print(f"Found patient: {patient.get('fullName')}")
                return patient

        print("Patient not found.")
        return None
    except Exception as e:
        print(f"Error finding patient in sheet: {e}")
        return None

def register_patient_in_sheet(details):
    try:
        sheets_service, _ = get_google_services()
        sheet = sheets_service.open(SHEET_NAME).sheet1
        headers = sheet.row_values(1)
        new_row = [details.get(h, '') for h in headers]

        sheet.append_row(new_row)
        print(f"Successfully registered patient: {details.get('fullName')}")
        return True
    except Exception as e:
        print(f"Error registering patient in sheet: {e}")
        return False

# --- APPOINTMENT MANAGEMENT FUNCTIONS (GOOGLE CALENDAR) ---
def check_calendar_availability(iso_datetime_str):
    try:
        _, calendar_service = get_google_services()
        requested_time = datetime.fromisoformat(iso_datetime_str.replace("Z", "+00:00"))

        if not (CLINIC_OPEN_HOUR <= requested_time.hour < CLINIC_CLOSE_HOUR):
            return "Sorry, that time is outside our clinic hours which are from 9 AM to 5 PM."

        time_min_iso = requested_time.isoformat() + 'Z'
        time_max_iso = (requested_time + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)).isoformat() + 'Z'

        events_result = calendar_service.events().list(
            calendarId=CALENDAR_ID, timeMin=time_min_iso, timeMax=time_max_iso, singleEvents=True
        ).execute()

        if not events_result.get('items', []):
            print(f"Slot at {requested_time} is available.")
            return "AVAILABLE"

        print(f"Slot at {requested_time} is booked. Finding alternatives...")
        suggestions = []
        search_time = requested_time
        day_end = requested_time.replace(hour=CLINIC_CLOSE_HOUR, minute=0, second=0)

        while len(suggestions) < 3 and search_time < day_end:
            search_time += timedelta(minutes=APPOINTMENT_DURATION_MINUTES)
            if search_time >= day_end:
                break

            next_min_iso = search_time.isoformat() + 'Z'
            next_max_iso = (search_time + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)).isoformat() + 'Z'

            check_result = calendar_service.events().list(
                calendarId=CALENDAR_ID, timeMin=next_min_iso, timeMax=next_max_iso, singleEvents=True
            ).execute()

            if not check_result.get('items', []):
                suggestions.append(search_time.strftime('%-I:%M %p'))

        if suggestions:
            return f"Suggestions: {', '.join(suggestions)}"
        else:
            return "I'm sorry, I couldn't find any other available slots on that day."

    except Exception as e:
        print(f"Calendar error: {e}")
        return "There was an error checking the calendar."

def schedule_event_in_calendar(full_name, iso_datetime_str, reason):
    try:
        _, calendar_service = get_google_services()
        start_time = datetime.fromisoformat(iso_datetime_str.replace("Z", "+00:00"))
        end_time = start_time + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

        event = {
            'summary': f'Appointment: {full_name}',
            'description': f'Reason for visit: {reason}\nPatient: {full_name}',
            'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
        }

        calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        print(f"Successfully scheduled event for {full_name} at {start_time}")
        return start_time
    except Exception as e:
        print(f"Error scheduling event in calendar: {e}")
        return None

def cancel_appointment_in_calendar(full_name, iso_datetime_str):
    try:
        _, calendar_service = get_google_services()
        target_time = datetime.fromisoformat(iso_datetime_str.replace("Z", "+00:00"))

        time_min_iso = target_time.isoformat() + 'Z'
        time_max_iso = (target_time + timedelta(minutes=1)).isoformat() + 'Z'

        events_result = calendar_service.events().list(
            calendarId=CALENDAR_ID, timeMin=time_min_iso, timeMax=time_max_iso, singleEvents=True
        ).execute()
        events = events_result.get('items', [])

        if not events:
            print(f"Cancellation failed: No event found at {target_time}")
            return False

        for event in events:
            if full_name.lower() in event.get('summary', '').lower():
                event_id = event['id']
                calendar_service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
                print(f"Successfully cancelled event {event_id} for {full_name}")
                return True

        print(f"Cancellation failed: Event found at {target_time}, but name '{full_name}' did not match.")
        return False
    except Exception as e:
        print(f"Error cancelling appointment: {e}")
        return False
