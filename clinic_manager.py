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
        # Configuration
        self.sheet_name = os.getenv("SHEET_NAME", "WellnessGroveClinic_Patients")
        self.calendar_id = os.getenv("CALENDAR_ID", "primary")
        self.appointment_duration = timedelta(minutes=30)
        self.clinic_tz = pytz.timezone(os.getenv("TIME_ZONE", "Australia/Sydney"))
        self.clinic_open_hour = 9
        self.clinic_close_hour = 17
        
        # Initialize services
        self.sheets_service, self.calendar_service = self._initialize_services()
        print(f"✅ ClinicManager initialized | Sheet: {self.sheet_name} | Calendar: {self.calendar_id}")

    def _initialize_services(self):
        """Set up authenticated Google service objects."""
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/calendar.events"
        ]
        creds_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_b64:
            raise ValueError("FATAL: GOOGLE_CREDENTIALS_JSON environment variable not set")
        
        try:
            creds_dict = json.loads(base64.b64decode(creds_json_b64))
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            sheets_service = gspread.authorize(creds)
            calendar_service = build('calendar', 'v3', credentials=creds)
            return sheets_service, calendar_service
        except Exception as e:
            print(f"❌ Service initialization failed: {e}")
            raise

    def _normalize_mobile(self, mobile_number):
        """Standardize mobile number format for matching."""
        if not mobile_number:
            return ""
        return re.sub(r"\D", "", str(mobile_number)).lstrip("0")

    def _parse_and_localize_time(self, iso_datetime_str):
        """Parse ISO string and convert to clinic timezone."""
        if not iso_datetime_str: raise ValueError("dateTime parameter cannot be null")
        try:
            if iso_datetime_str.endswith('Z'):
                iso_datetime_str = iso_datetime_str[:-1] + '+00:00'
            dt_object = datetime.fromisoformat(iso_datetime_str)
            return dt_object.astimezone(self.clinic_tz)
        except ValueError:
            print(f"⚠️ Could not parse '{iso_datetime_str}', falling back to current time.")
            return datetime.now(self.clinic_tz) + timedelta(hours=1)

    def find_patient(self, mobile_number=None, dob=None):
        """Find patient using normalized mobile number or DOB."""
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            records = sheet.get_all_records(head=1)
            
            if mobile_number:
                clean_mobile_to_find = self._normalize_mobile(mobile_number)
                for patient in records:
                    patient_mobile = self._normalize_mobile(patient.get('mobileNumber', ""))
                    if patient_mobile and patient_mobile == clean_mobile_to_find:
                        print(f"✅ Found patient by mobile: {patient.get('fullName')}")
                        return patient
            
            if dob:
                clean_dob_to_find = str(dob).strip().lower()
                for patient in records:
                    patient_dob = str(patient.get('dob', "")).strip().lower()
                    if patient_dob and patient_dob == clean_dob_to_find:
                        print(f"✅ Found patient by DOB: {patient.get('fullName')}")
                        return patient
            
            print(f"❌ Patient not found | Mobile: {mobile_number} | DOB: {dob}")
            return None
        except Exception as e:
            print(f"❌ Find patient error: {e}")
            return None

    def register_patient(self, details):
        """Register new patient after checking for duplicates."""
        if self.find_patient(mobile_number=details.get("mobileNumber"), dob=details.get("dob")):
            print("❌ Duplicate patient detected during registration attempt.")
            return False
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            headers = sheet.row_values(1)
            new_row = [details.get(h, "") for h in headers]
            sheet.append_row(new_row, value_input_option='USER_ENTERED')
            print(f"✅ Registered: {details.get('fullName')}")
            return True
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False

    def check_availability(self, iso_datetime_str):
        """Check calendar availability with timezone handling."""
        try:
            requested_time = self._parse_and_localize_time(iso_datetime_str)
            if not (self.clinic_open_hour <= requested_time.hour < self.clinic_close_hour):
                return "Outside clinic hours (9AM-5PM)"

            start_utc = requested_time.astimezone(pytz.utc)
            end_utc = start_utc + self.appointment_duration
            
            events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=start_utc.isoformat(), timeMax=end_utc.isoformat(), singleEvents=True).execute().get("items", [])
            if not events: return "AVAILABLE"

            suggestions = []
            current_time = requested_time
            end_of_day = requested_time.replace(hour=self.clinic_close_hour, minute=0, second=0, microsecond=0)
            
            while len(suggestions) < 3 and current_time < end_of_day:
                current_time += self.appointment_duration
                if current_time >= end_of_day: break
                    
                check_start_utc = current_time.astimezone(pytz.utc)
                check_end_utc = check_start_utc + self.appointment_duration
                
                check_events = self.calendar_service.events().list(calendarId=self.calendar_id, timeMin=check_start_utc.isoformat(), timeMax=check_end_utc.isoformat(), singleEvents=True).execute().get("items", [])
                if not check_events:
                    suggestions.append(current_time.strftime("%-I:%M %p"))
            
            return f"Suggestions: {', '.join(suggestions)}" if suggestions else "No other available slots found for today."
        except Exception as e:
            print(f"❌ Availability check error: {e}")
            return "Error checking calendar"
            
    def schedule_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        """Schedule appointment with proper timezone handling."""
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient:
                print("❌ Patient not found for scheduling")
                return None
            
            start_time = self._parse_and_localize_time(iso_datetime_str)
            end_time = start_time + self.appointment_duration
            
            event = {
                "summary": f"Appointment: {patient.get('fullName')}",
                "description": f"Verified via Mobile/DOB. Mobile: {patient.get('mobileNumber')} | DOB: {patient.get('dob')}",
                "start": {"dateTime": start_time.isoformat(), "timeZone": str(self.clinic_tz)},
                "end": {"dateTime": end_time.isoformat(), "timeZone": str(self.clinic_tz)}
            }
            
            self.calendar_service.events().insert(calendarId=self.calendar_id, body=event).execute()
            print(f"✅ Scheduled: {patient['fullName']} at {start_time}")
            return start_time
        except Exception as e:
            print(f"❌ Scheduling error: {e}")
            return None

    def cancel_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        """CRITICAL FIX: Cancel appointment using a precise time match to avoid errors."""
        try:
            patient = self.find_patient(mobile_number=mobile_number, dob=dob)
            if not patient:
                print("❌ Patient not found for cancellation")
                return False
            
            target_time = self._parse_and_localize_time(iso_datetime_str)
            
            # Search a wider window to catch events that might start a second or two off.
            search_start_utc = (target_time - timedelta(minutes=1)).astimezone(pytz.utc)
            search_end_utc = (target_time + timedelta(minutes=1)).astimezone(pytz.utc)
            
            events = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                timeMin=search_start_utc.isoformat(),
                timeMax=search_end_utc.isoformat(),
                singleEvents=True
            ).execute().get("items", [])
            
            for event in events:
                event_start_str = event['start'].get('dateTime')
                event_start_time = self._parse_and_localize_time(event_start_str)

                # CRITICAL CHECK: Ensure the found event's start time EXACTLY matches the requested cancellation time.
                if patient["fullName"].lower() in event.get("summary", "").lower() and event_start_time == target_time:
                    self.calendar_service.events().delete(calendarId=self.calendar_id, eventId=event["id"]).execute()
                    print(f"✅ Cancelled precise appointment for {patient['fullName']} at {target_time}")
                    return True
            
            print(f"❌ No exact appointment found for {patient['fullName']} at {target_time}")
            return False
        except Exception as e:
            print(f"❌ Cancellation error: {e}")
            return False
