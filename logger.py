# logger.py - Persistent logging for Meeting Light Controller
import time
import gc
import os

class Logger:
    def __init__(self, filename="meeting_light.log", max_size=50000, max_files=3):
        self.filename = filename
        self.max_size = max_size
        self.max_files = max_files
        self.current_size = 0

        # Check existing log size
        try:
            stat = os.stat(self.filename)
            self.current_size = stat[6]
        except:
            self.current_size = 0

    def _rotate_logs(self):
        """Rotate log files when max size is reached"""
        try:
            # Delete oldest backup if it exists
            try:
                os.remove(f"{self.filename}.{self.max_files}")
            except:
                pass

            # Rotate existing backups
            for i in range(self.max_files - 1, 0, -1):
                try:
                    os.rename(f"{self.filename}.{i}", f"{self.filename}.{i+1}")
                except:
                    pass

            # Move current log to .1
            try:
                os.rename(self.filename, f"{self.filename}.1")
            except:
                pass

            self.current_size = 0
        except Exception as e:
            print(f"Log rotation error: {e}")

    def log(self, level, message):
        """Write log message to file and console"""
        try:
            # Format timestamp
            t = time.localtime()
            timestamp = f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"

            # Create log entry
            log_entry = f"[{timestamp}] [{level}] {message}\n"

            # Print to console
            print(f"[{level}] {message}")

            # Check if rotation is needed
            if self.current_size > self.max_size:
                self._rotate_logs()

            # Write to file
            with open(self.filename, "a") as f:
                f.write(log_entry)
                self.current_size += len(log_entry)

            # Periodic garbage collection
            gc.collect()

        except Exception as e:
            print(f"Logging error: {e}")

    def info(self, message):
        self.log("INFO", message)

    def error(self, message):
        self.log("ERROR", message)

    def warning(self, message):
        self.log("WARN", message)

    def debug(self, message):
        self.log("DEBUG", message)

    def get_logs(self, lines=50):
        """Read last N lines from log file"""
        try:
            with open(self.filename, "r") as f:
                all_lines = f.readlines()
                return all_lines[-lines:] if len(all_lines) > lines else all_lines
        except:
            return ["No logs available\n"]

    def clear_logs(self):
        """Clear all log files"""
        try:
            for i in range(self.max_files + 1):
                filename = f"{self.filename}.{i}" if i > 0 else self.filename
                try:
                    os.remove(filename)
                except:
                    pass
            self.current_size = 0
            self.info("Logs cleared")
        except Exception as e:
            print(f"Error clearing logs: {e}")