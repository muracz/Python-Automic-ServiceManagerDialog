#!/usr/bin/env python3
# Automic Service Manager Wrapper
# Created by Marcin Uracz
# Github: https://github.com/muracz/Python-Automic-ServiceManagerDialog
#
# Usage:
# 1. Interactive mode (no parameters necessary)
# 2. With configuration - parameter 1 path to a json config file

import datetime
import getpass
import json
import os
import re
import select
import subprocess
import sys
import termios
import time


# Constants / config


# Let's have some colours
class bcolors:
    OK = "\033[92m"  # GREEN
    WARNING = "\033[93m"  # YELLOW
    FAIL = "\033[91m"  # RED
    RESET = "\033[0m"  # RESET COLOR


# Autorefresh interval in seconds
autorefresh = 10
use_autorefresh = os.getenv("AUTOMIC_AUTOREFRESH", "1") not in ("0", "false", "False")


def getConfigJSON(file):
    with open(file) as f:
        config = json.load(f)

    if (
        "connections" not in config
        or not isinstance(config["connections"], list)
        or not config["connections"]
    ):
        print("Config file is missing a valid 'connections' list")
        sys.exit(1)

    if len(config["connections"]) > 1:
        c = 0
        print("Available configurations")
        for conn in config["connections"]:
            print("%2d - %s" % (c, conn["name"]))
            c += 1

        while True:
            try:
                connID = int(input("Choose the config: "))
            except ValueError:
                print("Invalid number, try again.")
                continue
            if 0 <= connID < len(config["connections"]):
                break
            print("Config out of range, try again.")
    else:
        connID = 0

    conn = config["connections"][connID]
    required_keys = ("smgrclPath", "port", "host", "phrase", "pass")
    missing = [k for k in required_keys if k not in conn]
    if missing:
        print("Config entry is missing keys: " + ", ".join(missing))
        sys.exit(1)

    smgrPath = conn["smgrclPath"]
    smgrPort = conn["port"]
    smgrHost = conn["host"]
    smgrPhrase = conn["phrase"]
    smgrCert = conn.get("certificate")
    smgrKey = conn.get("key")
    smgrChain = conn.get("chain")
    if conn["pass"]:
        smgrPass = getpass.getpass("Password: ")
    else:
        smgrPass = ""

    return (
        smgrPath,
        smgrPort,
        smgrHost,
        smgrPhrase,
        smgrPass,
        smgrCert,
        smgrKey,
        smgrChain,
    )


def getConfigInput():
    smgrPath = (
        input("Path to ucybsmcl. Leave empty to use env variable $AUTOMIC_SMCL:  ")
        or os.getenv("AUTOMIC_SMCL")
    )
    smgrHost = input("Hostname: ")
    smgrPort = (
        input("ServiceManager port. Leave empty to use env variable $AUTOMIC_SMPORT:  ")
        or os.getenv("AUTOMIC_SMPORT")
    )
    smgrPhrase = (
        input("Phrase. Leave empty to use env variable $AUTOMIC_PHRASE:  ")
        or os.getenv("AUTOMIC_PHRASE")
    )
    smgrPass = getpass.getpass("Password. Leave empty if no password is configured ")
    smgrCert = os.getenv("AUTOMIC_SMCERT")
    smgrKey = os.getenv("AUTOMIC_SMKEY")
    smgrChain = os.getenv("AUTOMIC_SMCHAIN")

    missing = []
    if not smgrPath:
        missing.append("AUTOMIC_SMCL / ucybsmcl path")
    if not smgrHost:
        missing.append("host")
    if not smgrPort:
        missing.append("AUTOMIC_SMPORT / port")
    if not smgrPhrase:
        missing.append("AUTOMIC_PHRASE / phrase")
    if missing:
        print("Missing required values: " + ", ".join(missing))
        sys.exit(1)

    return (
        smgrPath,
        smgrPort,
        smgrHost,
        smgrPhrase,
        smgrPass,
        smgrCert,
        smgrKey,
        smgrChain,
    )


