import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


# ============================================================
# PATHS / GLOBAL CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_FILE = BASE_DIR / "system_config.json"
LOG_FILE = BASE_DIR / "system_health.log"
HEALTH_FILE = BASE_DIR / "system_health.json"
HISTORY_FILE = BASE_DIR / "system_health_history.json"
ALERT_STATE_FILE = BASE_DIR / "system_alert_state.json"


# Runtime configuration.
# These are initialized by initialize_config().
CPU_THRESHOLD = None
MEMORY_THRESHOLD = None
DISK_THRESHOLD = None
COMMAND_TIMEOUT = None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True
)


# ============================================================
# CONFIGURATION
# ============================================================

def load_config(filename):
    """Load JSON configuration."""

    try:
        with open(filename, "r") as file:
            return json.load(file)

    except FileNotFoundError:
        logging.error(
            "Configuration file not found: %s",
            filename
        )
        print("ERROR: Configuration file not found:", filename)
        return None

    except json.JSONDecodeError:
        logging.error(
            "Invalid JSON configuration: %s",
            filename
        )
        print("ERROR: Invalid JSON configuration:", filename)
        return None

    except OSError as e:
        logging.error(
            "Unable to read configuration: %s | error=%s",
            filename,
            e
        )
        print("ERROR: Unable to read configuration:", filename)
        return None


def validate_config(config):
    """Validate configuration values."""

    required_keys = [
        "cpu_threshold",
        "memory_threshold",
        "disk_threshold",
        "command_timeout"
    ]

    if not isinstance(config, dict):
        print("ERROR: Configuration must be a JSON object")
        logging.error("Configuration is not a dictionary")
        return False

    # Check required keys and numeric values.
    for key in required_keys:

        if key not in config:
            print("ERROR: Missing configuration:", key)
            logging.error(
                "Missing configuration: %s",
                key
            )
            return False

        # bool is technically a subclass of int in Python.
        if (
            isinstance(config[key], bool)
            or not isinstance(config[key], (int, float))
        ):
            print(
                "ERROR: Configuration must be a number:",
                key
            )
            logging.error(
                "Invalid configuration type: %s=%s",
                key,
                config[key]
            )
            return False

    # Validate percentage thresholds.
    for key in [
        "cpu_threshold",
        "memory_threshold",
        "disk_threshold"
    ]:

        if config[key] < 0 or config[key] > 100:
            print(
                "ERROR: Configuration must be between 0 and 100:",
                key
            )
            logging.error(
                "Configuration out of range: %s=%s",
                key,
                config[key]
            )
            return False

    # Validate command timeout.
    if config["command_timeout"] <= 0:
        print("ERROR: Command timeout must be greater than 0")
        logging.error(
            "Invalid command timeout: %s",
            config["command_timeout"]
        )
        return False

    return True


def initialize_config():
    """Load and initialize runtime configuration."""

    global CPU_THRESHOLD
    global MEMORY_THRESHOLD
    global DISK_THRESHOLD
    global COMMAND_TIMEOUT

    config = load_config(CONFIG_FILE)

    if config is None:
        return False

    if not validate_config(config):
        return False

    CPU_THRESHOLD = config["cpu_threshold"]
    MEMORY_THRESHOLD = config["memory_threshold"]
    DISK_THRESHOLD = config["disk_threshold"]
    COMMAND_TIMEOUT = config["command_timeout"]

    return True


# ============================================================
# ATOMIC JSON WRITE
# ============================================================

def save_json_atomic(data, filename):
    """
    Safely write JSON using a temporary file and atomic replace.

    The temporary file is created with restrictive permissions.
    """

    filename = Path(filename)
    temp_file = Path(str(filename) + ".tmp")

    try:

        with open(temp_file, "w") as file:
            json.dump(
                data,
                file,
                indent=4
            )
            file.flush()
            os.fsync(file.fileno())

        os.chmod(temp_file, 0o600)

        temp_file.replace(filename)

        return True

    except (OSError, TypeError, ValueError) as e:

        print(
            "ERROR: Unable to save JSON file:",
            filename
        )

        logging.error(
            "Unable to save JSON file: %s | error=%s",
            filename,
            e
        )

        try:
            if temp_file.exists():
                temp_file.unlink()
        except OSError as cleanup_error:
            logging.error(
                "Unable to remove temporary file: %s | error=%s",
                temp_file,
                cleanup_error
            )

        return False


# ============================================================
# HISTORY
# ============================================================

