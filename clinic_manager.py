# clinic_manager.py (Corrected with FULL Scopes)

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
        """Set up authenticated Google service objects with full required scopes."""
        # --- START: CRITICAL FIX ---
        # We need to add the Google Drive scope for gspread to reliably find and access sheets.
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/drive" # <-- THIS IS THE NEW, REQUIRED LINE
        ]
        # --- END: CRITICAL FIX ---

        creds_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_b64:
            raise ValueError("FATAL ERROR: GOOGLE_CREDENTIALS_JSON environment variable not set")
        
        try:
            creds_dict = json.loads(base64.b64decode(creds_json_b64))
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            sheets_service = gspread.authorize(creds)
            calendar_service = build('calendar', 'v3', credentials=creds)
            return sheets_service, calendar_service
        except Exception as e:
            print(f"❌ Service initialization failed: {e}")
            raise RuntimeError("Google service initialization failed") from e
    
    # The rest of your file is EXCELLENT and requires no changes.
    # I am including it here for completeness so you can copy-paste the whole file.

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
                        print(f"✅ Found patient by mobile: {patient.get('fullName')}")
                        return patient
            if dob:
                for patient in all_records:
                    if str(patient.get('dob', '')).strip() == str(dob).strip():
                        print(f"✅ Found patient by DOB: {patient.get('fullName')}")
                        return patient
            print(f"❌ Patient not found | Mobile: {mobile_number} | DOB: {dob}")
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
        try:
            req_time = self._parse_and_localize_time(iso_datetime_str)
            if not (self.clinic_open_hour <= req_time.hour < self.clinic_close_hour):
                return "Outside clinic hours"
            start_utc = req_time.astimezone(pytz.utc)
            end_utc = start_utc + self.appointment_duration
            events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=start_utc.isoformat(), timeMax=end_utc.isoformat(), singleEvents=True, maxResults=1).execute().get("items", [])
            if not events: return "AVAILABLE"
            suggestions = []
            search_time = req_time
            eod = req_time.replace(hour=self.clinic_close_hour, minute=0, second=0)
            while len(suggestions) < 3 and search_time < eod:
                search_time += self.appointment_duration
                if search_time >= eod: break
                check_start = search_time.astimezone(pytz.utc)
                check_end = check_start + self.appointment_duration
                check_events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=check_start.isoformat(), timeMax=check_end.isoformat(), singleEvents=True, maxResults=1).execute().get("items", [])
                if not check_events: suggestions.append(search_time.strftime("%-I:%M %p"))
            return f"Suggestions: {', '.join(suggestions)}" if suggestions else "No other slots available"
        except Exception as e:
            return f"Error checking calendar: {e}"
    
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
