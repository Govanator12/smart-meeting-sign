# web_logger.py - Simple HTTP server for remote log access with timezone support
import socket
import time
import gc
import re

class WebLogger:
    """
    Simple web server to access logs remotely
    Access via: http://<pico-ip-address>:8080/
    """

    # Common timezone definitions (offset in hours from UTC)
    TIMEZONES = {
        'UTC': 0,
        'EST': -5,
        'EDT': -4,
        'CST': -6,
        'CDT': -5,
        'MST': -7,
        'MDT': -6,
        'PST': -8,
        'PDT': -7,
        'GMT': 0,
        'CET': 1,
        'JST': 9,
        'AEST': 10,
    }

    def __init__(self, logger, port=8080, timezone_offset=0):
        self.logger = logger
        self.port = port
        self.socket = None
        self.timezone_offset = timezone_offset  # Hours offset from UTC

    def start(self):
        """Start the web server (non-blocking)"""
        try:
            # Create socket
            addr = socket.getaddrinfo('0.0.0.0', self.port)[0][-1]
            self.socket = socket.socket()
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(addr)
            self.socket.listen(1)
            self.socket.setblocking(False)  # Non-blocking mode

            print(f"Web logger started on port {self.port}")
            return True
        except Exception as e:
            print(f"Failed to start web logger: {e}")
            return False

    def convert_timestamp(self, log_line, offset):
        """Convert timestamp in log line from UTC to specified timezone offset"""
        # Match timestamp pattern: [YYYY-MM-DD HH:MM:SS]
        pattern = r'\[(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\]'
        match = re.search(pattern, log_line)

        if not match:
            return log_line

        try:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            second = int(match.group(6))

            # Convert to epoch, add offset, convert back
            # Note: This is a simplified conversion that doesn't handle DST or month boundaries perfectly
            new_hour = hour + offset
            new_day = day
            new_month = month
            new_year = year

            # Handle day overflow/underflow
            if new_hour >= 24:
                new_hour -= 24
                new_day += 1
            elif new_hour < 0:
                new_hour += 24
                new_day -= 1

            # Handle month overflow (simplified - assumes 28-31 days)
            days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            if new_day > days_in_month[month - 1]:
                new_day = 1
                new_month += 1
                if new_month > 12:
                    new_month = 1
                    new_year += 1
            elif new_day < 1:
                new_month -= 1
                if new_month < 1:
                    new_month = 12
                    new_year -= 1
                new_day = days_in_month[new_month - 1]

            new_timestamp = f"[{new_year:04d}-{new_month:02d}-{new_day:02d} {new_hour:02d}:{minute:02d}:{second:02d}]"
            return log_line.replace(match.group(0), new_timestamp)
        except:
            return log_line

    def get_timezone_name(self, offset):
        """Get timezone name from offset"""
        for name, tz_offset in self.TIMEZONES.items():
            if tz_offset == offset:
                return name
        if offset >= 0:
            return f"UTC+{offset}"
        else:
            return f"UTC{offset}"

    def check_requests(self):
        """Check for incoming requests (call this in your main loop)"""
        if not self.socket:
            return

        try:
            # Try to accept a connection (non-blocking)
            cl, addr = self.socket.accept()
            print(f"Web request from {addr}")

            # Set client socket to blocking for this request
            cl.setblocking(True)
            cl.settimeout(2.0)

            # Read request
            try:
                request = cl.recv(1024).decode('utf-8')

                # Parse request path
                lines = request.split('\n')
                if len(lines) > 0:
                    path = lines[0].split()[1] if len(lines[0].split()) > 1 else '/'

                    # Parse query parameters for timezone
                    tz_offset = self.timezone_offset
                    if '?' in path:
                        path_part, query = path.split('?', 1)
                        for param in query.split('&'):
                            if param.startswith('tz='):
                                try:
                                    tz_offset = int(param.split('=')[1])
                                except:
                                    pass
                        path = path_part

                    # Route the request
                    if path == '/' or path == '/logs':
                        self.serve_logs(cl, lines=100, tz_offset=tz_offset)
                    elif path.startswith('/logs/'):
                        # Extract line count from path like /logs/200
                        try:
                            num_lines = int(path.split('/')[2])
                            self.serve_logs(cl, lines=num_lines, tz_offset=tz_offset)
                        except:
                            self.serve_logs(cl, lines=100, tz_offset=tz_offset)
                    elif path == '/logs/live':
                        self.serve_live_logs(cl)
                    elif path == '/health':
                        self.serve_health(cl, tz_offset=tz_offset)
                    else:
                        self.serve_404(cl)
            except Exception as e:
                print(f"Error handling request: {e}")

            cl.close()
            gc.collect()

        except OSError:
            # No connection available (EAGAIN/EWOULDBLOCK in non-blocking mode)
            pass
        except Exception as e:
            print(f"Web server error: {e}")

    def serve_logs(self, client, lines=100, tz_offset=None):
        """Serve log file contents as HTML with timezone conversion"""
        if tz_offset is None:
            tz_offset = self.timezone_offset

        try:
            logs = self.logger.get_logs(lines=lines)
            tz_name = self.get_timezone_name(tz_offset)

            # Build timezone selector options
            tz_options = ""
            for name, offset in sorted(self.TIMEZONES.items(), key=lambda x: x[1]):
                selected = "selected" if offset == tz_offset else ""
                sign = "+" if offset >= 0 else ""
                tz_options += f'<option value="{offset}" {selected}>{name} (UTC{sign}{offset})</option>\n'

            html = f"""HTTP/1.1 200 OK
Content-Type: text/html
Connection: close

<!DOCTYPE html>
<html>
<head>
    <title>Meeting Light Logs</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: monospace;
            background: #1e1e1e;
            color: #d4d4d4;
            margin: 20px;
            font-size: 12px;
        }}
        h1 {{ color: #4ec9b0; }}
        .log-line {{ margin: 2px 0; white-space: pre-wrap; word-wrap: break-word; }}
        .ERROR {{ color: #f48771; }}
        .WARN {{ color: #dcdcaa; }}
        .INFO {{ color: #4fc1ff; }}
        .DEBUG {{ color: #b5cea8; }}
        .nav {{ margin: 20px 0; }}
        .nav a, .nav select {{
            color: #4ec9b0;
            margin-right: 15px;
            text-decoration: none;
            padding: 5px 10px;
            border: 1px solid #4ec9b0;
            border-radius: 3px;
            background: #1e1e1e;
        }}
        .nav a:hover {{ background: #2d2d30; }}
        .nav select {{ cursor: pointer; }}
        .timestamp {{ color: #858585; }}
        .relay {{ color: #ce9178; font-weight: bold; }}
        .tz-label {{ color: #858585; margin-right: 5px; }}
        .tz-display {{ color: #dcdcaa; font-weight: bold; }}
    </style>
    <script>
        function changeTimezone(offset) {{
            var url = window.location.pathname;
            window.location.href = url + '?tz=' + offset;
        }}
    </script>
</head>
<body>
    <h1>Meeting Light Logs</h1>
    <div class="nav">
        <a href="/logs/50?tz={tz_offset}">Last 50</a>
        <a href="/logs/100?tz={tz_offset}">Last 100</a>
        <a href="/logs/200?tz={tz_offset}">Last 200</a>
        <a href="/logs/500?tz={tz_offset}">Last 500</a>
        <a href="/health?tz={tz_offset}">Health</a>
        <a href="#" onclick="location.reload(); return false;">Refresh</a>
    </div>
    <div style="margin: 15px 0;">
        <span class="tz-label">Timezone:</span>
        <select onchange="changeTimezone(this.value)">
            {tz_options}
        </select>
        <span class="tz-display" style="margin-left: 10px;">Showing times in {tz_name}</span>
    </div>
    <div>Showing last {lines} lines (most recent at bottom):</div>
    <hr>
    <div class="logs">
"""

            # Add log lines with syntax highlighting and timezone conversion
            for line in logs:
                line = line.rstrip()

                # Convert timestamp to selected timezone
                line = self.convert_timestamp(line, tz_offset)

                # Highlight relay changes
                if "RELAY ->" in line:
                    html += f'<div class="log-line relay">{self.escape_html(line)}</div>\n'
                else:
                    # Color code by log level
                    css_class = "log-line"
                    if "[ERROR]" in line:
                        css_class += " ERROR"
                    elif "[WARN]" in line:
                        css_class += " WARN"
                    elif "[INFO]" in line:
                        css_class += " INFO"
                    elif "[DEBUG]" in line:
                        css_class += " DEBUG"

                    html += f'<div class="{css_class}">{self.escape_html(line)}</div>\n'

            html += """
    </div>
    <hr>
    <div style="margin-top: 20px; color: #858585;">
        Auto-refresh: <button onclick="setInterval(() => location.reload(), 5000)">Enable (5s)</button>
    </div>
</body>
</html>
"""
            client.send(html.encode('utf-8'))

        except Exception as e:
            print(f"Error serving logs: {e}")
            self.serve_error(client, str(e))

    def serve_health(self, client, tz_offset=None):
        """Serve system health information"""
        if tz_offset is None:
            tz_offset = self.timezone_offset

        try:
            import machine

            # Get memory info
            free_mem = gc.mem_free()

            # Get log file size
            log_size = 0
            try:
                import os
                stat = os.stat(self.logger.filename)
                log_size = stat[6]
            except:
                pass

            # Get current time and convert to display timezone
            t = time.localtime()
            display_hour = (t[3] + tz_offset) % 24
            tz_name = self.get_timezone_name(tz_offset)

            html = f"""HTTP/1.1 200 OK
Content-Type: text/html
Connection: close

<!DOCTYPE html>
<html>
<head>
    <title>Meeting Light Health</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: monospace;
            background: #1e1e1e;
            color: #d4d4d4;
            margin: 20px;
        }}
        h1 {{ color: #4ec9b0; }}
        .metric {{
            margin: 15px 0;
            padding: 10px;
            background: #2d2d30;
            border-left: 3px solid #4ec9b0;
        }}
        .label {{ color: #858585; }}
        .value {{ color: #4fc1ff; font-size: 18px; }}
        .nav a {{
            color: #4ec9b0;
            text-decoration: none;
            padding: 5px 10px;
            border: 1px solid #4ec9b0;
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    <h1>System Health</h1>
    <div class="nav"><a href="/logs?tz={tz_offset}">View Logs</a></div>
    <div class="metric">
        <div class="label">Free Memory</div>
        <div class="value">{free_mem:,} bytes</div>
    </div>
    <div class="metric">
        <div class="label">Log File Size</div>
        <div class="value">{log_size:,} bytes</div>
    </div>
    <div class="metric">
        <div class="label">Current Time (UTC)</div>
        <div class="value">{t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}</div>
    </div>
    <div class="metric">
        <div class="label">Current Time ({tz_name})</div>
        <div class="value">{t[0]}-{t[1]:02d}-{t[2]:02d} {display_hour:02d}:{t[4]:02d}:{t[5]:02d}</div>
    </div>
</body>
</html>
"""
            client.send(html.encode('utf-8'))

        except Exception as e:
            print(f"Error serving health: {e}")
            self.serve_error(client, str(e))

    def serve_404(self, client):
        """Serve 404 page"""
        html = """HTTP/1.1 404 Not Found
Content-Type: text/html
Connection: close

<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body>
    <h1>404 Not Found</h1>
    <p>Available paths:</p>
    <ul>
        <li><a href="/logs">/logs</a> - View logs</li>
        <li><a href="/health">/health</a> - System health</li>
    </ul>
</body>
</html>
"""
        client.send(html.encode('utf-8'))

    def serve_error(self, client, error_msg):
        """Serve error page"""
        html = f"""HTTP/1.1 500 Internal Server Error
Content-Type: text/html
Connection: close

<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body>
    <h1>Error</h1>
    <pre>{self.escape_html(error_msg)}</pre>
</body>
</html>
"""
        client.send(html.encode('utf-8'))

    def escape_html(self, text):
        """Escape HTML special characters"""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))

    def stop(self):
        """Stop the web server"""
        if self.socket:
            self.socket.close()
            self.socket = None
            print("Web logger stopped")