def save_history(report, filename):
    """Append report to history and retain the latest 100 entries."""

    try:

        with open(filename, "r") as file:
            history = json.load(file)

    except FileNotFoundError:

        history = []

    except json.JSONDecodeError:

        print("ERROR: Invalid history file")

        logging.error(
            "Invalid history file: %s",
            filename
        )

        return False

    except OSError as e:

        print("ERROR: Unable to read history file")

        logging.error(
            "Unable to read history file: %s | error=%s",
            filename,
            e
        )

        return False

    if not isinstance(history, list):

        logging.error(
            "History file does not contain a JSON list: %s",
            filename
        )

        return False

    history.append(report)

    # Keep only the latest 100 records.
    history = history[-100:]

    return save_json_atomic(
        history,
        filename
    )


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(command):
    """Execute a Linux command with timeout and error handling."""

    if not command:
        logging.error("Empty command received")
        return None

    if COMMAND_TIMEOUT is None:
        logging.error(
            "COMMAND_TIMEOUT is not initialized"
        )
        return None

    try:

        start_time = time.time()

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=COMMAND_TIMEOUT
        )

        duration = time.time() - start_time

        logging.info(
            "Command executed successfully: %s | duration=%.3f seconds",
            command[0],
            duration
        )

        return result.stdout.strip()

    except FileNotFoundError:

        print(
            "ERROR: Command not found:",
            command[0]
        )

        logging.error(
            "Command not found: %s",
            command[0]
        )

        return None

    except subprocess.CalledProcessError as e:

        error_message = (
            e.stderr.strip()
            if e.stderr
            else "No error message"
        )

        print(
            "ERROR: Command failed:",
            command[0]
        )
        print(
            "Return code:",
            e.returncode
        )
        print(
            "Error:",
            error_message
        )

        logging.error(
            "Command failed: %s | return code=%s | error=%s",
            command[0],
            e.returncode,
            error_message
        )

        return None

    except subprocess.TimeoutExpired:

        print(
            "ERROR: Command timed out:",
            command[0]
        )

        logging.error(
            "Command timed out: %s | timeout=%s seconds",
            command[0],
            COMMAND_TIMEOUT
        )

        return None

    except OSError as e:

        print(
            "ERROR: Unable to execute command:",
            command[0]
        )

        logging.error(
            "Unable to execute command: %s | error=%s",
            command[0],
            e
        )

        return None


# ============================================================
# HOSTNAME
# ============================================================

def get_hostname():

    return run_command(
        ["hostname"]
    )


# ============================================================
# KERNEL
# ============================================================

def get_kernel():

    return run_command(
        ["uname", "-r"]
    )


# ============================================================
# CPU
# ============================================================

def get_cpu_usage():
    """
    Calculate CPU usage using /proc/stat.

    This avoids depending on the formatting of `top`.
    """

    try:

        with open("/proc/stat", "r") as file:

            first_line = file.readline().strip()

        if not first_line.startswith("cpu "):

            print("ERROR: CPU information not found")

            logging.error(
                "CPU information not found in /proc/stat"
            )

            return None

        values = first_line.split()[1:]

        if len(values) < 4:

            print("ERROR: Invalid CPU information")

            logging.error(
                "Invalid CPU information in /proc/stat"
            )

            return None

        values = [int(value) for value in values]

        user = values[0]
        nice = values[1]
        system = values[2]
        idle = values[3]

        iowait = values[4] if len(values) > 4 else 0
        irq = values[5] if len(values) > 5 else 0
        softirq = values[6] if len(values) > 6 else 0
        steal = values[7] if len(values) > 7 else 0

        idle_time = idle + iowait

        total_time = (
            user
            + nice
            + system
            + idle
            + iowait
            + irq
            + softirq
            + steal
        )

        if total_time <= 0:

            print("ERROR: Invalid CPU timing information")

            logging.error(
                "Invalid CPU timing information"
            )

            return None

        cpu_usage = (
            (total_time - idle_time)
            / total_time
        ) * 100

        return max(
            0.0,
            min(100.0, cpu_usage)
        )

    except FileNotFoundError:

        print("ERROR: /proc/stat not found")

        logging.error(
            "/proc/stat not found"
        )

        return None

    except (ValueError, IndexError):

        print("ERROR: Unable to parse CPU information")

        logging.error(
            "Unable to parse CPU information"
        )

        return None

    except OSError as e:

        print("ERROR: Unable to read CPU information")

        logging.error(
            "Unable to read /proc/stat: %s",
            e
        )

        return None


# ============================================================
# MEMORY
# ============================================================

