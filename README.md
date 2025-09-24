# Meeting Status Light - Raspberry Pi Pico W

An automated LED sign controller that turns on during Google Calendar meetings using a Raspberry Pi Pico W with OAuth2 authentication. No need to make your calendar public!

## Features

- 🔐 **Private Calendar Access** - Uses OAuth2 device flow for secure authentication
- 🚦 **Automatic Control** - LED sign turns on/off based on meeting schedule
- ⏰ **Smart Timing** - Configurable buffer (default: 2 minutes before/after meetings)
- 🎨 **Event Filtering** - Automatically skips:
  - Declined meetings
  - All-day events
  - Out of Office events
  - Personal/Focus time (by calendar color)
- 🔄 **Daylight Saving Aware** - Handles DST changes automatically using UTC
- 💾 **Persistent Auth** - Authorize once, works forever with refresh tokens
- 📊 **Comprehensive Logging** - Persistent event logging with automatic rotation for diagnostics
- 🛡️ **Self-Healing** - Automatic WiFi reconnection with exponential backoff, watchdog timer, and error recovery
- 📈 **Health Monitoring** - Tracks memory usage, WiFi signal strength, and system health

## Hardware Requirements

- Raspberry Pi Pico W
- **5V 1-Channel Relay Module with Active-LOW trigger** (see important note below)
- USB Type A Female PCB Connector
- USB-powered LED sign
- Jumper wires
- Micro USB cable for power

### ⚠️ IMPORTANT: Relay Type Compatibility

**This code is configured for Active-LOW relay modules**, which are the most common type. These relays:
- Turn ON when GPIO is pulled LOW (0V)
- Turn OFF when GPIO is pulled HIGH (3.3V)
- Usually labeled as "5V Relay Module" on shopping sites
- Often have optocoupler isolation (good for protecting your Pico)

**How to identify your relay type:**
- **Active-LOW**: Most common, usually has markings like "IN: Low Level Trigger"
- **Active-HIGH**: Less common, marked as "High Level Trigger"

**If your LED sign turns ON when plugged in**, you have an Active-HIGH relay. See the Troubleshooting section for the fix.

## Wiring Diagram

```
Pico W → Relay Module
━━━━━━━━━━━━━━━━━━━━
Pin 36 (3V3)     → VCC (relay power)
Pin 38 (GND)     → GND (relay ground)
Pin 20 (GP15)    → IN  (relay signal)
Pin 40 (VBUS)    → COM (relay common)

Relay Module → USB Connector
━━━━━━━━━━━━━━━━━━━━━━━━━━
NO (Normally Open) → VBUS (5V pin)

USB Connector → Pico W
━━━━━━━━━━━━━━━━━━━━━
GND → Pin 38 (or any GND)
```

## Software Setup

### 1. Install MicroPython

