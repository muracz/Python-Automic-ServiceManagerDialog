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

# // TODo
#  - set_data action for smgr > 12.3


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
    # Read the config file
    f = open(file)
    config = json.load(f)
    f.close()

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
    smgrPhrase = input("Phrase. Leave empty to use env variable $AUTOMIC_PHRASE:  ") or os.getenv('AUTOMIC_SMCL')
    smgrPass = getpass("Password. Leave empty if no password is configured ")

    return smgrPath, smgrPort, smgrHost, smgrPhrase, smgrPass


# Get the config
try:
    smgrPath, smgrPort, smgrHost, smgrPhrase, smgrPass = getConfigJSON(sys.argv[1])
except IndexError:
    smgrPath, smgrPort, smgrHost, smgrPhrase, smgrPass = getConfigInput()


# We need the port always when set so why do it over and over again
if smgrPort is not None:
    smgrHost = smgrHost + ":" + smgrPort

# Build Preliminary argList
smgrArgs = [smgrPath, '-h', smgrHost, '-n', smgrPhrase, '-p', smgrPass]


# Prepare env
os.environ['LD_LIBRARY_PATH'] = smgrPath.replace("ucybsmcl", "")


# ---------------------------------------------------
#      Supporting functions
# ---------------------------------------------------

def clrScreen():
    subprocess.run("clear", check=True)

def runCommand(args):
    try:
        res = subprocess.run(smgrArgs, stdout=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        print(e.output.decode("utf-8"))
        sys.exit(e.returncode)

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
    smgrArgs.append("-c")
    smgrArgs.append("GET_PROCESS_LIST")

    result = runCommand(smgrArgs)

    c = 1
    procList = {}
    # Populate the dict
    for line in result.stdout.decode("utf-8").splitlines():
        procList[c] = line.replace("\"", "").split(" ")
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
            procTimestamp = procList[c][3] + " - " + procList[c][4]
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


def commitAction(a, p):
    if a == "R":
        restartProcess(p)
    elif a == "K":
        stopProcess(p)
    elif a == "KA":
        stopProcess(p, "A")
    elif a == "KS":
        stopProcess(p, "S")
    else:
        startProcess(p)


# Validation functions
def validateCommit(inputCommit):
    return inputCommit.upper() == "Y"


def validateNumber(inputNumber, procList):
    while inputNumber not in range(1, len(procList)):
        inputNumber = int(input("Invalid number, try again: "))

    return inputNumber


def validateAction(inputAction):
    while inputAction not in ("K", "KA", "KS", "R", "S", "Q", "RE"):
        inputAction = input("Invalid action, try again ").upper()

    return inputAction


# ---------------------------------------------------
#      Main loop
# ---------------------------------------------------

# Version = getVersion()
# print(Version)
while True:
    commit = False
    procList = getProcessList()

    print()
    print("Actions: R - restart, S - start, K - stop")
    print("         KA - stop abnormally , KS - shutdown ")
    print("         Q - quit, RE - refresh")

    # Timeout after n seconds a.k.a auto-refresh
    print("Action: ", end="",flush=True)
    i, o, e = select.select([sys.stdin], [], [], autorefresh)

    if i:
        inputAction = validateAction(sys.stdin.readline().strip().upper())
    else:
        continue

    if inputAction == "Q":
        break
    if inputAction == "RE":
        continue

    inputNumber = validateNumber(
        int(input("Which process number? ")), procList)

    print("Action: %s on %s. " % (inputAction, procList[inputNumber][0]))
    commit = validateCommit(input("Commit Y/N ? "))

    if commit:
        commitAction(inputAction, procList[inputNumber][0])
