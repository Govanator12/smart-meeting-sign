# main.py - Meeting Light Controller with WiFi resilience, relay state logging, and web UI
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
from logger import Logger
from web_logger import WebLogger

# Enable garbage collection
gc.enable()
gc.collect()

class MeetingLight:
    def __init__(self):
        # Initialize logger first
        self.logger = Logger()
        self.logger.info("="*50)
        self.logger.info("Meeting Light Controller Starting (with Web UI)...")
        self.logger.info(f"Free memory: {gc.mem_free()} bytes")

        # Log reset cause for diagnostics
        try:
            reset_cause = machine.reset_cause()
            reset_reasons = {}

            # Only add reset reasons that exist on this platform
            if hasattr(machine, 'PWRON_RESET'):
                reset_reasons[machine.PWRON_RESET] = "Power-on reset"
            if hasattr(machine, 'HARD_RESET'):
                reset_reasons[machine.HARD_RESET] = "Hard reset (button press)"
            if hasattr(machine, 'WDT_RESET'):
                reset_reasons[machine.WDT_RESET] = "Watchdog timer reset (system hang detected)"
            if hasattr(machine, 'SOFT_RESET'):
                reset_reasons[machine.SOFT_RESET] = "Soft reset (Ctrl+D or software reset)"
            if hasattr(machine, 'DEEPSLEEP_RESET'):
                reset_reasons[machine.DEEPSLEEP_RESET] = "Deep sleep wake"

            reset_reason = reset_reasons.get(reset_cause, f"Unknown reset cause: {reset_cause}")
            self.logger.info(f"Reset cause: {reset_reason}")
        except Exception as e:
            self.logger.warning(f"Could not determine reset cause: {e}")

        # Initialize hardware
        self.relay = machine.Pin(RELAY_PIN, machine.Pin.OUT)
        self.led = machine.Pin(LED_PIN, machine.Pin.OUT)
        self.relay.on()  # Active-LOW: on() = relay OFF (light off at startup)
        self.led.off()

        # State tracking
        self.events_cache = []
        self.last_calendar_fetch = 0
        self.in_meeting = False
        self.relay_state = "OFF"  # Track relay state for logging
        self.logger.info(f"Initial relay state: {self.relay_state} (boot initialization)")
        self.wifi_connected = False
        self.wifi_reconnect_attempts = 0
        self.wifi_reconnect_delay = 5  # Initial reconnect delay in seconds
        self.max_wifi_reconnect_delay = 300  # Max delay of 5 minutes
        self.last_wifi_check = 0
        self.wifi_check_interval = 60  # Check WiFi every 60 seconds

        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5

        # Initialize watchdog timer (8 seconds timeout)
        try:
            self.wdt = machine.WDT(timeout=8000)
            self.logger.info("Watchdog timer initialized (8s timeout)")
        except:
            self.logger.warning("Watchdog timer not available")
            self.wdt = None

        # Initialize web logger
        self.web_logger = WebLogger(self.logger, port=8080)

        # Connect to WiFi first
        self.connect_wifi()

        # Sync time (needed for OAuth2)
        self.sync_time()

        # Initialize OAuth2 handler
        self.logger.info("Initializing OAuth2...")
        try:
            self.oauth = OAuth2Handler(
                CLIENT_ID,
                CLIENT_SECRET,
                CALENDAR_SCOPE,
                TOKEN_FILE
            )

            # Test OAuth2 connection
            if not self.oauth.get_valid_token():
                self.logger.error("Failed to authenticate with Google")
                self.error_flash()
            else:
                self.logger.info("Google Calendar connected successfully!")
        except Exception as e:
            self.logger.error(f"OAuth initialization failed: {e}")
            self.error_flash()

    def feed_watchdog(self):
        """Feed the watchdog timer to prevent reset"""
        if self.wdt:
            try:
                self.wdt.feed()
            except:
                pass

    def set_relay(self, state, reason=""):
        """
        Control relay with detailed logging
        state: "ON" (light on) or "OFF" (light off)
        reason: Why the relay is being changed
        """
        if state == "ON":
            self.relay.off()  # Active-LOW: off() = relay ON
            new_state = "ON"
        else:
            self.relay.on()  # Active-LOW: on() = relay OFF
            new_state = "OFF"

        # Only log if state actually changed
        if new_state != self.relay_state:
            self.relay_state = new_state
            t = time.localtime()
            timestamp = f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
            self.logger.info(f"RELAY -> {new_state} ({reason}) at {timestamp}")

        return new_state

    def connect_wifi(self, force_reconnect=False):
        """Connect to WiFi network with exponential backoff"""
        self.logger.info(f"Connecting to WiFi: {WIFI_SSID} (attempt {self.wifi_reconnect_attempts + 1})")

        try:
            # Reset WiFi first to ensure clean state
            try:
                if hasattr(self, 'wlan'):
                    self.wlan.active(False)
                    self.wlan.disconnect()
                    time.sleep(1)
            except:
                pass

            # Create fresh WiFi connection
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(False)
            time.sleep(0.5)
            self.wlan.active(True)
            time.sleep(0.5)

            # Set WiFi power saving mode off for better reliability
            try:
                self.wlan.config(pm=0xa11140)  # Disable power saving
            except:
                pass

            # Connect to WiFi
            self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)

            # Wait for connection with timeout
            max_wait = 30  # 30 seconds timeout
            wait_count = 0
            while not self.wlan.isconnected() and wait_count < max_wait:
                self.blink_led(1, 0.2)
                self.feed_watchdog()
                wait_count += 1
                time.sleep(1)

                # Log progress every 5 seconds
                if wait_count % 5 == 0:
                    self.logger.info(f"WiFi connecting... ({wait_count}s)")

            if self.wlan.isconnected():
                self.wifi_connected = True
                self.wifi_reconnect_attempts = 0
                self.wifi_reconnect_delay = 5  # Reset delay on successful connection
                ip_info = self.wlan.ifconfig()
                self.logger.info(f"WiFi connected! IP: {ip_info[0]}")
                self.logger.info(f"Signal strength: {self.get_wifi_signal()} dBm")

                # Start web server for remote log access
                if self.web_logger.start():
                    self.logger.info(f"Web UI available at: http://{ip_info[0]}:8080/")
                    print(f"\n{'='*50}")
                    print(f"WEB UI: http://{ip_info[0]}:8080/")
                    print(f"{'='*50}\n")
                else:
                    self.logger.warning("Failed to start web server")

                self.led.on()
                time.sleep(1)
                self.led.off()
                return True
            else:
                self.wifi_connected = False
                self.wifi_reconnect_attempts += 1
                self.logger.error(f"WiFi connection failed (attempt {self.wifi_reconnect_attempts})")

                # Exponential backoff with max delay
                current_delay = min(self.wifi_reconnect_delay * (2 ** (self.wifi_reconnect_attempts - 1)),
                                  self.max_wifi_reconnect_delay)
                self.logger.info(f"Will retry WiFi connection in {current_delay} seconds...")

                # Wait with watchdog feeding
                for i in range(int(current_delay)):
                    self.feed_watchdog()
                    time.sleep(1)

                return False

        except Exception as e:
            self.logger.error(f"WiFi connection error: {e}")
            self.wifi_reconnect_attempts += 1

            # Exponential backoff on exception too
            current_delay = min(self.wifi_reconnect_delay * (2 ** (self.wifi_reconnect_attempts - 1)),
                              self.max_wifi_reconnect_delay)
            self.logger.info(f"Will retry WiFi connection in {current_delay} seconds...")

            for i in range(int(current_delay)):
                self.feed_watchdog()
                time.sleep(1)

            return False

    def get_wifi_signal(self):
        """Get WiFi signal strength"""
        try:
            if hasattr(self.wlan, 'status'):
                return self.wlan.status('rssi')
            return "N/A"
        except:
            return "N/A"

    def check_wifi_connection(self):
        """Periodically check WiFi connection and reconnect if needed"""
        current_time = time.time()

        if current_time - self.last_wifi_check < self.wifi_check_interval:
            return True

        self.last_wifi_check = current_time

        try:
            if not self.wlan.isconnected():
                self.logger.warning("WiFi disconnected, attempting reconnection...")
                self.wifi_connected = False

                # Keep trying to reconnect with exponential backoff
                while not self.wlan.isconnected():
                    if self.connect_wifi(force_reconnect=True):
                        self.sync_time()
                        return True
                    # connect_wifi handles the backoff delay
                return False
            else:
                # WiFi is connected, check signal strength
                signal = self.get_wifi_signal()
                if signal != "N/A" and signal < -80:
                    self.logger.warning(f"Weak WiFi signal: {signal} dBm")

                return True
        except Exception as e:
            self.logger.error(f"WiFi check error: {e}")
            return False

    def sync_time(self):
        """Sync time via NTP with better error handling"""
        self.logger.info("Syncing time via NTP...")
        max_attempts = 5

        for attempt in range(max_attempts):
            try:
                self.feed_watchdog()
                ntptime.settime()
                t = time.localtime()
                self.logger.info(f"Time synced: {t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d} UTC")
                return True
            except Exception as e:
                if attempt < max_attempts - 1:
                    self.logger.warning(f"NTP sync attempt {attempt + 1} failed: {e}, retrying...")
                    time.sleep(2)
                else:
                    self.logger.error(f"NTP sync failed after {max_attempts} attempts")

        return False

    def fetch_calendar_events(self):
        """Fetch and cache calendar events with improved error handling"""
        self.logger.info("Fetching calendar events...")
        self.blink_led(3, 0.1)
        self.feed_watchdog()

        try:
            # Check WiFi before fetching
            if not self.check_wifi_connection():
                self.logger.error("Cannot fetch calendar - WiFi not connected")
                return False

            # Get valid OAuth2 token
            token = self.oauth.get_valid_token()
            if not token:
                self.logger.error("Could not get valid auth token")
                self.consecutive_errors += 1
                return False

            # Get current time for date range (in UTC)
            now = time.localtime()
            year, month, day = now[0], now[1], now[2]

            # Create time range for next 48 hours in UTC
            time_min = f"{year:04d}-{month:02d}-{day:02d}T{now[3]:02d}:{now[4]:02d}:00Z"

            # Calculate end time (48 hours from now)
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

            self.logger.info(f"Fetching events from {time_min} to {time_max}")

            # Build Calendar API request
            url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
            params = (f"?timeMin={time_min}&timeMax={time_max}"
                     f"&singleEvents=true&orderBy=startTime&maxResults=50"
                     f"&timeZone=UTC")

            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json'
            }

            self.feed_watchdog()

            # Make API request with timeout
            response = requests.get(url + params, headers=headers)
            data = response.json()
            response.close()
            gc.collect()

            self.feed_watchdog()

            # Check for API errors
            if 'error' in data:
                error_code = data['error'].get('code', 0)
                error_msg = data['error'].get('message', 'Unknown error')
                self.logger.error(f"API Error {error_code}: {error_msg}")

                if error_code == 401:
                    self.logger.info("Token expired, refreshing...")
                    self.oauth.refresh_access_token()

                self.consecutive_errors += 1
                return False

            # Process events
            self.events_cache = []
            items = data.get('items', [])

            if not items:
                self.logger.info("No events found for next 48 hours")
            else:
                self.logger.info(f"Found {len(items)} total events")

                for event in items:
                    if self.should_skip_event(event):
                        continue

                    start_str = event.get('start', {}).get('dateTime', '')
                    end_str = event.get('end', {}).get('dateTime', '')

                    if start_str and end_str:
                        processed_event = {
                            'summary': event.get('summary', 'No title')[:50],
                            'start': self.parse_time_utc(start_str),
                            'end': self.parse_time_utc(end_str)
                        }
                        self.events_cache.append(processed_event)

                        event_date = start_str.split('T')[0]
                        event_time = start_str.split('T')[1][:5] if 'T' in start_str else ''
                        today_date = f"{year:04d}-{month:02d}-{day:02d}"
                        if event_date == today_date:
                            self.logger.info(f"  Today {event_time} UTC: {processed_event['summary']}")
                        else:
                            self.logger.info(f"  {event_date} {event_time} UTC: {processed_event['summary']}")

            self.last_calendar_fetch = time.time()
            self.logger.info(f"Cached {len(self.events_cache)} relevant events")
            self.consecutive_errors = 0  # Reset error counter on success
            gc.collect()
            return True

        except MemoryError:
            self.logger.error("Memory error - reducing cache size")
            self.events_cache = self.events_cache[:10]
            gc.collect()
            self.consecutive_errors += 1
            return False
        except Exception as e:
            self.logger.error(f"Calendar fetch error: {e}")
            self.error_flash()
            self.consecutive_errors += 1
            return False

    def should_skip_event(self, event):
        """Check if event should be skipped based on filters"""
        # Skip declined events
        if IGNORE_DECLINED:
            attendees = event.get('attendees', [])
            for attendee in attendees:
                if attendee.get('self', False):
                    if attendee.get('responseStatus') == 'declined':
                        self.logger.debug(f"Skipping declined: {event.get('summary', '')[:30]}")
                        return True

        # Skip all-day events
        if IGNORE_ALL_DAY and 'date' in event.get('start', {}):
            self.logger.debug(f"Skipping all-day: {event.get('summary', '')[:30]}")
            return True

        # Skip Personal Work (tangerine color) events
        if event.get('colorId') == PERSONAL_WORK_COLOR_ID:
            self.logger.debug(f"Skipping personal: {event.get('summary', '')[:30]}")
            return True

        # Skip Focus Time (banana color) events
        if event.get('colorId') == FOCUS_TIME_COLOR_ID:
            self.logger.debug(f"Skipping focus: {event.get('summary', '')[:30]}")
            return True

        # Skip OOO events
        if IGNORE_OOO:
            if event.get('eventType') == 'outOfOffice':
                self.logger.debug(f"Skipping OOO: {event.get('summary', '')[:30]}")
                return True

            if event.get('transparency') == 'transparent':
                self.logger.debug(f"Skipping transparent: {event.get('summary', '')[:30]}")
                return True

            summary_lower = event.get('summary', '').lower()
            if any(term in summary_lower for term in ['ooo', 'out of office', 'vacation']):
                self.logger.debug(f"Skipping OOO text: {event.get('summary', '')[:30]}")
                return True

        return False

    def parse_time_utc(self, time_str):
        """Parse ISO time string to epoch seconds (expecting UTC times)"""
        try:
            date_part = time_str.split('T')[0]
            time_part = time_str.split('T')[1][:8]

            year, month, day = map(int, date_part.split('-'))
            hour, minute, second = map(int, time_part.split(':'))

            return time.mktime((year, month, day, hour, minute, second, 0, 0))
        except Exception as e:
            self.logger.error(f"Time parse error: {e} for {time_str}")
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
                    self.logger.info(f"MEETING STARTED: {event['summary']}")
                    self.in_meeting = True
                    self.set_relay("ON", f"Meeting: {event['summary']}")
                    self.led.on()  # Solid LED during meeting
                return True

        # No active meetings
        if self.in_meeting:
            self.logger.info("MEETING ENDED")
            self.in_meeting = False
            self.set_relay("OFF", "Meeting ended")
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
        self.logger.warning("Error flash sequence triggered")
        for i in range(3):
            self.set_relay("ON", f"Error flash {i+1}/3")
            self.led.on()
            time.sleep(1)
            self.set_relay("OFF", f"Error flash {i+1}/3 end")
            self.led.off()
            time.sleep(1)

    def run(self):
        """Main loop with improved error handling"""
        self.logger.info("Starting main loop...")
        self.logger.info("="*50)

        # Initial calendar fetch
        self.fetch_calendar_events()

        last_status_check = 0
        last_gc = 0
        last_health_log = 0
        health_log_interval = 300  # Log health status every 5 minutes

        while True:
            try:
                self.feed_watchdog()

                # Check for web requests (non-blocking)
                self.web_logger.check_requests()

                current_time = time.time()

                # Garbage collection every minute
                if current_time - last_gc >= 60:
                    gc.collect()
                    last_gc = current_time

                # Health status logging
                if current_time - last_health_log >= health_log_interval:
                    free_mem = gc.mem_free()
                    signal = self.get_wifi_signal()
                    self.logger.info(f"Health check - Memory: {free_mem} bytes, WiFi: {signal} dBm, In meeting: {self.in_meeting}")
                    last_health_log = current_time

                # Check for too many consecutive errors (but not WiFi errors, those use backoff)
                if self.consecutive_errors >= self.max_consecutive_errors:
                    self.logger.error(f"Too many consecutive API/OAuth errors ({self.consecutive_errors})")
                    self.logger.info("Will continue retrying with exponential backoff...")
                    # Reset error counter but don't reset device
                    self.consecutive_errors = 0

                # Refresh calendar
                if current_time - self.last_calendar_fetch >= CALENDAR_REFRESH_INTERVAL:
                    if not self.fetch_calendar_events():
                        # If fetch failed, try again in 60 seconds
                        self.last_calendar_fetch = current_time - CALENDAR_REFRESH_INTERVAL + 60

                # Check meeting status
                if current_time - last_status_check >= STATUS_CHECK_INTERVAL:
                    if not self.in_meeting:
                        # Quick blink when checking (only if not in meeting)
                        self.blink_led(1, 0.05)
                    self.check_meeting_status()
                    last_status_check = current_time

                # Check WiFi connection periodically
                self.check_wifi_connection()

                time.sleep(1)

            except MemoryError:
                self.logger.error("Memory error in main loop, restarting...")
                time.sleep(2)
                machine.reset()
            except KeyboardInterrupt:
                self.logger.info("Stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                self.consecutive_errors += 1
                self.error_flash()
                time.sleep(10)

# Start the meeting light controller
if __name__ == "__main__":
    try:
        controller = MeetingLight()
        controller.run()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        time.sleep(5)
        machine.reset()