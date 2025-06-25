# clinic_manager.py

import os
import json
import base64
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

    def _initialize_services(self):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/calendar"
        ]
        creds_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_b64:
            raise ValueError("FATAL ERROR: GOOGLE_CREDENTIALS_JSON not set.")

        creds_dict = json.loads(base64.b64decode(creds_json_b64))
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds), build('calendar', 'v3', credentials=creds)

    def _parse_and_localize_time(self, iso_datetime_str):
        if iso_datetime_str.endswith('Z'):
            iso_datetime_str = iso_datetime_str[:-1] + '+00:00'
        dt_object = datetime.fromisoformat(iso_datetime_str)
        return dt_object.astimezone(self.clinic_tz)

    def _normalize_mobile(self, number):
        return str(number).replace(" ", "").replace("-", "").strip().lstrip("0")

    def find_patient(self, mobile_number=None, dob=None):
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            records = sheet.get_all_records()
            for row in records:
                row_mobile = self._normalize_mobile(row.get("Mobile", ""))
                row_dob = str(row.get("DOB", "")).strip()
                if mobile_number and self._normalize_mobile(mobile_number) == row_mobile:
                    return row
                if dob and str(dob).strip() == row_dob:
                    return row
            return None
        except Exception as e:
            print(f"❌ Error in find_patient: {e}")
            return None

    def register_patient(self, details):
        if self.find_patient(details.get("mobileNumber"), details.get("dob")):
            print("❌ Duplicate patient.")
            return False
        try:
            sheet = self.sheets_service.open(self.sheet_name).sheet1
            headers = sheet.row_values(1)
            new_row = [details.get(h, '') for h in headers]
            sheet.append_row(new_row)
            print("✅ Patient registered.")
            return True
        except Exception as e:
            print(f"❌ Error in register_patient: {e}")
            return False

    def check_availability(self, iso_datetime_str):
        try:
            requested_time = self._parse_and_localize_time(iso_datetime_str)
            if not (self.clinic_open_hour <= requested_time.hour < self.clinic_close_hour):
                return "Sorry, that time is outside clinic hours."

            start_utc = requested_time.astimezone(pytz.utc)
            end_utc = start_utc + self.appointment_duration

            events = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_utc.isoformat(),
                timeMax=end_utc.isoformat(),
                singleEvents=True
            ).execute().get('items', [])

            if not events:
                return "AVAILABLE"

            suggestions = []
            search_time = requested_time
            day_end_local = requested_time.replace(hour=self.clinic_close_hour, minute=0)

            while len(suggestions) < 3 and search_time < day_end_local:
                search_time += self.appointment_duration
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

            return f"Suggestions: {', '.join(suggestions)}" if suggestions else "I'm sorry, no free slots later today."
        except Exception as e:
            print(f"❌ Error in check_availability: {e}")
            return "Error checking calendar."

    def schedule_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        try:
            patient = self.find_patient(mobile_number, dob)
            if not patient:
                return None

            start_time = self._parse_and_localize_time(iso_datetime_str)
            end_time = start_time + self.appointment_duration

            event = {
                'summary': f'Appointment: {patient.get("Full Name", "Unknown")}',
                'start': {'dateTime': start_time.isoformat(), 'timeZone': str(self.clinic_tz)},
                'end': {'dateTime': end_time.isoformat(), 'timeZone': str(self.clinic_tz)}
            }

            self.calendar_service.events().insert(calendarId=self.calendar_id, body=event).execute()
            return start_time
        except Exception as e:
            print(f"❌ Error in schedule_appointment: {e}")
            return None

    def cancel_appointment(self, iso_datetime_str, mobile_number=None, dob=None):
        try:
            patient = self.find_patient(mobile_number, dob)
            if not patient:
                return False

            target_time = self._parse_and_localize_time(iso_datetime_str)
            start_utc = target_time.astimezone(pytz.utc)
            end_utc = start_utc + timedelta(seconds=60)

            events = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_utc.isoformat(),
                timeMax=end_utc.isoformat(),
                singleEvents=True
            ).execute().get('items', [])

            for event in events:
                if patient.get("Full Name", "").lower() in event.get('summary', '').lower():
                    self.calendar_service.events().delete(calendarId=self.calendar_id, eventId=event['id']).execute()
                    return True

            return False
        except Exception as e:
            print(f"❌ Error in cancel_appointment: {e}")
            return False
