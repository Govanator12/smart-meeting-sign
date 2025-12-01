# Smart Meeting Sign - Claude Context

## Project Overview

An automated LED sign controller for Raspberry Pi Pico W that turns on during Google Calendar meetings using OAuth2 authentication. The sign provides a visual indicator when you're in a meeting, perfect for home offices or shared workspaces.

## Key Technologies

- **Hardware**: Raspberry Pi Pico W (RP2040 microcontroller with WiFi)
- **Language**: MicroPython
- **APIs**: Google Calendar API (OAuth2 device flow)
- **Hardware Components**: 5V 1-Channel Active-LOW Relay, USB-powered LED sign

## Architecture

### Core Components

1. **[main.py](main.py)** - Main controller with self-healing capabilities
   - `MeetingLight` class handles the entire system lifecycle
   - WiFi connection management with exponential backoff
   - Calendar event polling and filtering
   - Relay control for LED sign
   - Watchdog timer for automatic recovery from hangs
   - Health monitoring (memory, WiFi signal strength)

2. **[oauth_handler.py](oauth_handler.py)** - OAuth2 authentication
   - Implements Google OAuth2 device flow
   - Manages token storage, refresh, and validation
   - Handles first-time authorization flow

3. **[logger.py](logger.py)** - Persistent logging system
   - File-based logging with automatic rotation (5000 lines max)
   - Log levels: INFO, WARNING, ERROR
   - Used throughout the system for diagnostics

4. **[config.py](config.py)** - Configuration settings
   - Calendar settings (refresh intervals, buffer times)
   - Event filtering rules (declined, all-day, OOO, colors)
   - Hardware pin definitions
   - OAuth2 endpoint URLs

5. **[config_secrets.py](config_secrets.py)** - Credentials (not in git)
   - WiFi SSID and password
   - Google OAuth2 Client ID and Secret
   - Created from [config_secrets_template.py](config_secrets_template.py)

6. **[view_logs.py](view_logs.py)** - Log viewing utility
   - Interactive log viewer for troubleshooting
   - Log analysis for common issues
   - Live log monitoring

7. **[web_logger.py](web_logger.py)** - Web server for remote log access (enabled by default)
   - HTTP server on port 8080
   - View logs from any device on the network
   - System health monitoring
   - Non-blocking, minimal overhead
   - Automatically starts when WiFi connects

## System Flow

### Initialization
1. Hardware setup (relay + LED pins)
2. Initialize web logger
3. WiFi connection with exponential backoff retry
4. Start web server on port 8080 (displays IP in console)
5. NTP time synchronization (UTC)
6. OAuth2 authentication (device flow on first run)
7. Start watchdog timer (8-second timeout)

### Main Loop
1. **Web Server Check** (every iteration)
   - Non-blocking check for incoming HTTP requests
   - Serve logs and health status on demand

2. **Calendar Fetch** (every 15 minutes by default)
   - Fetch events from Google Calendar API
   - Filter events based on config rules
   - Cache events locally
   - Log WiFi signal strength and memory usage

3. **Status Check** (every 10 seconds)
   - Check cached events against current time
   - Determine if currently in a meeting (with buffer)
   - Control relay accordingly (Active-LOW logic)
   - Feed watchdog timer

4. **Error Recovery**
   - WiFi disconnection: Automatic reconnection with exponential backoff (5s → 10s → 20s → ... → 5 min max)
   - Calendar fetch failure: Retry after 60 seconds
   - Time sync failure: Resync on WiFi reconnection
   - Watchdog timeout: Automatic system reset
   - Web server restarts automatically on WiFi reconnection

## Important Implementation Details

### Active-LOW Relay Logic
The code is configured for **Active-LOW relay modules** (most common type):
- `relay.on()` → GPIO HIGH → Relay OFF → Light OFF
- `relay.off()` → GPIO LOW → Relay ON → Light ON

This seems backwards but is standard for optocoupler-based relays. If your relay is Active-HIGH, you need to swap all `.on()` and `.off()` calls in [main.py](main.py).

### Event Filtering
Events are skipped if they meet any of these criteria:
- Response status is "declined"
- All-day events (no specific start time)
- Event type is "outOfOffice"
- Calendar color ID matches personal work (Tangerine/6) or focus time (Banana/5)