1. Download the latest Pico W firmware from [micropython.org](https://micropython.org/download/RPI_PICO_W/)
2. Hold BOOTSEL button while connecting Pico W
3. Drag the .uf2 file to the RPI-RP2 drive
4. Pico W will reboot with MicroPython

### 2. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Google Calendar API
4. Configure OAuth consent screen:
   - Choose "External"
   - Add scope: `https://www.googleapis.com/auth/calendar.readonly`
   - Add your email as a test user (if in testing mode)
5. Create OAuth2 credentials:
   - Type: "TVs and Limited Input devices"
   - Save the Client ID and Client Secret

### 3. Configure the Project

1. Copy `config_secrets_template.py` to `config_secrets.py` and fill in your credentials:
```python
# WiFi credentials
WIFI_SSID = "your_wifi_name"
WIFI_PASSWORD = "your_wifi_password"

# OAuth2 credentials
CLIENT_ID = "your_client_id.apps.googleusercontent.com"
CLIENT_SECRET = "your_client_secret"
```

2. Adjust settings in `config.py` as needed:
```python
MEETING_BUFFER_MINUTES = 2  # Turn on X minutes early/late
CALENDAR_REFRESH_INTERVAL = 900  # Refresh every 15 minutes
```

### 4. Upload Files to Pico W

Using Thonny IDE:
1. Connect Pico W via USB
2. Upload these files in order:
   - `config_secrets.py` (your credentials)
   - `config.py` (settings)
   - `oauth_handler.py` (OAuth2 logic)
   - `logger.py` (logging system)
   - `main.py` (main program)
   - `view_logs.py` (optional - for troubleshooting)

### 5. First-Time Authorization

On first run, you'll see:
```
===== FIRST TIME SETUP - AUTHORIZATION NEEDED =====

📱 TO AUTHORIZE THIS DEVICE:
1. Visit: https://www.google.com/device
2. Enter code: XXXX-XXXX
3. Sign in and grant calendar access
```

Complete this one-time setup, and the device will save the refresh token for permanent access.

## Configuration Options

### Event Filtering

In `config.py`:
```python
IGNORE_DECLINED = True           # Skip meetings you've declined
IGNORE_ALL_DAY = True           # Skip all-day events
IGNORE_OOO = True               # Skip Out of Office events
PERSONAL_WORK_COLOR_ID = "6"   # Skip Tangerine colored events
FOCUS_TIME_COLOR_ID = "5"      # Skip Banana colored events
```

### Google Calendar Color IDs
- 1: Lavender
- 2: Sage
- 3: Grape
- 4: Flamingo
- 5: Banana (Focus Time)
- 6: Tangerine (Personal)
- 7: Peacock
- 8: Graphite
- 9: Blueberry
- 10: Basil
- 11: Tomato

### Timing Adjustments

```python
MEETING_BUFFER_MINUTES = 2      # Buffer before/after meetings
CALENDAR_REFRESH_INTERVAL = 900 # How often to fetch calendar (seconds)
STATUS_CHECK_INTERVAL = 10      # How often to check cached events
```

## LED Status Indicators

- **Quick blink** (every 10s): Checking calendar status
- **Triple blink**: Fetching fresh calendar data
- **Solid on**: Currently in a meeting
- **Off**: No meeting
- **Slow flash** (3 times): Error condition

## Troubleshooting

### Viewing System Logs

The system includes comprehensive logging to help diagnose issues. To view logs:

1. **In Thonny IDE**, run:
```python
exec(open('view_logs.py').read())
```

2. **Select from the menu**:
   - Option 1/2: View recent log entries (50 or 100 lines)
   - Option 3: Analyze logs for common issues (WiFi disconnects, OAuth failures, memory errors)
   - Option 4: Live log monitoring (similar to `tail -f`)
   - Option 5: Clear all logs

The log analysis will show counts of errors, warnings, meeting events, and recent error messages with timestamps.

### Relay Issues

#### **Light Turns ON at Startup (Active-HIGH Relay Fix)**
If your LED sign turns ON immediately when you plug in the Pico, you have an Active-HIGH relay. You have two options:

**Option 1: Software Fix (Recommended)**
Modify all relay commands in `main.py`:
- Find every `self.relay.on()` and change it to `self.relay.off()`
- Find every `self.relay.off()` and change it to `self.relay.on()`
- There are 6 locations to change:
  - Line ~29: In `__init__` (startup state)
  - Line ~264: When meeting starts
  - Line ~272: When meeting ends  
  - Lines ~286-289: Error flash function (2 changes)

**Option 2: Hardware Fix**
- Use the NC (Normally Closed) terminal instead of NO (Normally Open)
- This inverts the relay logic at the hardware level

#### **How to Test Your Relay Type**
In Thonny's shell, run:
```python
from machine import Pin
import time
relay = Pin(15, Pin.OUT)

print("Setting relay.on()")
relay.on()
time.sleep(2)

print("Setting relay.off()")
relay.off()
```

- **Active-LOW relay**: Light should be OFF after `.on()`, ON after `.off()`
- **Active-HIGH relay**: Light should be ON after `.on()`, OFF after `.off()`

#### **No Clicks Heard**
- Check wiring connections
- Ensure relay module has power (3.3V and GND connected)
- Verify GPIO pin 15 connection to relay IN

#### **Double-Click at Startup**
- Normal for some relays during initialization
- Not a problem if light ends up in correct state

### Connection Issues

If the sign fails to turn on for meetings:

1. **Check the logs first** - Run `view_logs.py` to identify the specific issue
2. **The system will automatically**:
   - Reconnect WiFi with exponential backoff (5s, 10s, 20s... up to 5 minutes)
   - Continue retrying indefinitely without giving up
   - Retry failed calendar fetches after 60 seconds
   - Use watchdog timer to recover from hangs (8-second timeout)
   - Reset backoff delay after successful reconnection

### Calendar Issues
- **Wrong timing**: Check logs for NTP sync failures
- **Missing events**: Review event filters in config.py and check logs for skipped events
- **Auth errors**: Delete `oauth_token.json` and re-authorize

### WiFi Issues
- **Disconnections**: Check logs for WiFi signal strength (logged every 5 minutes)
- **Can't connect**: Ensure 2.4GHz network (Pico W doesn't support 5GHz)
- **Wrong credentials**: Verify in `config_secrets.py`
- **Weak signal**: Logs will show warnings if signal < -80 dBm, consider moving Pico closer to router
- **Persistent disconnections**: System uses exponential backoff to retry indefinitely (never gives up)
- After reconnection, time is automatically resynced via NTP

