#!/usr/bin/python3
# Automic Service Manager Wrapper
# Created by Marcin Uracz
# Github: https://github.com/muracz/Python-Automic-ServiceManagerDialog
#
# Usage:
# 1. Interactive mode (no parameters necessary)
# 2. With configuration - parameter 1 path to a json config file
#


import os
import sys
import subprocess
import re
import time
import json
import datetime
import select
from getpass import getpass


#  Constants / config

# Let's have some colours
class bcolors:
    OK = '\033[92m'  # GREEN
    WARNING = '\033[93m'  # YELLOW
    FAIL = '\033[91m'  # RED
    RESET = '\033[0m'  # RESET COLOR


# Autorefresh interval in seconds
autorefresh = 10


def getConfigJSON(file):
   with open(file) as f: 
    # Read the config file
    config = json.load(f)

    if len(config['connections']) > 1:
        c = 0
        print("Available configurations")
        for conn in config['connections']:
            print("%2d - %s" % (c, conn['name']))
            c += 1

        connID = input("Choose the config: ")
        connID = int(connID)
    else:
        connID = 0

    smgrPath = config['connections'][connID]['smgrclPath']
    smgrPort = config['connections'][connID]['port']
    smgrHost = config['connections'][connID]['host']
    smgrPhrase = config['connections'][connID]['phrase']
    if config['connections'][connID]['pass']:
        smgrPass = getpass("Password: ")
    else:
        smgrPass = ""

    return smgrPath, smgrPort, smgrHost, smgrPhrase, smgrPass


def getConfigInput():

    smgrPath = input(
        "Path to ucybsmcl. Leave empty to use env variable $AUTOMIC_SMCL:  ") or os.getenv('AUTOMIC_SMCL')
    smgrHost = input("Hostame: ")
    smgrPort = input("ServiceManager port. Leave empty to use env variable $AUTOMIC_SMPORT:  ") or os.getenv('AUTOMIC_SMPORT')
    smgrPhrase = input("Phrase. Leave empty to use env variable $AUTOMIC_PHRASE:  ") or os.getenv('AUTOMIC_PHRASE')
    smgrPass = getpass("Password. Leave empty if no password is configured ")

    return smgrPath, smgrPort, smgrHost, smgrPhrase, smgrPass


# Get the config
try:
    smgrPath, smgrPort, smgrHost, smgrPhrase, smgrPass = getConfigJSON(sys.argv[1])
except IndexError:
    try:
        smgrPath, smgrPort, smgrHost, smgrPhrase, smgrPass = getConfigInput()
    except KeyboardInterrupt:
        print("Bye!")
        sys.exit()

# We need the port always when set so why do it over and over again
# Plus Last check
if all([smgrPath,smgrPort,smgrHost,smgrPhrase]):
    smgrHost = smgrHost + ":" + smgrPort
else:
    print("Not all parameters set")
    sys.exit(1)

# Prepare env
os.environ['LD_LIBRARY_PATH'] = smgrPath.replace("ucybsmcl", "")


# ---------------------------------------------------
#      Supporting functions
# ---------------------------------------------------
def initArgs():
    # Build Preliminary argList
    smgrArgs = [smgrPath, '-h', smgrHost, '-n', smgrPhrase, '-p', smgrPass]

    return smgrArgs



def clrScreen():
    subprocess.run("clear", check=True)

