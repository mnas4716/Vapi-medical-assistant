# clinic_manager.py (Advanced Version - This code is correct, no changes needed)

import os
import json
import base64
import re
import gspread
import pytz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

class ClinicManager:
    def __init__(self):
        self.sheet_name = os.getenv("SHEET_NAME", "WellnessGroveClinic_Patients")
        self.calendar_id = os.getenv("CALENDAR_ID", "primary")
        self.appointment_duration = timedelta(minutes=30)
        self.clinic_tz = pytz.timezone(os.getenv("TIME_ZONE", "Australia/Sydney"))
        self.clinic_open_hour = 9
        self.clinic_close_hour = 17
        self.sheets_service, self.calendar_service = self._initialize_services()
        print(f"✅ ClinicManager initialized | Sheet: {self.sheet_name}")

    def _initialize_services(self):
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/calendar.events"]
        creds_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_b64: raise ValueError("FATAL ERROR: GOOGLE_CREDENTIALS_JSON env var not set")
        try:
            creds_dict = json.loads(base64.b64decode(creds_json_b64))
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            sheets_service = gspread.authorize(creds)
            calendar_service = build('calendar', 'v3', credentials=creds)
            return sheets_service, calendar_service
        except Exception as e:
            raise RuntimeError("Google service initialization failed") from e

    def _normalize_mobile(self, mobile_number):
        if not mobile_number: return ""
        return re.sub(r"\D", "", str(mobile_number))

    def _parse_and_localize_time(self, iso_datetime_str):
        if not iso_datetime_str: raise ValueError("dateTime cannot be null.")
        if iso_datetime_str.endswith('Z'): iso_datetime_str = iso_datetime_str[:-1] + '+00:00'
        dt_object = datetime.fromisoformat(iso_datetime_str)
        return dt_object.astimezone(self.clinic_tz) if dt_object.tzinfo else self.clinic_tz.localize(dt_object)
    
    def find_patient(self, mobile_number=None, dob=None):
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            all_records = sheet.get_all_records()
            if mobile_number:
                norm_mobile = self._normalize_mobile(mobile_number)
                for patient in all_records:
                    if self._normalize_mobile(patient.get('mobileNumber')) == norm_mobile:
                        return patient
            if dob:
                for patient in all_records:
                    if str(patient.get('dob', '')).strip() == str(dob).strip():
                        return patient
            return None
        except Exception as e:
            print(f"❌ Find patient error: {e}")
            return None
            
    def register_patient(self, details):
        try:
            if self.find_patient(mobile_number=details.get("mobileNumber"), dob=details.get("dob")):
                return False 
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            sheet.append_row([details.get('fullName', ''), details.get('dob', ''), details.get('mobileNumber', '')])
            return True
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False

    def check_availability(self, iso_datetime_str):
        """
        ADVANCED: Checks calendar for available slots. If the requested slot is
        taken, it finds up to 3 alternative slots on the same day.
        """
        try:
            requested_time = self._parse_and_localize_time(iso_datetime_str)
            if not (self.clinic_open_hour <= requested_time.hour < self.clinic_close_hour):
                return "Outside clinic hours"

            start_utc = requested_time.astimezone(pytz.utc)
            end_utc = start_utc + self.appointment_duration
            
            events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=start_utc.isoformat(), timeMax=end_utc.isoformat(), singleEvents=True, maxResults=1).execute().get("items", [])
            if not events:
                print(f"✅ Slot at {requested_time} is available.")
                return "AVAILABLE"

            print(f"⚠️ Slot at {requested_time} is booked. Searching for alternatives...")
            suggestions = []
            search_time = requested_time
            day_end = requested_time.replace(hour=self.clinic_close_hour, minute=0, second=0, microsecond=0)

            while len(suggestions) < 3 and search_time < day_end:
                search_time += self.appointment_duration
                if search_time >= day_end: break
                
                check_start_utc = search_time.astimezone(pytz.utc)
                check_end_utc = check_start_utc + self.appointment_duration
                
                check_events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=check_start_utc.isoformat(), timeMax=check_end_utc.isoformat(), singleEvents=True, maxResults=1).execute().get("items", [])
                if not check_events:
                    suggestions.append(search_time.strftime("%-I:%M %p"))
            
            if suggestions:
                response_string = f"Suggestions: {', '.join(suggestions)}"
                print(f"✅ Found alternatives: {response_string}")
                return response_string
            else:
                print("❌ No alternative slots found for the rest of the day.")
                return "No other slots available today"
        except Exception as e:
            print(f"❌ Availability check error: {e}")
            return "Error checking calendar"
    
    def schedule_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient: return None
            start_time = self._parse_and_localize_time(iso_datetime_str)
            event = {
                "summary": f"Appointment: {patient.get('fullName', 'Unknown')}",
                "description": f"Patient verified via system. Mobile: {patient.get('mobileNumber')}",
                "start": {"dateTime": start_time.isoformat(), "timeZone": str(self.clinic_tz)},
                "end": {"dateTime": (start_time + self.appointment_duration).isoformat(), "timeZone": str(self.clinic_tz)}
            }
            self.calendar_service.events().insert(calendarId=self.calendar_id, body=event).execute()
            return start_time
        except Exception as e:
            print(f"❌ Scheduling error: {e}")
            return None

    def cancel_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient: return False
            target_time = self._parse_and_localize_time(iso_datetime_str)
            start_utc = (target_time - timedelta(seconds=10)).astimezone(pytz.utc)
            end_utc = (target_time + timedelta(seconds=10)).astimezone(pytz.utc)
            events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=start_utc.isoformat(), timeMax=end_utc.isoformat(), singleEvents=True).execute().get("items", [])
            for event in events:
                event_start = self._parse_and_localize_time(event['start'].get('dateTime'))
                if patient.get("fullName", "").lower() in event.get("summary", "").lower() and event_start == target_time:
                    self.calendar_service.events().delete(calendarId=self.calendar_id, eventId=event["id"]).execute()
                    return True
            return False
        except Exception as e:
            print(f"❌ Cancellation error: {e}")
            return False