## File Structure

```
/
├── main.py                    # Main program logic with self-healing capabilities
├── config.py                  # User settings
├── config_secrets.py          # WiFi and OAuth credentials (create from template)
├── config_secrets_template.py # Template for secrets file
├── oauth_handler.py           # OAuth2 implementation
├── logger.py                  # Persistent logging system with rotation
├── view_logs.py               # Interactive log viewer utility
├── oauth_token.json           # Saved auth token (auto-generated)
└── meeting_light.log          # System event logs (auto-generated)
```

## Security Notes

- Never commit `config_secrets.py` to version control (add to .gitignore)
- OAuth tokens are stored locally on the Pico W
- Calendar access is read-only
- Refresh tokens persist indefinitely unless revoked

## Maintenance

- **Tokens**: Automatically refresh, should work indefinitely
- **Updates**: Can modify code without re-authorizing
- **Revoke access**: Via Google Account settings → Security → Third-party apps

## Support for Different Relay Types

### Active-LOW Relays (Default - Code Configured for This)
Most common relay modules use Active-LOW triggering where:
- `relay.on()` (GPIO HIGH) = Relay OFF = Light OFF
- `relay.off()` (GPIO LOW) = Relay ON = Light ON

This seems backwards but is standard for optocoupler-based relay modules.

### Active-HIGH Relays (Requires Code Modification)
Less common, but if your relay uses Active-HIGH triggering:
- `relay.on()` (GPIO HIGH) = Relay ON = Light ON
- `relay.off()` (GPIO LOW) = Relay OFF = Light OFF

**If you have an Active-HIGH relay**, swap all `.on()` and `.off()` calls in main.py (see Troubleshooting section for details).

## License

MIT License - See LICENSE file for details

## Acknowledgments

Built with MicroPython and the Google Calendar API
### Active-LOW Relays (Default - Code Configured for This)
Most common relay modules use Active-LOW triggering where:
- `relay.on()` (GPIO HIGH) = Relay OFF = Light OFF
- `relay.off()` (GPIO LOW) = Relay ON = Light ON

This seems backwards but is standard for optocoupler-based relay modules.

### Active-HIGH Relays (Requires Code Modification)
Less common, but if your relay uses Active-HIGH triggering:
- `relay.on()` (GPIO HIGH) = Relay ON = Light ON
- `relay.off()` (GPIO LOW) = Relay OFF = Light OFF

**If you have an Active-HIGH relay**, swap all `.on()` and `.off()` calls in main.py (see Troubleshooting section for details).

## License

MIT License - See LICENSE file for details

## Acknowledgments

Built with MicroPython and the Google Calendar API