def get_memory_usage():

    output = run_command(
        ["free", "-m"]
    )

    if output is None:
        return None

    try:

        lines = output.splitlines()

        memory_line = None

        for line in lines:

            if line.startswith("Mem:"):

                memory_line = line
                break

        if memory_line is None:

            print("ERROR: Memory information not found")

            logging.error(
                "Memory information not found"
            )

            return None

        memory_info = memory_line.split()

        if len(memory_info) < 7:

            print("ERROR: Invalid memory information")

            logging.error(
                "Invalid memory information"
            )

            return None

        total_memory = int(memory_info[1])
        available_memory = int(memory_info[6])

        if total_memory <= 0:

            print("ERROR: Invalid total memory")

            logging.error(
                "Total memory is zero or negative"
            )

            return None

        memory_usage = (
            (total_memory - available_memory)
            / total_memory
        ) * 100

        return max(
            0.0,
            min(100.0, memory_usage)
        )

    except (ValueError, IndexError, ZeroDivisionError):

        print(
            "ERROR: Unable to parse memory information"
        )

        logging.error(
            "Unable to parse memory information"
        )

        return None


# ============================================================
# DISK
# ============================================================

def get_disk_usage():

    output = run_command(
        ["df", "-hP"]
    )

    if output is None:
        return None

    filesystems = []

    try:

        lines = output.splitlines()

        for line in lines[1:]:

            parts = line.split()

            if len(parts) < 6:
                continue

            filesystem = parts[0]

            try:
                usage = int(
                    parts[4].strip("%")
                )
            except ValueError:
                logging.warning(
                    "Unable to parse disk usage: %s",
                    line
                )
                continue

            mountpoint = parts[5]

            # Ignore virtual/temporary filesystems.
            if filesystem.startswith(
                ("tmpfs", "devtmpfs", "efivarfs")
            ):
                continue

            filesystems.append(
                {
                    "filesystem": filesystem,
                    "mountpoint": mountpoint,
                    "usage": usage
                }
            )

        if not filesystems:

            logging.error(
                "No usable filesystems found"
            )

            return None

        return filesystems

    except (ValueError, IndexError):

        print(
            "ERROR: Unable to parse disk information"
        )

        logging.error(
            "Unable to parse disk information"
        )

        return None


# ============================================================
# HEALTH CHECK
# ============================================================

def check_health(
    cpu_usage,
    memory_usage,
    disk_usage
):

    issues = []

    # --------------------------------------------------------
    # CPU
    # --------------------------------------------------------

    if cpu_usage is None:

        cpu_status = "ERROR"

        issues.append(
            "CPU information unavailable"
        )

    elif cpu_usage <= CPU_THRESHOLD:

        cpu_status = "OK"

    else:

        cpu_status = "WARNING"

        issues.append(
            f"CPU usage {cpu_usage:.1f}% exceeds "
            f"threshold {CPU_THRESHOLD}%"
        )

    # --------------------------------------------------------
    # Memory
    # --------------------------------------------------------

    if memory_usage is None:

        memory_status = "ERROR"

        issues.append(
            "Memory information unavailable"
        )

    elif memory_usage <= MEMORY_THRESHOLD:

        memory_status = "OK"

    else:

        memory_status = "WARNING"

        issues.append(
            f"Memory usage {memory_usage:.1f}% exceeds "
            f"threshold {MEMORY_THRESHOLD}%"
        )

    # --------------------------------------------------------
    # Disk
    # --------------------------------------------------------

    if disk_usage is None:

        disk_status = "ERROR"

        issues.append(
            "Disk information unavailable"
        )

    else:

        disk_status = "OK"

        for filesystem in disk_usage:

            usage = filesystem["usage"]
            mountpoint = filesystem["mountpoint"]

            if usage > DISK_THRESHOLD:

                disk_status = "WARNING"

                issues.append(
                    f"Disk usage {usage}% exceeds "
                    f"threshold {DISK_THRESHOLD}% "
                    f"on {mountpoint}"
                )

    # --------------------------------------------------------
    # Overall status
    # --------------------------------------------------------

    statuses = [
        cpu_status,
        memory_status,
        disk_status
    ]

    if "ERROR" in statuses:

        overall_status = "ERROR"

    elif "WARNING" in statuses:

        overall_status = "ISSUE"

    else:

        overall_status = "HEALTHY"

    return {
        "cpu": cpu_status,
        "memory": memory_status,
        "disk": disk_status,
        "overall": overall_status,
        "issues": issues
    }


# ============================================================
# EMAIL
# ============================================================