# Get the config
try:
    (
        smgrPath,
        smgrPort,
        smgrHost,
        smgrPhrase,
        smgrPass,
        smgrCert,
        smgrKey,
        smgrChain,
    ) = getConfigJSON(sys.argv[1])
except IndexError:
    try:
        (
            smgrPath,
            smgrPort,
            smgrHost,
            smgrPhrase,
            smgrPass,
            smgrCert,
            smgrKey,
            smgrChain,
        ) = getConfigInput()
    except KeyboardInterrupt:
        print("Bye!")
        sys.exit()


# We need the port always when set so why do it over and over again
# Plus Last check
if all([smgrPath, smgrPort, smgrHost, smgrPhrase]):
    if not os.path.isfile(smgrPath) or not os.access(smgrPath, os.X_OK):
        print("Invalid ucybsmcl path: file not found or not executable")
        sys.exit(1)
    if not str(smgrPort).isdigit():
        print("Invalid port: must be numeric")
        sys.exit(1)
    if (smgrCert or smgrKey or smgrChain) and not (smgrCert and smgrKey):
        print("Certificate auth requires both certificate and key files")
        sys.exit(1)
    smgrHost = smgrHost + ":" + smgrPort
else:
    print("Not all parameters set")
    sys.exit(1)


# Prepare env
os.environ["LD_LIBRARY_PATH"] = os.path.dirname(smgrPath)


# ---------------------------------------------------
# Supporting functions
# ---------------------------------------------------
def initArgs():
    # Build Preliminary argList
    smgrArgs = [smgrPath, "-h", smgrHost, "-n", smgrPhrase, "-p", smgrPass]
    if smgrCert:
        smgrArgs.extend(["-certificate", smgrCert])
    if smgrKey:
        smgrArgs.extend(["-key", smgrKey])
    if smgrChain:
        smgrArgs.extend(["-chain", smgrChain])

    return smgrArgs


def clrScreen():
    print("\033[2J\033[H", end="")


def runCommand(args):
    try:
        res = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print("Command failed.")
        if e.stdout:
            print(e.stdout.decode("utf-8"))
        if e.stderr:
            print(e.stderr.decode("utf-8"))
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("Wrong ucybsmcl path provided")
        sys.exit(1)

    return res


