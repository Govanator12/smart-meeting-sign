# web_logger.py - Simple HTTP server for remote log access
import socket
import time
import gc

class WebLogger:
    """
    Simple web server to access logs remotely
    Access via: http://<pico-ip-address>:8080/
    """

    def __init__(self, logger, port=8080):
        self.logger = logger
        self.port = port
        self.socket = None

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

                    # Route the request
                    if path == '/' or path == '/logs':
                        self.serve_logs(cl, lines=100)
                    elif path.startswith('/logs/'):
                        # Extract line count from path like /logs/200
                        try:
                            num_lines = int(path.split('/')[2])
                            self.serve_logs(cl, lines=num_lines)
                        except:
                            self.serve_logs(cl, lines=100)
                    elif path == '/logs/live':
                        self.serve_live_logs(cl)
                    elif path == '/health':
                        self.serve_health(cl)
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

    def serve_logs(self, client, lines=100):
        """Serve log file contents as HTML"""
        try:
            logs = self.logger.get_logs(lines=lines)

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
        .nav a {{
            color: #4ec9b0;
            margin-right: 15px;
            text-decoration: none;
            padding: 5px 10px;
            border: 1px solid #4ec9b0;
            border-radius: 3px;
        }}
        .nav a:hover {{ background: #2d2d30; }}
        .timestamp {{ color: #858585; }}
        .relay {{ color: #ce9178; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>Meeting Light Logs</h1>
    <div class="nav">
        <a href="/logs/50">Last 50</a>
        <a href="/logs/100">Last 100</a>
        <a href="/logs/200">Last 200</a>
        <a href="/logs/500">Last 500</a>
        <a href="/health">Health</a>
        <a href="/" onclick="location.reload(); return false;">Refresh</a>
    </div>
    <div>Showing last {lines} lines (most recent at bottom):</div>
    <hr>
    <div class="logs">
"""

            # Add log lines with syntax highlighting
            for line in logs:
                line = line.rstrip()

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

    def serve_health(self, client):
        """Serve system health information"""
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
    <div class="nav"><a href="/logs">View Logs</a></div>
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
        <div class="value">{time.localtime()}</div>
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