def runCommand(args):

    try:
        res = subprocess.run(args, stdout=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        print(e.output.decode("utf-8"))
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("Wrong ucybsmcl path provided")
        sys.exit(1)

    return res

def getVersion():
    result = subprocess.run(
        [smgrPath, '-v'], stdout=subprocess.PIPE, check=True)

    try:
        Version = re.search(
            r'([0-9.-]+)\+', result.stdout.decode("utf-8")).group(1)
        return Version
    except AttributeError:
        print('Error: Could not find version')
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
        procList[c] = list(filter(None,map(str.strip, line.split("\""))))
        c += 1

    # Header
    clrScreen()
    print()
    print("Host: %s\t\t       Phrase:  %s" % (smgrHost, smgrPhrase))
    print("Current time: %s".rjust(55) %
          (datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")))
    print('-' * 72)
    print("| %2s | %25s | %1s | %10s | %18s | " %
          ("#", "Process Name", "", "PID", "Timestamp"))
    print('-' * 72)
    # Print
    for c in procList:
        # Make it pretty
        procName = procList[c][0].ljust(25)
        procStatus = procList[c][1]
        try:
            procPID = procList[c][2]
        except IndexError:
            procPID = ''

        try:
            procTimestamp = procList[c][3] 
        except IndexError:
            procTimestamp = ''

    # Add the colours
        if procStatus == "R":
            procStatus = bcolors.OK + procStatus + bcolors.RESET
        else:
            procStatus = bcolors.FAIL + procStatus + bcolors.RESET

        print("| %2d | %25s | %3s | %10s | %18s | " %
              (c, procName, procStatus, procPID, procTimestamp))

    # Close the table
    print('-' * 72)
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
    smgrArgs.append("-s")
    smgrArgs.append(ProcName)

    result = runCommand(smgrArgs)


def startProcess(ProcName):
    smgrArgs = initArgs()
    print("Starting %s" % ProcName)

    # Add the appropriate paramters
    smgrArgs.append("-c")
    smgrArgs.append("START_PROCESS")
    smgrArgs.append("-s")
    smgrArgs.append(ProcName)

    result = runCommand(smgrArgs)

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

    
    result = runCommand(smgrArgs)

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
        modifyProcess(p, m , d)
    else:
        startProcess(p)


# Validation functions
def validateCommit(inputCommit):
    return inputCommit.upper() == "Y"


def validateNumber(inputNumber, procList):
    while inputNumber not in range(1, len(procList)+1):
        inputNumber = int(input("Invalid number, try again: "))

    return inputNumber


def validateNumbers(input_str, procList):
    numbers = []
    ranges = input_str.split(',')
    for r in ranges:
        if '-' in r:
            start, end = map(int, r.split('-'))
            numbers.extend(range(start, end + 1))
        else:
            numbers.append(int(r))
    return [n for n in numbers if n in range(1, len(procList) + 1)]


def validateAction(inputAction):
    """Validate action and parse any numbers included in the command"""
    # Define bulk and single actions separately
    bulk_actions = ("K", "KA", "R", "S", "MA", "MO")
    single_actions = ("KS", "Q", "RE", "MC", "MP")
    valid_actions = bulk_actions + single_actions
    
    # Match action followed by optional numbers only for bulk actions
    pattern = r"^(" + "|".join(valid_actions) + r")([\d,\-\s]+)?$"

    while not re.match(pattern, inputAction):
        inputAction = input("Invalid action, try again: ").upper()

    # Split the input into the action and the number part
    match = re.match(pattern, inputAction)
    action = match.group(1)
    number_part = match.group(2)

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
#      Main loop
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
        


        ## Additional Command M{X}-> modify property 
        ## Additional input to change P - path, C - command, A - active, I - inactive 

        # Timeout after n seconds a.k.a auto-refresh
        print("Action: ", end="",flush=True)
        i, o, e = select.select([sys.stdin], [], [], autorefresh)

        if i:
            inputAction, numberPart = validateAction(sys.stdin.readline().strip().upper())
        else:
            continue

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
                numbers = [validateNumber(int(input("Which process number? ")), procList)]

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
        
        commit = validateCommit(input(f"\nExecute {inputAction} on these processes? Y/N [Y] ") or "Y")

        if commit:
            for num in numbers:
                print(f"Processing {procList[num][0]}...")
                commitAction(inputAction, procList[num][0], inputData)
except KeyboardInterrupt:
    print("Bye!")
    sys.exit()