Filtering happens in the calendar fetch logic to reduce unnecessary relay switching.

### Time Handling
- All times are converted to UTC for consistency
- NTP synchronization on startup and after WiFi reconnection
- Daylight Saving Time is automatically handled via UTC
- Meeting buffer (default 2 minutes) applied to start/end times

### WiFi Resilience
- Exponential backoff for reconnection attempts (5s → 10s → 20s → 40s → ... → 5 min max)
- Never gives up trying to reconnect
- Backoff resets after successful connection
- Periodic WiFi health checks (every 60 seconds)
- Signal strength monitoring with warnings for weak signal (< -80 dBm)

### Memory Management
- Explicit garbage collection enabled
- Periodic GC calls to prevent memory fragmentation
- Memory usage logged every calendar refresh
- Critical for long-term stability on constrained hardware

### Relay State Logging
- **Every relay state change is logged** with precise timestamp and reason
- Includes meeting name that triggered the change
- Only logs when state actually changes (prevents log spam)
- Example: `RELAY -> ON (Meeting: Team Standup) at 14:30:15`
- Helps diagnose unexpected relay activations or "clicking" sounds
- Logs error flash sequences separately for easy identification

## File Locations and Pins

### Hardware Pins
- **GPIO 15 (Pin 20)**: Relay control signal
- **Built-in LED**: Status indicator
- **Pin 36 (3V3)**: Relay VCC
- **Pin 38 (GND)**: Relay GND
- **Pin 40 (VBUS)**: Relay common (5V source)

### File Storage (on Pico W)
- `oauth_token.json` - Persisted OAuth2 tokens (auto-generated)
- `meeting_light.log` - System event logs (auto-generated, max 50KB with rotation)

## LED Status Indicators

- **Quick blink** (every 10s): Checking calendar status
- **Triple blink**: Fetching fresh calendar data
- **Solid on**: Currently in a meeting
- **Off**: No meeting
- **Slow flash** (3 times): Error condition

## Configuration Options

### Timing Settings
- `CALENDAR_REFRESH_INTERVAL` (900s / 15 min): How often to fetch from Google Calendar
- `STATUS_CHECK_INTERVAL` (10s): How often to check cached events
- `MEETING_BUFFER_MINUTES` (2 min): Early start / late end buffer

### Event Filters
- `IGNORE_DECLINED` (True): Skip declined meetings
- `IGNORE_ALL_DAY` (True): Skip all-day events
- `IGNORE_OOO` (True): Skip Out of Office
- `PERSONAL_WORK_COLOR_ID` ("6"): Skip Tangerine colored events
- `FOCUS_TIME_COLOR_ID` ("5"): Skip Banana colored events

## Development Tips

### Testing Relay Type
Run this in Thonny's shell to determine if your relay is Active-LOW or Active-HIGH:
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

### Viewing Logs

#### Option 1: USB Connection (Simplest)
Use [view_logs.py](view_logs.py) in Thonny to diagnose issues:
- View recent log entries (50/100 lines)
- Analyze logs for common problems
- Live log monitoring
- Clear logs

#### Option 2: Remote Access (WiFi)
The web UI is **enabled by default** - no setup required!
- **Access logs from any device** on the same network
- Visit `http://<pico-ip>:8080/` in your browser (IP shown in console on boot)
- **Real-time viewing** without USB connection
- **Health monitoring** page shows memory and system status
- **Color-coded logs** with highlighted relay changes
- **Historical logs** - see what happened in the past

Perfect for:
- Pico is mounted in an inconvenient location
- Want to monitor logs in real-time during operation
- Investigating intermittent issues (like random relay clicks)
- Monitoring from another room or device
- Quick checks from your phone

### Common Modification Points

1. **Change relay behavior**: Modify the `set_relay()` method in [main.py](main.py)
   - The new centralized relay control makes this easier
   - Swap "ON" and "OFF" logic in the `set_relay()` method around line 91-111
   - All relay changes now go through this single method

2. **Adjust timing**: Modify constants in [config.py](config.py)

3. **Change event filtering**: Edit filter conditions in [config.py](config.py)