def send_email(subject, message):

    if COMMAND_TIMEOUT is None:

        logging.error(
            "Email cannot be sent: COMMAND_TIMEOUT is not initialized"
        )

        return False

    try:

        email = (
            f"To: YOUR_EMAIL@example.com\n"
            f"Subject: {subject}\n"
            f"\n"
            f"{message}\n"
        )

        subprocess.run(
            ["sendmail", "-t"],
            input=email,
            text=True,
            capture_output=True,
            check=True,
            timeout=COMMAND_TIMEOUT
        )

        logging.info(
            "Email sent successfully: subject=%s",
            subject
        )

        return True

    except FileNotFoundError:

        logging.error(
            "Email sending failed: sendmail command not found"
        )

        return False

    except subprocess.CalledProcessError as e:

        error_message = (
            e.stderr.strip()
            if e.stderr
            else "No error message"
        )

        logging.error(
            "Email sending failed: %s",
            error_message
        )

        return False

    except subprocess.TimeoutExpired:

        logging.error(
            "Email sending timed out"
        )

        return False

    except OSError as e:

        logging.error(
            "Email sending failed due to OS error: %s",
            e
        )

        return False


# ============================================================
# ALERTING
# ============================================================

def send_alert(
    health,
    previous_state
):

    current_status = health["overall"]
    current_issues = health["issues"]

    previous_status = previous_state.get(
        "status",
        "HEALTHY"
    )

    previous_issues = previous_state.get(
        "issues",
        []
    )

    # --------------------------------------------------------
    # Recovery
    # --------------------------------------------------------

    if (
        current_status == "HEALTHY"
        and previous_status != "HEALTHY"
    ):

        print("\n===== RECOVERY =====")

        print(
            "System status: HEALTHY"
        )

        print(
            "Previous status:",
            previous_status
        )

        logging.info(
            "System recovered: previous_status=%s",
            previous_status
        )

        email_subject = "EC2 System Recovery"

        hostname = get_hostname()

        email_message = (
            f"System status: HEALTHY\n"
            f"Hostname: {hostname}\n\n"
            f"The system has recovered from the previous "
            f"{previous_status} state.\n"
        )

        if not send_email(
            email_subject,
            email_message
        ):

            logging.error(
                "Recovery email could not be delivered"
            )

        return

    # --------------------------------------------------------
    # Healthy with no previous issue
    # --------------------------------------------------------

    if current_status == "HEALTHY":

        return

    # --------------------------------------------------------
    # Duplicate alert suppression
    #
    # Suppress only when BOTH status and actual issues
    # are unchanged.
    # --------------------------------------------------------

    if (
        current_status == previous_status
        and current_issues == previous_issues
    ):

        return

    # --------------------------------------------------------
    # Determine severity
    # --------------------------------------------------------

    if current_status == "ISSUE":

        severity = "WARNING"

    elif current_status == "ERROR":

        severity = "CRITICAL"

    else:

        severity = "UNKNOWN"

    # --------------------------------------------------------
    # Console alert
    # --------------------------------------------------------

    print("\n===== ALERT =====")

    print(
        "Severity:",
        severity
    )

    print(
        "System status:",
        current_status
    )

    for issue in current_issues:

        print(
            "ALERT:",
            issue
        )

    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    logging.warning(
        "System alert: severity=%s | status=%s | issues=%s",
        severity,
        current_status,
        current_issues
    )

    # --------------------------------------------------------
    # Email
    # --------------------------------------------------------

    email_subject = (
        f"EC2 System Alert - {severity}"
    )

    hostname = get_hostname()

    email_message = (
        f"System status: {current_status}\n"
        f"Hostname: {hostname}\n\n"
        f"Issues:\n"
    )

    for issue in current_issues:

        email_message += (
            f"- {issue}\n"
        )

    if not send_email(
        email_subject,
        email_message
    ):

        logging.error(
            "Alert email could not be delivered"
        )


# ============================================================
# LOAD ALERT STATE
# ============================================================