def read_action_with_autorefresh(timeout):
    if not sys.stdin.isatty():
        i, o, e = select.select([sys.stdin], [], [], timeout)
        if i:
            return sys.stdin.readline()
        return None

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    new_settings = termios.tcgetattr(fd)
    new_settings[3] &= ~(termios.ICANON | termios.ECHO)
    new_settings[6][termios.VMIN] = 1
    new_settings[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)

    try:
        r, o, e = select.select([sys.stdin], [], [], timeout)
        if not r:
            return None

        buf = []
        while True:
            try:
                ch = os.read(fd, 1)
            except KeyboardInterrupt:
                raise
            if not ch:
                continue
            ch = ch.decode(errors="ignore")
            if ch in ("\n", "\r"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
            if ch in ("\x7f", "\b"):
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            buf.append(ch)
            sys.stdout.write(ch)
            sys.stdout.flush()
        return "".join(buf)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def getVersion():
    result = subprocess.run([smgrPath, "-v"], stdout=subprocess.PIPE, check=True)

    try:
        output = result.stdout.decode("utf-8").strip()
        match = re.search(r"([0-9][0-9.-]+)\+?", output)
        if match:
            return match.group(1)
        if output:
            return output.split()[0]
        return None
    except AttributeError:
        print("Error: Could not find version")
        return None


def getProcessList():
    smgrArgs = initArgs()
    smgrArgs.append("-c")
    smgrArgs.append("GET_PROCESS_LIST")

    result = runCommand(smgrArgs)

    c = 1
    procList = {}
    # Populate the dict
    for line in result.stdout.decode("utf-8").splitlines():
        if not line.strip():
            continue
        procList[c] = list(filter(None, map(str.strip, line.split('"'))))
        c += 1

    # Header
    clrScreen()
    print()
    print(
        "Host: %s\t\t       Phrase:  %s" % (smgrHost, smgrPhrase)
    )
    print(
        ("Current time: %s".rjust(55))
        % (datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
    )
    print("-" * 72)
    print(
        "| %2s | %25s | %1s | %10s | %18s | "
        % ("#", "Process Name", "", "PID", "Timestamp")
    )
    print("-" * 72)
    # Print
    for c in procList:
        # Make it pretty
        procName = procList[c][0].ljust(25)
        procStatus = procList[c][1]
        try:
            procPID = procList[c][2]
        except IndexError:
            procPID = ""

        try:
            procTimestamp = procList[c][3]
        except IndexError:
            procTimestamp = ""

        # Add the colours
        if procStatus == "R":
            procStatus = bcolors.OK + procStatus + bcolors.RESET
        else:
            procStatus = bcolors.FAIL + procStatus + bcolors.RESET

        print(
            "| %2d | %25s | %3s | %10s | %18s | "
            % (c, procName, procStatus, procPID, procTimestamp)
        )

    # Close the table
    print("-" * 72)
    return procList


def stopProcess(ProcName, Mode=None):
    smgrArgs = initArgs()

    # Add the appropriate paramters
    smgrArgs.append("-c")
    smgrArgs.append("STOP_PROCESS")
    smgrArgs.append("-s")
    smgrArgs.append(ProcName)
    if Mode is not None:
        smgrArgs.append("-m")
        smgrArgs.append(Mode)

    runCommand(smgrArgs)


def startProcess(ProcName):
    smgrArgs = initArgs()
    print("Starting %s" % ProcName)

    # Add the appropriate paramters
    smgrArgs.append("-c")
    smgrArgs.append("START_PROCESS")
    smgrArgs.append("-s")
    smgrArgs.append(ProcName)

    runCommand(smgrArgs)


def restartProcess(ProcName):
    stopProcess(ProcName)
    time.sleep(2)
    startProcess(ProcName)


def modifyProcess(ProcName, Mode=None, Data=None):
    smgrArgs = initArgs()

    print("Modifying %s" % ProcName)

    # Add the appropriate paramters
    smgrArgs.append("-c")
    smgrArgs.append("SET_DATA")
    smgrArgs.append("-s")
    smgrArgs.append(ProcName)
    smgrArgs.append("-d")
    if Mode == "A":
        smgrArgs.append("Autostart")
        smgrArgs.append("1")
    elif Mode == "O":
        smgrArgs.append("Autostart")
        smgrArgs.append("0")
    elif Mode == "C":
        smgrArgs.append("Command")
        smgrArgs.append(Data)
    elif Mode == "P":
        smgrArgs.append("StartPath")
        smgrArgs.append(Data)

    runCommand(smgrArgs)


def commitAction(a, p, d):
    if a == "R":
        restartProcess(p)
    elif a == "K":
        stopProcess(p)
    elif a == "KA":
        stopProcess(p, "A")
    elif a == "KS":
        stopProcess(p, "S")
    elif a.startswith("M") and len(a) == 2:
        m = a[1]
        modifyProcess(p, m, d)
    elif a == "S":
        startProcess(p)
    else:
        print(f"Unknown action: {a}")


# Validation functions
def validateCommit(inputCommit):
    return inputCommit.upper() == "Y"


def validateNumber(inputNumber, procList):
    while inputNumber not in range(1, len(procList) + 1):
        try:
            inputNumber = int(input(f"Invalid number (1-{len(procList)}), try again: "))
        except ValueError:
            continue

    return inputNumber


def validateNumbers(input_str, procList):
    numbers = []
    ranges = input_str.split(",")
    for r in ranges:
        r = r.strip()
        if not r:
            continue
        if "-" in r:
            try:
                start, end = map(int, r.split("-", 1))
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            numbers.extend(range(start, end + 1))
        else:
            try:
                numbers.append(int(r))
            except ValueError:
                continue
    valid = [n for n in numbers if n in range(1, len(procList) + 1)]
    if not valid and input_str.strip():
        print("No valid numbers detected.")
    return sorted(set(valid))


def validateAction(inputAction):
    """Validate action and parse any numbers included in the command"""
    # Define bulk and single actions separately
    bulk_actions = ("K", "KA", "R", "S", "MA", "MO")
    single_actions = ("KS", "Q", "RE", "MC", "MP")
    valid_actions = bulk_actions + single_actions

    # Match action followed by optional numbers only for bulk actions
    pattern = r"^(" + "|".join(valid_actions) + r")([\d,\-\s]+)?$"
    numbers_pattern = r"^\s*\d+\s*(?:-\s*\d+\s*)?(?:,\s*\d+\s*(?:-\s*\d+\s*)?)*\s*$"

    while True:
        match = re.match(pattern, inputAction)
        if not match:
            inputAction = input("Invalid action, try again: ").upper()
            continue
        action = match.group(1)
        number_part = match.group(2)
        if number_part and action in bulk_actions:
            if not re.match(numbers_pattern, number_part):
                inputAction = input("Invalid numbers, try again: ").upper()
                continue
        break

    # Return just action for non-numeric commands
    if action in ("Q", "RE"):
        return action, None

    # Validate that numbers are only provided for bulk actions
    if number_part and action not in bulk_actions:
        print(f"Action {action} cannot be used with multiple processes")
        return action, None

    # If numbers provided for bulk actions, return them for processing
    if number_part and action in bulk_actions:
        return action, number_part.strip()

    return action, None


# ---------------------------------------------------
# Main loop
# ---------------------------------------------------

# Version = getVersion()
# print(Version)
try:
    while True:
        commit = False
        procList = getProcessList()

        print()
        print("Actions: R - restart, S - start, K - stop")
        print("         KA - stop abnormally , KS - shutdown ")
        print("         MC - modify command, MP - modify start path")
        print("         MA - autostart on, MO- autostart off")
        print("         Q - quit, RE - refresh")

        # Timeout after n seconds a.k.a auto-refresh
        print("Action: ", end="", flush=True)
        if use_autorefresh:
            line = read_action_with_autorefresh(autorefresh)
            if line is None:
                continue
            inputAction, numberPart = validateAction(line.strip().upper())
        else:
            inputAction, numberPart = validateAction(input().strip().upper())

        if inputAction == "Q":
            break
        if inputAction == "RE":
            continue

        # Process numbers if provided in command or ask for input
        if numberPart:
            numbers = validateNumbers(numberPart, procList)
            if not numbers:
                print("No valid process numbers provided")
                continue
        else:
            if inputAction in ("R", "S", "K", "KA", "MA", "MO"):
                input_str = input("Which process number(s)? (e.g. 1,2,3 or 1-5): ")
                numbers = validateNumbers(input_str, procList)
                if not numbers:
                    print("No valid process numbers provided")
                    continue
            else:
                num = int(input("Which process number? "))
                numbers = [validateNumber(num, procList)]

        if inputAction == "MC":
            inputData = input("Provide new command: ")
        elif inputAction == "MP":
            inputData = input("Provide new path: ")
        else:
            inputData = None

        # Show confirmation for all processes
        print("\nSelected processes:")
        for num in numbers:
            print(f"- {procList[num][0]}")

        commit = validateCommit(
            input(
                f"\nExecute {inputAction} on these processes? Y/N [Y] "
            )
            or "Y"
        )

        if commit:
            for num in numbers:
                print(
                    f"Processing {procList[num][0]}..."
                )
                commitAction(inputAction, procList[num][0], inputData)
except KeyboardInterrupt:
    print("Bye!")
    sys.exit()