4. **Modify hardware pins**: Update `RELAY_PIN` and `LED_PIN` in [config.py](config.py)

5. **Disable web server**: Remove or comment out web logger initialization and calls in [main.py](main.py) if you don't need remote access

## Security Considerations

- `config_secrets.py` must NEVER be committed to version control
- OAuth tokens stored locally on device (not transmitted)
- Calendar access is read-only (scope: `calendar.readonly`)
- Refresh tokens persist indefinitely unless revoked via Google Account settings
- Device uses OAuth2 device flow (suitable for limited input devices)
- **Web UI**: Not password protected. Only use on trusted networks. Logs may contain meeting names/attendees. Don't expose port 8080 to the internet.

## Known Limitations

- Pico W only supports 2.4GHz WiFi (not 5GHz)
- MicroPython memory constraints (~100KB free RAM typical)
- Calendar refresh limited to 15-minute intervals to reduce API calls
- No support for multiple calendars (uses primary by default)
- Relies on internet connectivity (no offline mode)

## Troubleshooting Guide

### Random Relay Clicks / Unexpected Activations

**NEW**: Enhanced logging now tracks every relay state change!

1. **Note the time** when you hear a click
2. **Check logs** (USB or web interface)
3. **Look for relay state changes** around that time:
   ```
   [2025-12-01 14:30:15] [INFO] RELAY -> ON (Meeting: Team Standup) at 14:30:15
   [2025-12-01 14:30:17] [INFO] RELAY -> OFF (Meeting ended) at 14:30:17
   ```
4. **Common causes**:
   - Meeting events with very short durations
   - Calendar events being added/removed rapidly
   - Time sync issues causing time jumps
   - Error flash sequences (check for warnings/errors in logs)
   - WiFi reconnections triggering calendar refetch

If clicks happen at random times with no corresponding log entry, this could indicate a hardware issue with the relay.

### Light doesn't turn on during meetings
1. Check logs using [view_logs.py](view_logs.py) or web UI
2. Search for "RELAY ->" to see all state changes
3. Verify WiFi connection and signal strength
4. Confirm OAuth token is valid (check for auth errors in logs)
5. Check event filters aren't excluding the meeting
6. Verify NTP time sync succeeded

### Light stays on when it shouldn't
1. Check relay type (Active-LOW vs Active-HIGH)
2. Search logs for "RELAY ->" to see last state change
3. Review cached events in logs
4. Verify meeting buffer settings
5. Check for calendar sync issues

### WiFi keeps disconnecting
1. Check signal strength in logs (warnings if < -80 dBm)
2. Move Pico closer to router
3. Ensure 2.4GHz network is available
4. System will auto-reconnect with exponential backoff

### System hangs or freezes
- Watchdog timer will automatically reset system after 8 seconds
- Check logs after restart for error patterns

### Can't Access Web UI
1. Check Pico's IP address in logs or serial output
2. Ensure your device is on the same WiFi network
3. Try `http://192.168.1.x:8080` (include port :8080)
4. Verify web_logger.py is uploaded and integrated
5. Check logs for "Web UI available at..." message

## OAuth2 Setup Checklist

1. Create Google Cloud project
2. Enable Google Calendar API
3. Configure OAuth consent screen (External, add test user)
4. Create credentials (TVs and Limited Input devices)
5. Copy Client ID and Client Secret to [config_secrets.py](config_secrets.py)
6. On first run, visit google.com/device and enter code shown in logs
7. Authorize with Google account
8. System saves refresh token for permanent access

## Maintenance

- **No regular maintenance required** - tokens auto-refresh
- **Code updates** - Can modify without re-authorizing
- **Revoke access** - Via Google Account → Security → Third-party apps
- **Log rotation** - Automatic at 5000 lines
- **Memory management** - Automatic garbage collection

## Contributing

When modifying this project:
- Test WiFi resilience by temporarily disconnecting router
- Verify relay behavior with actual hardware
- Check log output for error patterns
- Test OAuth flow from scratch (delete `oauth_token.json`)
- Monitor memory usage over extended periods
- Ensure changes work with both Active-LOW and Active-HIGH relays (or document requirements)
