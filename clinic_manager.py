# clinic_manager.py

import os
import json
import base64
import gspread
import pytz # New import for timezone handling
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

class ClinicManager:
    """Manages all interactions with Google Sheets (patient data) and Google Calendar (appointments)."""

    def __init__(self):
        """Initializes the manager, configuration, and services ONCE."""
        # --- CONFIGURATION ---
        self.sheet_name = "WellnessGroveClinic_Patients" # Or your actual sheet name
        self.calendar_id = os.getenv("CALENDAR_ID", "primary")
        self.appointment_duration = timedelta(minutes=30)
        self.clinic_tz = pytz.timezone('Australia/Sydney') # CRITICAL: Set to your clinic's timezone
        self.clinic_open_hour = 9
        self.clinic_close_hour = 17
        
        # --- INITIALIZE SERVICES ---
        # This prevents re-authenticating on every single function call.
        self.sheets_service, self.calendar_service = self._initialize_services()
        print("✅ ClinicManager initialized and services are ready.")

    def _initialize_services(self):
        """Private helper to set up authenticated Google service objects."""
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/calendar"
        ]
        creds_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_b64:
            raise ValueError("FATAL ERROR: GOOGLE_CREDENTIALS_JSON environment variable not set.")
        
        creds_dict = json.loads(base64.b64decode(creds_json_b64))
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        
        sheets_service = gspread.authorize(creds)
        calendar_service = build('calendar', 'v3', credentials=creds)
        return sheets_service, calendar_service

    def _parse_and_localize_time(self, iso_datetime_str):
        """Parses an ISO string and makes it timezone-aware."""
        if iso_datetime_str.endswith('Z'):
             iso_datetime_str = iso_datetime_str[:-1] + '+00:00'
        # Convert the naive datetime object from isoformat() to a timezone-aware one
        dt_object = datetime.fromisoformat(iso_datetime_str)
        return dt_object.astimezone(self.clinic_tz)

    def find_patient(self, mobile_number=None, dob=None):
        """MORE EFFICIENT: Finds a patient using gspread's find method."""
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            cell = None
            if mobile_number:
                cell = sheet.find(str(mobile_number).strip(), in_column=6) # Assuming mobileNumber is in column F
            if not cell and dob:
                cell = sheet.find(str(dob).strip(), in_column=2) # Assuming dob is in column B
            
            if cell:
                patient_data = sheet.get_all_records()[cell.row - 2] # -2 because get_all_records is 0-indexed and sheet is 1-indexed with a header
                print(f"✅ Found patient: {patient_data.get('fullName')}")
                return patient_data
            
            print("❌ Patient not found.")
            return None
        except Exception as e:
            print(f"❌ Error in find_patient: {e}")
            return None

    def register_patient(self, details):
        """IMPROVEMENT: Prevents creating duplicate patients."""
        # First, check if patient already exists
        existing_patient = self.find_patient(mobile_number=details.get("mobileNumber"), dob=details.get("dob"))
        if existing_patient:
            print(f"❌ Attempted to register a duplicate patient: {existing_patient.get('fullName')}")
            # Optionally, you could return a specific message here
            return False # Indicate failure due to duplication

        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            headers = sheet.row_values(1)
            new_row = [details.get(h, '') for h in headers]
            sheet.append_row(new_row)
            print(f"✅ Successfully registered new patient: {details.get('fullName')}")
            return True
        except Exception as e:
            print(f"❌ Error in register_patient: {e}")
            return False

    def check_availability(self, iso_datetime_str):
        """TIMEZONE-AWARE: Checks calendar for available slots."""
        try:
            requested_time = self._parse_and_localize_time(iso_datetime_str)

            if not (self.clinic_open_hour <= requested_time.hour < self.clinic_close_hour):
                return "Sorry, that time is outside our clinic hours (9 AM – 5 PM)."

            start_utc = requested_time.astimezone(pytz.utc)
            end_utc = start_utc + self.appointment_duration
            
            events = self.calendar_service.events().list(
                calendarId=self.calendar_id, 
                timeMin=start_utc.isoformat(), 
                timeMax=end_utc.isoformat(), 
                singleEvents=True
            ).execute().get('items', [])

            if not events:
                print(f"✅ Slot at {requested_time} is available.")
                return "AVAILABLE"
            
            # Find next suggestions
            suggestions = []
            search_time = requested_time
            day_end_local = requested_time.replace(hour=self.clinic_close_hour, minute=0, second=0)

            while len(suggestions) < 3 and search_time < day_end_local:
                search_time += self.appointment_duration
                if search_time >= day_end_local: break
                
                check_start_utc = search_time.astimezone(pytz.utc)
                check_end_utc = check_start_utc + self.appointment_duration
                
                check_events = self.calendar_service.events().list(
                    calendarId=self.calendar_id, 
                    timeMin=check_start_utc.isoformat(), 
                    timeMax=check_end_utc.isoformat(), 
                    singleEvents=True
                ).execute().get('items', [])

                if not check_events:
                    suggestions.append(search_time.strftime('%-I:%M %p'))

            return f"Suggestions: {', '.join(suggestions)}" if suggestions else "I'm sorry, no free slots found later today."
        except Exception as e:
            print(f"❌ Error in check_availability: {e}")
            return "There was an error checking the calendar."

    def schedule_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        """TIMEZONE-AWARE: Schedules appointment for a verified patient."""
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient: return None
            
            start_time_local = self._parse_and_localize_time(iso_datetime_str)
            end_time_local = start_time_local + self.appointment_duration
            
            event = {
                'summary': f'Appointment: {patient.get("fullName", "Unknown")}',
                'start': {'dateTime': start_time_local.isoformat(), 'timeZone': str(self.clinic_tz)},
                'end': {'dateTime': end_time_local.isoformat(), 'timeZone': str(self.clinic_tz)},
            }

            self.calendar_service.events().insert(calendarId=self.calendar_id, body=event).execute()
            print(f"✅ Scheduled: {patient.get('fullName', 'Unknown')} at {start_time_local}")
            return start_time_local
        except Exception as e:
            print(f"❌ Error in schedule_appointment: {e}")
            return None

    def cancel_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        """TIMEZONE-AWARE: Cancels a specific appointment for a verified patient."""
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient: return False

            target_time_local = self._parse_and_localize_time(iso_datetime_str)
            start_utc = target_time_local.astimezone(pytz.utc)
            end_utc = start_utc + timedelta(seconds=60) # Small window to find the event

            events = self.calendar_service.events().list(
                calendarId=self.calendar_id, 
                timeMin=start_utc.isoformat(), 
                timeMax=end_utc.isoformat(), 
                singleEvents=True
            ).execute().get('items', [])

            for event in events:
                if patient.get("fullName", "").lower() in event.get('summary', '').lower():
                    self.calendar_service.events().delete(calendarId=self.calendar_id, eventId=event['id']).execute()
                    print(f"✅ Cancelled event for {patient.get('fullName', 'Unknown')}")
                    return True
            
            print(f"❌ No matching event found for {patient.get('fullName', 'Unknown')}")
            return False
        except Exception as e:
            print(f"❌ Error in cancel_appointment: {e}")
            return False