def load_alert_state(filename):

    try:

        with open(filename, "r") as file:
            state = json.load(file)

        if not isinstance(state, dict):

            logging.error(
                "Alert state is not a JSON object: %s",
                filename
            )

            return {
                "status": "HEALTHY",
                "issues": []
            }

        return state

    except FileNotFoundError:

        return {
            "status": "HEALTHY",
            "issues": []
        }

    except json.JSONDecodeError:

        logging.error(
            "Invalid alert state file: %s",
            filename
        )

        return {
            "status": "HEALTHY",
            "issues": []
        }

    except OSError as e:

        logging.error(
            "Unable to read alert state: %s | error=%s",
            filename,
            e
        )

        return {
            "status": "HEALTHY",
            "issues": []
        }


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Configuration
    # --------------------------------------------------------

    if not initialize_config():

        return 2

    # --------------------------------------------------------
    # Previous alert state
    # --------------------------------------------------------

    previous_state = load_alert_state(
        ALERT_STATE_FILE
    )

    # --------------------------------------------------------
    # Collect system information
    # --------------------------------------------------------

    hostname = get_hostname()
    kernel = get_kernel()

    cpu_usage = get_cpu_usage()
    memory_usage = get_memory_usage()
    disk_usage = get_disk_usage()

    # --------------------------------------------------------
    # Check system health
    # --------------------------------------------------------

    health = check_health(
        cpu_usage,
        memory_usage,
        disk_usage
    )

    # --------------------------------------------------------
    # Alert
    # --------------------------------------------------------

    send_alert(
        health,
        previous_state
    )

    # --------------------------------------------------------
    # Save alert state
    # --------------------------------------------------------

    alert_state_saved = save_json_atomic(
        {
            "status": health["overall"],
            "issues": health["issues"]
        },
        ALERT_STATE_FILE
    )

    if not alert_state_saved:

        logging.error(
            "Failed to save alert state"
        )

    # --------------------------------------------------------
    # Build report
    # --------------------------------------------------------

    report = {
        "timestamp": datetime.now().isoformat(),
        "hostname": hostname,
        "kernel": kernel,
        "cpu_usage": (
            round(cpu_usage)
            if cpu_usage is not None
            else None
        ),
        "memory_usage": (
            round(memory_usage)
            if memory_usage is not None
            else None
        ),
        "disk_usage": disk_usage,
        "thresholds": {
            "cpu": CPU_THRESHOLD,
            "memory": MEMORY_THRESHOLD,
            "disk": DISK_THRESHOLD,
            "command_timeout": COMMAND_TIMEOUT
        },
        "health": health,
        "summary": {
            "status": health["overall"],
            "issue_count": len(health["issues"])
        }
    }

    # --------------------------------------------------------
    # Save latest report
    # --------------------------------------------------------

    health_report_saved = save_json_atomic(
        report,
        HEALTH_FILE
    )

    if not health_report_saved:

        logging.error(
            "Failed to save health report"
        )

    # --------------------------------------------------------
    # Save history
    # --------------------------------------------------------

    history_saved = save_history(
        report,
        HISTORY_FILE
    )

    if not history_saved:

        logging.error(
            "Failed to save health history"
        )

    # --------------------------------------------------------
    # Log health result
    # --------------------------------------------------------

    logging.info(
        "Health check completed: CPU=%s, Memory=%s, "
        "Disk=%s, Overall=%s",
        health["cpu"],
        health["memory"],
        health["disk"],
        health["overall"]
    )

    # --------------------------------------------------------
    # Console report
    # --------------------------------------------------------

    print("===== SYSTEM HEALTH =====")

    print(
        "Hostname:",
        hostname
    )

    print(
        "Kernel:",
        kernel
    )

    if cpu_usage is not None:

        print(
            "CPU Usage:",
            round(cpu_usage),
            "%"
        )

    print(
        "CPU Status:",
        health["cpu"]
    )

    if memory_usage is not None:

        print(
            "Memory Usage:",
            round(memory_usage),
            "%"
        )

    print(
        "Memory Status:",
        health["memory"]
    )

    print("Disk Usage:")

    if disk_usage is not None:

        for filesystem in disk_usage:

            print(
                f"  {filesystem['mountpoint']}: "
                f"{filesystem['usage']}%"
            )

    print(
        "Disk Status:",
        health["disk"]
    )

    print(
        "Overall Status:",
        health["overall"]
    )

    if health["issues"]:

        print("\nIssues:")

        for issue in health["issues"]:

            print(
                "-",
                issue
            )

    # --------------------------------------------------------
    # Exit code
    #
    # 0 = healthy
    # 1 = system issue
    # 2 = monitoring/system error
    # --------------------------------------------------------

    if health["overall"] == "ERROR":

        return 2

    if health["overall"] == "ISSUE":

        return 1

    # The system itself is healthy.
    # Persistence failures don't change system health,
    # but they do make the monitoring result incomplete.

    if (
        not alert_state_saved
        or not health_report_saved
        or not history_saved
    ):

        return 2

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )
