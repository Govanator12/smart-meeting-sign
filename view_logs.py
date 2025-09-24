# view_logs.py - Log viewer utility for Meeting Light Controller
# Run this on the Pico W to view recent logs

import os
import time

def view_logs(filename="meeting_light.log", lines=50):
    """View recent log entries"""
    print("\n" + "="*60)
    print("MEETING LIGHT CONTROLLER - LOG VIEWER")
    print("="*60)

    try:
        # Show available log files
        log_files = []
        for i in range(4):
            fname = f"{filename}.{i}" if i > 0 else filename
            try:
                stat = os.stat(fname)
                size = stat[6]
                log_files.append((fname, size))
                print(f"Found: {fname} ({size} bytes)")
            except:
                pass

        if not log_files:
            print("No log files found.")
            return

        print(f"\nShowing last {lines} lines from {filename}:\n")
        print("-"*60)

        # Read and display logs
        try:
            with open(filename, "r") as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

                for line in recent_lines:
                    print(line.rstrip())
        except Exception as e:
            print(f"Error reading log file: {e}")

        print("-"*60)
        print(f"\nTotal log entries shown: {len(recent_lines)}")

        # Show log statistics
        if log_files:
            total_size = sum(size for _, size in log_files)
            print(f"Total log size across all files: {total_size} bytes")

    except Exception as e:
        print(f"Error viewing logs: {e}")

def analyze_logs(filename="meeting_light.log"):
    """Analyze logs for common issues"""
    print("\n" + "="*60)
    print("LOG ANALYSIS")
    print("="*60)

    try:
        with open(filename, "r") as f:
            lines = f.readlines()

        # Count different types of messages
        errors = []
        warnings = []
        wifi_disconnects = 0
        oauth_failures = 0
        memory_errors = 0
        meeting_starts = 0
        meeting_ends = 0

        for line in lines:
            if "[ERROR]" in line:
                errors.append(line.rstrip())
                if "WiFi" in line:
                    wifi_disconnects += 1
                if "OAuth" in line or "auth" in line.lower():
                    oauth_failures += 1
                if "Memory" in line:
                    memory_errors += 1
            elif "[WARN]" in line:
                warnings.append(line.rstrip())
            elif "MEETING STARTED" in line:
                meeting_starts += 1
            elif "MEETING ENDED" in line:
                meeting_ends += 1

        # Display analysis
        print(f"\nLog Summary:")
        print(f"  Total lines: {len(lines)}")
        print(f"  Errors: {len(errors)}")
        print(f"  Warnings: {len(warnings)}")
        print(f"  Meeting starts: {meeting_starts}")
        print(f"  Meeting ends: {meeting_ends}")

        if wifi_disconnects > 0:
            print(f"\n⚠️  WiFi Issues:")
            print(f"  WiFi disconnections: {wifi_disconnects}")

        if oauth_failures > 0:
            print(f"\n⚠️  OAuth Issues:")
            print(f"  OAuth failures: {oauth_failures}")

        if memory_errors > 0:
            print(f"\n⚠️  Memory Issues:")
            print(f"  Memory errors: {memory_errors}")

        # Show recent errors
        if errors:
            print(f"\nRecent Errors (last 5):")
            for error in errors[-5:]:
                # Extract timestamp and message
                if "]" in error:
                    parts = error.split("]")
                    if len(parts) >= 3:
                        timestamp = parts[0].replace("[", "")
                        message = parts[2].strip()
                        print(f"  {timestamp}: {message[:60]}...")

        # Calculate uptime from first and last log entry
        if len(lines) >= 2:
            try:
                first_line = lines[0]
                last_line = lines[-1]

                # Extract timestamps
                first_time = first_line.split("]")[0].replace("[", "")
                last_time = last_line.split("]")[0].replace("[", "")

                print(f"\nLog Time Range:")
                print(f"  First entry: {first_time}")
                print(f"  Last entry:  {last_time}")
            except:
                pass

    except FileNotFoundError:
        print("No log file found. The device may not have created logs yet.")
    except Exception as e:
        print(f"Error analyzing logs: {e}")

def clear_logs(filename="meeting_light.log"):
    """Clear all log files"""
    print("\nClearing log files...")

    cleared = 0
    for i in range(4):
        fname = f"{filename}.{i}" if i > 0 else filename
        try:
            os.remove(fname)
            print(f"  Deleted: {fname}")
            cleared += 1
        except:
            pass

    print(f"Cleared {cleared} log file(s)")

def monitor_logs(filename="meeting_light.log", interval=5):
    """Live monitor of log file (tail -f equivalent)"""
    print("\n" + "="*60)
    print("LIVE LOG MONITOR (Press Ctrl+C to stop)")
    print("="*60 + "\n")

    try:
        # Get initial file size
        last_size = 0
        try:
            stat = os.stat(filename)
            last_size = stat[6]

            # Show last 10 lines to start
            with open(filename, "r") as f:
                lines = f.readlines()
                for line in lines[-10:]:
                    print(line.rstrip())
        except:
            print("Waiting for logs...")

        # Monitor for changes
        while True:
            try:
                stat = os.stat(filename)
                current_size = stat[6]

                if current_size > last_size:
                    # File has grown, show new content
                    with open(filename, "r") as f:
                        f.seek(last_size)
                        new_content = f.read()
                        print(new_content, end="")
                    last_size = current_size
                elif current_size < last_size:
                    # File was rotated
                    print("\n[Log file rotated]\n")
                    last_size = 0

            except:
                pass

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")

# Interactive menu
def main():
    """Interactive log viewer menu"""
    while True:
        print("\n" + "="*60)
        print("MEETING LIGHT LOG VIEWER")
        print("="*60)
        print("1. View recent logs (last 50 lines)")
        print("2. View recent logs (last 100 lines)")
        print("3. Analyze logs for issues")
        print("4. Monitor logs (live)")
        print("5. Clear all logs")
        print("6. Exit")
        print("-"*60)

        try:
            choice = input("Select option (1-6): ")

            if choice == "1":
                view_logs(lines=50)
            elif choice == "2":
                view_logs(lines=100)
            elif choice == "3":
                analyze_logs()
            elif choice == "4":
                monitor_logs()
            elif choice == "5":
                confirm = input("Are you sure you want to clear all logs? (y/n): ")
                if confirm.lower() == "y":
                    clear_logs()
            elif choice == "6":
                print("Goodbye!")
                break
            else:
                print("Invalid option. Please try again.")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()