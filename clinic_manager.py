# clinic_manager.py

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
    """Manages all interactions with Google Sheets and Google Calendar."""

    def __init__(self):
        # Configuration with environment variables
        self.sheet_name = os.getenv("SHEET_NAME", "WellnessGroveClinic_Patients")
        self.calendar_id = os.getenv("CALENDAR_ID", "primary")
        self.appointment_duration = timedelta(minutes=30)
        self.clinic_tz = pytz.timezone(os.getenv("TIME_ZONE", "Australia/Sydney"))
        self.clinic_open_hour = 9
        self.clinic_close_hour = 17
        
        # Initialize Google services
        self.sheets_service, self.calendar_service = self._initialize_services()
        print(f"✅ ClinicManager initialized | Sheet: {self.sheet_name} | Calendar: {self.calendar_id}")

    def _initialize_services(self):
        """Set up authenticated Google service objects."""
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/calendar.events"]
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

    def _normalize_mobile(self, mobile_number):
        """Standardize mobile number format for robust matching."""
        if not mobile_number: return ""
        cleaned = re.sub(r"\D", "", str(mobile_number))
        if cleaned.startswith("04") and len(cleaned) == 10: return "61" + cleaned[1:]
        if cleaned.startswith("4") and len(cleaned) == 9: return "61" + cleaned
        return cleaned

    def _parse_and_localize_time(self, iso_datetime_str):
        """Parse ISO string and convert to clinic timezone with robust error handling."""
        if not iso_datetime_str: raise ValueError("dateTime parameter cannot be null.")
        try:
            if iso_datetime_str.endswith('Z'): iso_datetime_str = iso_datetime_str[:-1] + '+00:00'
            dt_object = datetime.fromisoformat(iso_datetime_str)
            return dt_object.astimezone(self.clinic_tz) if dt_object.tzinfo else self.clinic_tz.localize(dt_object)
        except (ValueError, TypeError) as e:
            print(f"⚠️ Time parsing error for '{iso_datetime_str}', using fallback: {e}")
            return datetime.now(self.clinic_tz) + timedelta(hours=1)

    def find_patient(self, mobile_number=None, dob=None):
        """Find patient using normalized mobile number or DOB with dynamic column mapping."""
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            all_records = sheet.get_all_records()
            
            if mobile_number:
                clean_mobile_to_find = self._normalize_mobile(mobile_number)
                for patient in all_records:
                    if self._normalize_mobile(patient.get('mobileNumber')) == clean_mobile_to_find:
                        print(f"✅ Found patient by mobile: {patient.get('fullName')}")
                        return patient
            
            if dob:
                clean_dob_to_find = str(dob).strip()
                for patient in all_records:
                    if str(patient.get('dob', '')).strip() == clean_dob_to_find:
                        print(f"✅ Found patient by DOB: {patient.get('fullName')}")
                        return patient
            
            print(f"❌ Patient not found | Mobile: {mobile_number} | DOB: {dob}")
            return None
        except gspread.exceptions.APIError as e:
            print(f"❌ Google Sheets API error: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in find_patient: {e}")
            return None

    def register_patient(self, details):
        """Register new patient after checking for duplicates."""
        if self.find_patient(mobile_number=details.get("mobileNumber"), dob=details.get("dob")):
            print("❌ Duplicate patient detected; registration aborted.")
            return False
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            headers = sheet.row_values(1)
            new_row = [details.get(h, "") for h in headers]
            sheet.append_row(new_row, value_input_option='USER_ENTERED')
            print(f"✅ Registered new patient: {details.get('fullName')}")
            return True
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False

    def check_availability(self, iso_datetime_str):
        """Check calendar availability with robust timezone handling."""
        try:
            requested_time = self._parse_and_localize_time(iso_datetime_str)
            if not (self.clinic_open_hour <= requested_time.hour < self.clinic_close_hour):
                return "Outside clinic hours (9AM-5PM)"
                
            start_utc = requested_time.astimezone(pytz.utc)
            end_utc = start_utc + self.appointment_duration
            
            events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=start_utc.isoformat(), timeMax=end_utc.isoformat(), singleEvents=True, maxResults=1).execute().get("items", [])
            if not events: return "AVAILABLE"

            suggestions = []
            current_time = requested_time
            end_of_day = requested_time.replace(hour=self.clinic_close_hour, minute=0, second=0, microsecond=0)
            
            while len(suggestions) < 3 and current_time < end_of_day:
                current_time += self.appointment_duration # Check next full slot
                if current_time >= end_of_day: break
                
                check_start_utc = current_time.astimezone(pytz.utc)
                check_end_utc = check_start_utc + self.appointment_duration
                
                check_events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=check_start_utc.isoformat(), timeMax=check_end_utc.isoformat(), singleEvents=True, maxResults=1).execute().get("items", [])
                if not check_events:
                    suggestions.append(current_time.strftime("%-I:%M %p"))
            
            return f"Suggestions: {', '.join(suggestions)}" if suggestions else "No other available slots found today."
        except Exception as e:
            print(f"❌ Availability check error: {e}")
            return "Error checking calendar"
            
    def schedule_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        """Schedule appointment with proper timezone handling and verification"""
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient: return None
            
            start_time = self._parse_and_localize_time(iso_datetime_str)
            end_time = start_time + self.appointment_duration
            
            event = {
                "summary": f"Appointment: {patient.get('fullName', 'Unknown')}",
                "description": f"Patient verified via system.\nMobile: {patient.get('mobileNumber')}\nDOB: {patient.get('dob')}",
                "start": {"dateTime": start_time.isoformat(), "timeZone": str(self.clinic_tz)},
                "end": {"dateTime": end_time.isoformat(), "timeZone": str(self.clinic_tz)},
                "reminders": {"useDefault": True}
            }
            
            created_event = self.calendar_service.events().insert(calendarId=self.calendar_id, body=event).execute()
            print(f"✅ Scheduled: {patient['fullName']} at {start_time} | Event ID: {created_event.get('id')}")
            return start_time
        except Exception as e:
            print(f"❌ Scheduling error: {e}")
            return None

    def cancel_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        """CRITICAL FIX: Cancel appointment using a precise time match to avoid errors."""
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient: return False
            
            target_time_local = self._parse_and_localize_time(iso_datetime_str)
            
            # Use a very tight search window to find the event, just a few seconds on each side.
            search_start_utc = (target_time_local - timedelta(seconds=10)).astimezone(pytz.utc)
            search_end_utc = (target_time_local + timedelta(seconds=10)).astimezone(pytz.utc)
            
            events = self.calendar_service.events().list(
                calendarId=self.calendar_id, timeMin=search_start_utc.isoformat(), timeMax=search_end_utc.isoformat(), singleEvents=True
            ).execute().get("items", [])
            
            for event in events:
                event_start_time = self._parse_and_localize_time(event['start'].get('dateTime'))
                
                # CRITICAL CHECK: Ensure the found event's start time EXACTLY matches the requested cancellation time.
                if patient.get("fullName", "").lower() in event.get("summary", "").lower() and event_start_time == target_time_local:
                    self.calendar_service.events().delete(calendarId=self.calendar_id, eventId=event["id"]).execute()
                    print(f"✅ Cancelled precise appointment for {patient['fullName']} at {target_time_local}")
                    return True
            
            print(f"❌ No exact appointment found for {patient.get('fullName', 'Unknown')} at {target_time_local}")
            return False
        except Exception as e:
            print(f"❌ Cancellation error: {e}")
            return False
