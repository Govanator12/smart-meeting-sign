# main.py - Meeting Light Controller with OAuth2 (Active-LOW Relay Version)
import network
import urequests as requests
import ujson as json
import utime as time
import machine
import gc
import ntptime

# Import configuration and OAuth handler
from config import *
from oauth_handler import OAuth2Handler

# Enable garbage collection
gc.enable()
gc.collect()

class MeetingLight:
    def __init__(self):
        # Initialize hardware
        self.relay = machine.Pin(RELAY_PIN, machine.Pin.OUT)
        self.led = machine.Pin(LED_PIN, machine.Pin.OUT)
        self.relay.on()  # Active-LOW: on() = relay OFF (light off at startup)
        self.led.off()
        
        # State tracking
        self.events_cache = []
        self.last_calendar_fetch = 0
        self.in_meeting = False
        self.wifi_connected = False
        
        # Connect to WiFi first
        self.connect_wifi()
        
        # Sync time (needed for OAuth2)
        self.sync_time()
        
        # Initialize OAuth2 handler
        print("Initializing OAuth2...")
        self.oauth = OAuth2Handler(
            CLIENT_ID,
            CLIENT_SECRET,
            CALENDAR_SCOPE,
            TOKEN_FILE
        )
        
        # Test OAuth2 connection
        if not self.oauth.get_valid_token():
            print("❌ Failed to authenticate with Google")
            self.error_flash()
        else:
            print("✅ Google Calendar connected!")
    
    def connect_wifi(self):
        """Connect to WiFi network with proper reset"""
        print(f"Connecting to WiFi: {WIFI_SSID}")
        
        try:
            # Reset WiFi first to ensure clean state
            try:
                temp_wlan = network.WLAN(network.STA_IF)
                temp_wlan.active(False)
                temp_wlan.deinit()
                time.sleep(1)
            except:
                pass
                
            # Now create fresh WiFi connection
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(False)
            time.sleep(0.5)
            self.wlan.active(True)
            time.sleep(0.5)
            
            if self.wlan.isconnected():
                self.wlan.disconnect()
                time.sleep(1)
            
            self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
            
            max_attempts = 20
            attempt = 0
            while not self.wlan.isconnected() and attempt < max_attempts:
                self.blink_led(1, 0.2)
                print(".", end="")
                attempt += 1
                time.sleep(1)
            
            if self.wlan.isconnected():
                self.wifi_connected = True
                print(f"\n✅ WiFi connected! IP: {self.wlan.ifconfig()[0]}")
                self.led.on()
                time.sleep(1)
                self.led.off()
            else:
                print("\n❌ WiFi connection failed!")
                time.sleep(2)
                machine.reset()
                
        except Exception as e:
            print(f"WiFi error: {e}")
            time.sleep(2)
            machine.reset()
    
    def sync_time(self):
        """Sync time via NTP (required for OAuth2)"""
        print("Syncing time...")
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                ntptime.settime()
                t = time.localtime()
                print(f"✓ Time synced: {t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")
                return True
            except:
                if attempt < max_attempts - 1:
                    print(f"Time sync attempt {attempt + 1} failed, retrying...")
                    time.sleep(2)
        
        print("Warning: Time sync failed - OAuth may not work correctly")
        return False
    
    def fetch_calendar_events(self):
        """Fetch and cache calendar events using OAuth2"""
        print("\n📅 Fetching calendar events...")
        self.blink_led(3, 0.1)
        
        # Get valid OAuth2 token
        token = self.oauth.get_valid_token()
        if not token:
            print("❌ Could not get valid auth token")
            return
        
        try:
            # Get current time for date range (in UTC)
            now = time.localtime()
            year, month, day = now[0], now[1], now[2]
            
            # Create time range for next 48 hours in UTC
            # Start from now
            time_min = f"{year:04d}-{month:02d}-{day:02d}T{now[3]:02d}:{now[4]:02d}:00Z"
            
            # Calculate end time (48 hours from now)
            # Simple approach: add 2 days (won't be exact for month boundaries but close enough)
            end_day = day + 2
            end_month = month
            end_year = year
            
            # Handle month overflow (simplified)
            if end_day > 28:  # Safe for all months
                if month == 2:  # February
                    if end_day > 28:
                        end_day = end_day - 28
                        end_month = month + 1
                elif month in [4, 6, 9, 11]:  # 30-day months
                    if end_day > 30:
                        end_day = end_day - 30
                        end_month = month + 1
                else:  # 31-day months
                    if end_day > 31:
                        end_day = end_day - 31
                        end_month = month + 1
            
            # Handle year overflow
            if end_month > 12:
                end_month = 1
                end_year = year + 1
            
            time_max = f"{end_year:04d}-{end_month:02d}-{end_day:02d}T{now[3]:02d}:{now[4]:02d}:00Z"
            
            print(f"Fetching events from now until {end_year}-{end_month:02d}-{end_day:02d}")
            
            # Build Calendar API request - REQUEST UTC TIMES
            url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
            params = (f"?timeMin={time_min}&timeMax={time_max}"
                     f"&singleEvents=true&orderBy=startTime&maxResults=50"
                     f"&timeZone=UTC")  # Force UTC timezone
            
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json'
            }
            
            # Make API request
            response = requests.get(url + params, headers=headers)
            data = response.json()
            response.close()
            gc.collect()
            
            # Check for API errors
            if 'error' in data:
                error_code = data['error'].get('code', 0)
                error_msg = data['error'].get('message', 'Unknown error')
                print(f"API Error {error_code}: {error_msg}")
                
                # If unauthorized, try refreshing token
                if error_code == 401:
                    print("Token expired, refreshing...")
                    self.oauth.refresh_access_token()
                return
            
            # Process events
            self.events_cache = []
            items = data.get('items', [])
            
            if not items:
                print("No events found for next 48 hours")
                return
            
            print(f"Found {len(items)} total events in next 48 hours")
            
            for event in items:
                # Check if we should skip this event
                if self.should_skip_event(event):
                    continue
                
                # Get event times (now in UTC)
                start_str = event.get('start', {}).get('dateTime', '')
                end_str = event.get('end', {}).get('dateTime', '')
                
                if start_str and end_str:
                    processed_event = {
                        'summary': event.get('summary', 'No title')[:50],  # Limit length
                        'start': self.parse_time_utc(start_str),
                        'end': self.parse_time_utc(end_str)
                    }
                    self.events_cache.append(processed_event)
                    
                    # Show date and time in local for display
                    event_date = start_str.split('T')[0]
                    event_time = start_str.split('T')[1][:5] if 'T' in start_str else ''
                    today_date = f"{year:04d}-{month:02d}-{day:02d}"
                    if event_date == today_date:
                        print(f"  📌 Today {event_time} UTC: {processed_event['summary']}")
                    else:
                        print(f"  📌 {event_date} {event_time} UTC: {processed_event['summary']}")
            
            self.last_calendar_fetch = time.time()
            print(f"✓ Cached {len(self.events_cache)} relevant events")
            gc.collect()
            
        except MemoryError:
            print("Memory error - reducing cache size")
            self.events_cache = self.events_cache[:10]
            gc.collect()
        except Exception as e:
            print(f"Calendar fetch error: {e}")
            self.error_flash()
    
    def should_skip_event(self, event):
        """Check if event should be skipped based on filters"""
        # Skip declined events
        if IGNORE_DECLINED:
            attendees = event.get('attendees', [])
            for attendee in attendees:
                if attendee.get('self', False):
                    if attendee.get('responseStatus') == 'declined':
                        print(f"  ⏭️  Skipping (declined): {event.get('summary', '')[:30]}")
                        return True
        
        # Skip all-day events
        if IGNORE_ALL_DAY and 'date' in event.get('start', {}):
            print(f"  ⏭️  Skipping (all-day): {event.get('summary', '')[:30]}")
            return True
        
        # Skip Personal Work (tangerine color) events
        if event.get('colorId') == PERSONAL_WORK_COLOR_ID:
            print(f"  ⏭️  Skipping (personal/tangerine): {event.get('summary', '')[:30]}")
            return True
        
        # Skip Focus Time (banana color) events
        if event.get('colorId') == FOCUS_TIME_COLOR_ID:
            print(f"  ⏭️  Skipping (focus/banana): {event.get('summary', '')[:30]}")
            return True
        
        # Skip OOO events
        if IGNORE_OOO:
            # Check event type
            if event.get('eventType') == 'outOfOffice':
                print(f"  ⏭️  Skipping (OOO type): {event.get('summary', '')[:30]}")
                return True
            
            # Check transparency
            if event.get('transparency') == 'transparent':
                print(f"  ⏭️  Skipping (transparent): {event.get('summary', '')[:30]}")
                return True
            
            # Check summary text as fallback
            summary_lower = event.get('summary', '').lower()
            if any(term in summary_lower for term in ['ooo', 'out of office', 'vacation']):
                print(f"  ⏭️  Skipping (OOO text): {event.get('summary', '')[:30]}")
                return True
        
        return False
    
    def parse_time_utc(self, time_str):
        """Parse ISO time string to epoch seconds (expecting UTC times)"""
        try:
            # Format: 2024-01-15T10:30:00Z (Z means UTC)
            # Or: 2024-01-15T10:30:00-05:00 (with timezone offset)
            date_part = time_str.split('T')[0]
            time_part = time_str.split('T')[1][:8]
            
            year, month, day = map(int, date_part.split('-'))
            hour, minute, second = map(int, time_part.split(':'))
            
            # Convert to epoch (Pico is now in UTC after NTP sync)
            return time.mktime((year, month, day, hour, minute, second, 0, 0))
        except Exception as e:
            print(f"Time parse error: {e} for {time_str}")
            return 0
    
    def check_meeting_status(self):
        """Check if currently in a meeting based on cached events"""
        now = time.localtime()
        current_time = time.mktime(now)
        
        buffer_seconds = MEETING_BUFFER_MINUTES * 60
        
        for event in self.events_cache:
            meeting_start = event['start'] - buffer_seconds  # Start early
            meeting_end = event['end'] + buffer_seconds      # End late
            
            if meeting_start <= current_time <= meeting_end:
                if not self.in_meeting:
                    print(f"\n🔴 MEETING ON: {event['summary']}")
                    self.in_meeting = True
                    self.relay.off()  # Active-LOW: off() = relay ON (light ON)
                    self.led.on()  # Solid LED during meeting
                return True
        
        # No active meetings
        if self.in_meeting:
            print("\n🟢 MEETING OFF")
            self.in_meeting = False
            self.relay.on()  # Active-LOW: on() = relay OFF (light OFF)
            self.led.off()
        
        return False
    
    def blink_led(self, times, duration):
        """Blink the built-in LED"""
        for _ in range(times):
            self.led.on()
            time.sleep(duration)
            self.led.off()
            time.sleep(duration)
    
    def error_flash(self):
        """Flash relay/LED to indicate error"""
        for _ in range(3):
            self.relay.off()  # Active-LOW: off() = relay ON
            self.led.on()
            time.sleep(1)
            self.relay.on()  # Active-LOW: on() = relay OFF
            self.led.off()
            time.sleep(1)
    
    def run(self):
        """Main loop"""
        print("\n🚀 Starting Meeting Light Controller...")
        print("="*50)
        
        # Initial calendar fetch
        self.fetch_calendar_events()
        
        last_status_check = 0
        last_gc = 0
        
        while True:
            try:
                current_time = time.time()
                
                # Garbage collection every minute
                if current_time - last_gc >= 60:
                    gc.collect()
                    last_gc = current_time
                
                # Refresh calendar every 15 minutes
                if current_time - self.last_calendar_fetch >= CALENDAR_REFRESH_INTERVAL:
                    self.fetch_calendar_events()
                
                # Check meeting status every 10 seconds
                if current_time - last_status_check >= STATUS_CHECK_INTERVAL:
                    if not self.in_meeting:
                        # Quick blink when checking (only if not in meeting)
                        self.blink_led(1, 0.05)
                    self.check_meeting_status()
                    last_status_check = current_time
                
                # Check WiFi connection
                if not self.wlan.isconnected():
                    print("WiFi disconnected, reconnecting...")
                    self.wifi_connected = False
                    self.wlan.active(False)
                    time.sleep(1)
                    self.connect_wifi()
                    self.sync_time()
                
                time.sleep(1)
                
            except MemoryError:
                print("Memory error - restarting...")
                machine.reset()
            except KeyboardInterrupt:
                print("\nStopped by user")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                self.error_flash()
                time.sleep(10)

# Start the meeting light controller
if __name__ == "__main__":
    try:
        controller = MeetingLight()
        controller.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"Fatal error: {e}")
        time.sleep(5)
        machine.reset()