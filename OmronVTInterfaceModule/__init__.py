import json
import os
import pickle
import shutil
import threading
import time
from datetime import datetime
from telnetlib import Telnet
from collections import deque
import math

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
from markupsafe import escape
import markupsafe

import OmronVTInterfaceModule.ovtimconfig
import OmronVTInterfaceModule.ovtimfunctions

# gunicorn -w 1 -b 127.0.0.1:5000 --threads 100 "OmronVTInterfaceModule:app"
"""
scanner reads a barcode
    python code reads barcode from scanner
    Logic Overview:
        only accept a new barcode every X seconds (15? 30?)
            scannerIntervalLimit = 15 # time that must elapse (in seconds) between a barcode being read for. Each scanner has different timer
        if a barcode matches the previously scanned one, do not create new toast, but update timestamp in "current barcodes" toast
        otherwise overwrite the variable (for example topsideBarcode) with the new barcode
        ---add the barcode to the "barcode master list" variable?
        generate an event for the JS code
        JS code reads event and generates toast

python code outputs barcode and generates notification event


barcodeList[(barcode, scanner, timestamp)]
    whenever a barcode is scanned, it is added to this list
"""

def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=False, instance_path=__path__[0])
    app.config.from_mapping(
        SECRET_KEY='Omron247',
    )
    #socketio = SocketIO(app, logger=True, engineio_logger=True, async_mode='gevent')
    socketio = SocketIO(app, async_mode='gevent')

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    # initialize webapp and barcode logging
    app.logger = OmronVTInterfaceModule.ovtimfunctions.initLogging(app.instance_path, OmronVTInterfaceModule.ovtimconfig.logConfigWebapp)
    barcodeLogger = OmronVTInterfaceModule.ovtimfunctions.initLogging(app.instance_path, OmronVTInterfaceModule.ovtimconfig.logConfigBarcode)

    OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath = os.path.join(app.instance_path, 'static', OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath)

    # index page
    @app.route('/')
    def index():
        configData = OmronVTInterfaceModule.ovtimfunctions.readConfig(app.logger, OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath, OmronVTInterfaceModule.ovtimconfig.possibleIniValues, OmronVTInterfaceModule.ovtimconfig.possibleModelValues)
        #print(configData)
        dictActiveProfile = configData[1][configData[2]]
        activeProfile = configData[2]
        app.logger.debug('{0}|{1}'.format(request.remote_addr, request.url))
        return render_template('index.html', dictActiveProfile = dictActiveProfile, activeProfile = activeProfile)

    # create, change, or delete scanner profiles
    @app.route('/managescanners')
    def managescanners():
        configData = OmronVTInterfaceModule.ovtimfunctions.readConfig(app.logger, OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath, OmronVTInterfaceModule.ovtimconfig.possibleIniValues, OmronVTInterfaceModule.ovtimconfig.possibleModelValues)
        dictProfiles = configData[1]
        activeProfile = configData[2]
        app.logger.debug('{0} requested {1}'.format(request.remote_addr, request.url))
        return render_template('managescanners.html', jsonString = json.dumps(json.load(open(OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath, 'r'))), activeProfile = activeProfile, dictProfiles = dictProfiles, karlboxConfigFilePath = OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath)

    # display quick start guide and helpful resources
    @app.route('/help')
    def help():
        app.logger.debug('{0} requested {1}'.format(request.remote_addr, request.url))
        return render_template('help.html')

    # "main application" which shows weblink, reads input barcodes and outputs to inspection machine
    @app.route('/displayweblink', methods=['GET'])
    def displayweblink():
        OmronVTInterfaceModule.ovtimfunctions.readConfig(app.logger, OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath, OmronVTInterfaceModule.ovtimconfig.possibleIniValues, OmronVTInterfaceModule.ovtimconfig.possibleModelValues)
        app.logger.debug('{0} requested {1}'.format(request.remote_addr, request.url))
        if 'scanner1ip' in request.args.keys():
            scanner1ip = request.args['scanner1ip']
            if 'scanner1port' in request.args.keys():
                scanner1port = request.args['scanner1port']
            else:
                scanner1port = 2001
        else:
            scanner1ip = ''
        if 'scanner2ip' in request.args.keys():
            scanner2ip = request.args['scanner2ip']
            if 'scanner2port' in request.args.keys():
                scanner2port = request.args['scanner2port']
            else:
                scanner2port = 2003
        else:
            scanner2ip = ''
        return render_template('displayweblink.html', scanner1ip=scanner1ip, scanner1port=scanner1port, scanner2ip=scanner2ip, scanner2port=scanner2port)

    # allow HTML files to access logging
    @app.context_processor
    def utility_processor():
        def writeWebLog(logcontent, loglevel='DEBUG'):
            if loglevel == 'DEBUG':
                app.logger.debug('{0}|{1}| {2}'.format(request.remote_addr, request.url, logcontent))
            elif loglevel == 'INFO':
                app.logger.info('{0}|{1}| {2}'.format(request.remote_addr, request.url, logcontent))
            elif loglevel == 'ERROR':
                app.logger.error('{0}|{1}| {2}'.format(request.remote_addr, request.url, logcontent))
            return
        def writeBarcodeLog(logcontent, loglevel='INFO'):
            if loglevel == 'DEBUG':
                barcodeLogger.debug('{0}|{1}| {2}'.format(request.remote_addr, request.url, logcontent))
            elif loglevel == 'INFO':
                barcodeLogger.info('{0}|{1}| {2}'.format(request.remote_addr, request.url, logcontent))
            elif loglevel == 'ERROR':
                barcodeLogger.error('{0}|{1}| {2}'.format(request.remote_addr, request.url, logcontent))
            return
        return dict(writeWebLog=writeWebLog, writeBarcodeLog=writeBarcodeLog)
        
    # used to determine if scanner is accessible via the IP and port provided as arguments
    @socketio.on('Event_isScannerConnectedLan')
    def isScannerConnectedLan(ip, port):
        app.logger.debug('Testing if scanner is connected via LAN: ' + str(ip) + ':' + str(port))
        t = threading.Thread(target=OmronVTInterfaceModule.ovtimfunctions.testTelnetConn, args=(str(ip), int(port), OmronVTInterfaceModule.ovtimconfig.testLAN, app.logger))
        t.setDaemon(True)
        OmronVTInterfaceModule.ovtimconfig.testLAN[t.name] = 0
        t.start()
        startTimer = time.time()
        while OmronVTInterfaceModule.ovtimconfig.testLAN[t.name] == 0:
            if time.time() - startTimer > 5: # timeout 5 seconds
                app.logger.debug('Scanner (' + str(ip) + ':' + str(port) + ') not connected via LAN- connection timed out after 5 seconds')
                socketio.emit('Event_isScannerConnectedLanResult', {'ip': ip, 'port': port, 'result': 'fail'})
                return
        app.logger.debug('Scanner (' + str(ip) + ':' + str(port) + ') connected via LAN')
        socketio.emit('Event_isScannerConnectedLanResult', {'ip': ip, 'port': port, 'result': 'success'})
        OmronVTInterfaceModule.ovtimconfig.testLAN[t.name] = 0
        return

    

    # connects to scanner via LAN, then enters infinite loop to read data from scanner and pass along via 'Event_scannerNotification' event
    @socketio.on('Event_readDataFromLan')
    def readDataFromLan(ip, port):
        attemptNo = 1
        while True:
            app.logger.info('Establishing LAN connection with scanner to receive data: ' + str(ip) + ':' + str(port) + ' (this is attempt #' + str(attemptNo) + ' of 3)')
            try:
                tnclient = Telnet(str(ip), int(port), 5)
                app.logger.info('LAN connection established with scanner: ' + str(ip) + ':' + str(port))
                break
            except Exception as e:
                app.logger.error('Failed to establish LAN connection with scanner (' + str(ip) + ':' + str(port) + ') because of error: ' + str(e) + '. Retrying in 30 seconds (this was attempt #' + str(attemptNo) + ' of 3)')
                if attemptNo > 2:
                    socketio.emit('Event_scannerNotification', {'title': 'Failed to Establish Connection', 'ip':str(ip), 'port':str(port), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'error', 'msg': 'Could not establish connection to scanner (Attempt #' + str(attemptNo) + ' of 3). Please ensure the scanner is plugged in, powered on, and settings have been configured in <a href="{{ url_for(\'managescanners\') }}">Manage Scanners</a>. Refresh the page to try again.'})
                    return
                else:
                    socketio.emit('Event_scannerNotification', {'title': 'Failed to Establish Connection', 'ip':str(ip), 'port':str(port), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'error_retry', 'msg': 'Could not establish connection to scanner (Attempt #' + str(attemptNo) + ' of 3). Waiting 30 seconds before retrying.'})
                attemptNo += 1
                time.sleep(30)
                continue

        while True:
            time.sleep(0.5)
            try:
                rcvData = tnclient.read_until(b'\r\n', timeout=3)
            except EOFError as e:
                app.logger.warning('LAN connection reset for scanner (' + str(ip) + ':' + str(port) + ')')
                socketio.emit('Event_scannerNotification', {'title': 'Connection Reset', 'ip':str(ip), 'port':str(port), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'error', 'msg': 'The connection was reset. If you do not detect new barcodes, please refresh the page.'})
                return
            except Exception as e:
                app.logger.error('LAN connection closed for scanner (' + str(ip) + ':' + str(port) + ') due to error: ' + str(e))
                socketio.emit('Event_scannerNotification', {'title': 'Connection Error', 'ip':str(ip), 'port':str(port), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'error', 'msg': 'Connection error: ' + str(e) + '. Please check the connection and refresh the web page.'})
                return
            if len(rcvData) > 1:

                ### barcode handling logic:
                # is this the first time seeing the scanner?
                #   yes -> initialize variables, set initial timer to a value that ensures it will get read
                # has it been at least 30 seconds since we last recorded a barcode from this scanner?
                #   no -> Do not pass the barcode to the UI. Have we already logged it?
                #       yes -> do nothing (do not log it)
                #       no -> log a message saying the scanner scanned something before its time limit, and set a flag to prevent additional log messages
                #   yes -> Clear any "too soon" scanner flags. Reset the 30 second timer. Is this the first barcode we've scanned?
                #       yes -> append barcode+data to variable
                #       no -> is the barcode the same as the previous scan?
                #           yes -> update existing variable but dont append new one
                #           no -> append barcode+data to variable

                # convert raw barcode to a string with leading/trailing whitespace stripped and properly URL escaped
                scannedBarcode = str(escape(rcvData.decode('ascii'))).strip()

                # scannerData[ip address] = {'barcodes': deque, 'timer': time.time(), 'timerMsgFlag': 0}
                # scannerData[ip]['barcodes'] = [{'barcode': str, 'timestamp': datetime}, {'barcode': str, 'timestamp': datetime}, etc]
                scannerData = OmronVTInterfaceModule.ovtimconfig.scannerData
                
                if ip not in scannerData.keys():
                    scannerData[ip] = {'barcodes': deque(maxlen=1), 'timer': time.time() - 1000, 'timerMsgFlag': 0}
                    
                if time.time() - scannerData[ip]['timer'] < OmronVTInterfaceModule.ovtimconfig.scannerTimelimit:
                    if scannerData[ip]['timerMsgFlag'] == 0:
                        barcodeLogger.info('Received barcode from scanner (' + str(ip) + ':' + str(port) + '), but scanner time limit hasnt been reached (' + str(round(time.time() - scannerData[ip]['timer'], 1)) + ' seconds elapsed out of ' + str(OmronVTInterfaceModule.ovtimconfig.scannerTimelimit) + '). Data will be ignored and future notifications are surpressed until the time limit has elapsed. (Barcode: ' + scannedBarcode + ')')
                        scannerData[ip]['timerMsgFlag'] = 1
                else:
                    scannerData[ip]['timer'] = time.time()
                    scannerData[ip]['timerMsgFlag'] = 0

                    if len(scannerData[ip]['barcodes']) > 0:
                        if scannerData[ip]['barcodes'][-1]['barcode'] == scannedBarcode:
                            scannerData[ip]['barcodes'][-1] = {'barcode': scannedBarcode, 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S')}
                            barcodeLogger.info('Received barcode from scanner (' + str(ip) + ':' + str(port) + '): ' + scannedBarcode + ' | (The barcode was a duplicate of the previously scanned barcode)')
                            OmronVTInterfaceModule.ovtimconfig.currentBarcode = scannedBarcode
                            OmronVTInterfaceModule.ovtimconfig.currentBarcodeTimestamp = time.time()
                            socketio.emit('Event_scannerNotification', {'title': 'Barcode Read', 'ip':str(ip), 'port':str(port), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'update', 'msg': 'Barcode read: ' + scannedBarcode, 'data': list(scannerData[ip]['barcodes'])})
                        else:
                            scannerData[ip]['barcodes'].append({'barcode': scannedBarcode, 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S')})
                            barcodeLogger.info('[1]Received barcode from scanner (' + str(ip) + ':' + str(port) + '): ' + scannedBarcode)
                            OmronVTInterfaceModule.ovtimconfig.currentBarcode = scannedBarcode
                            OmronVTInterfaceModule.ovtimconfig.currentBarcodeTimestamp = time.time()
                            socketio.emit('Event_scannerNotification', {'title': 'Barcode Read', 'ip':str(ip), 'port':str(port), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'info', 'msg': 'Barcode read: ' + scannedBarcode, 'data': list(scannerData[ip]['barcodes'])})
                    else:
                        scannerData[ip]['barcodes'].append({'barcode': scannedBarcode, 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S')})
                        barcodeLogger.info('[2]Received barcode from scanner (' + str(ip) + ':' + str(port) + '): ' + scannedBarcode)
                        OmronVTInterfaceModule.ovtimconfig.currentBarcode = scannedBarcode
                        OmronVTInterfaceModule.ovtimconfig.currentBarcodeTimestamp = time.time()
                        socketio.emit('Event_scannerNotification', {'title': 'Barcode Read', 'ip':str(ip), 'port':str(port), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'info', 'msg': 'Barcode read: ' + scannedBarcode, 'data': list(scannerData[ip]['barcodes'])})
            
    # connects to the serial output device and sends it the last-read barcode
    @socketio.on('Event_startBarcodeOutput')
    def sendBarcode():
        app.logger.info('Event_startBarcodeOutput event received!')
        # initialize connection
        attemptNo = 1
        while True:
            app.logger.info('Establishing serial connection with inspection machine to send barcode data on port /dev/ttyTHS2/ (this is attempt #' + str(attemptNo) + ' of 3)')
            try:
                tm = OmronVTInterfaceModule.ovtimfunctions.TimeManager("/dev/ttyTHS2")
                app.logger.info('Serial connection established on port /dev/ttyTHS2')
                break
            except Exception as e:
                app.logger.error('Failed to establish serial connection to insection machine on port /dev/ttyTHS2 because of error: ' + str(e) + '. Retrying in 30 seconds (this was attempt #' + str(attemptNo) + ' of 3)')
                if attemptNo > 2:
                    socketio.emit('Event_scannerNotification', {'title': 'Failed to Establish Serial Connection', 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'errorSerial', 'msg': 'Could not establish serial connection to inspection machine because of error: ' + str(e) + ' (Attempt #' + str(attemptNo) + ' of 3). Please ensure the inspection machine is powered on and all cables and connectors are securely inserted. Selecting an inspection program on the inspection machine before attempting to connect may help. You must refresh this web page to attempt the connection again.'})
                    return
                else:
                    socketio.emit('Event_scannerNotification', {'title': 'Failed to Establish Serial Connection', 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'errorSerial', 'msg': 'Could not establish connection to inspection machine (Attempt #' + str(attemptNo) + ' of 3). Waiting 30 seconds before retrying.'})
                attemptNo += 1
                time.sleep(30)
                continue

        while True:
            if time.time() - OmronVTInterfaceModule.ovtimconfig.currentBarcodeTimestamp <= OmronVTInterfaceModule.ovtimconfig.barcodeOutputTimelimit:
                try:
                    tm.send(str(OmronVTInterfaceModule.ovtimconfig.currentBarcode.strip() + '\r\n').encode('utf-8'))
                    socketio.emit('Event_scannerNotification', {'title': 'Barcode Sent to Inspection Machine', 'ip':str(0), 'port':str(0), 'timestamp': datetime.now().strftime('%m/%d/%Y %H:%M:%S'), 'type': 'info', 'msg': 'Barcode sent to inspection machine: ' + str(OmronVTInterfaceModule.ovtimconfig.currentBarcode.strip()), 'data': str(OmronVTInterfaceModule.ovtimconfig.currentBarcode.strip())})
                    barcodeLogger.info('Sent barcode to inspection machine: ' + str(OmronVTInterfaceModule.ovtimconfig.currentBarcode.strip()))
                    time.sleep(OmronVTInterfaceModule.ovtimconfig.barcodeSleepTime)
                except Exception as e:
                    app.logger.error('Failed to send barcode (' + str(OmronVTInterfaceModule.ovtimconfig.currentBarcode.strip()) + ') to inspection machine because ' + str(e))
                    time.sleep(OmronVTInterfaceModule.ovtimconfig.barcodeSleepTime)
                    continue
            

    @socketio.on('Event_overwriteConfigFile')
    def overwriteConfigFile(jsonData):
        try:
            shutil.copy2(OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath, OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath.split('.')[0] + '_old.json')
        except Exception as e:
            return 'Failed to save config file. Error when backing up original config file: ' + str(e)

        try:
            with open(OmronVTInterfaceModule.ovtimconfig.karlboxConfigFilePath, 'w') as cfile:
                cfile.write(json.dumps(jsonData))
        except Exception as e:
            return "Failed to save config file. Error when overwriting config file: " + str(e)
        return "success"

    @socketio.on('Event_detectScannerInfo')
    def getScannerInfo(side):
        OmronVTInterfaceModule.ovtimfunctions.ethernetAutoDetect(side, OmronVTInterfaceModule.ovtimconfig.testLAN, app.logger, socketio)
    
    return app

app = create_app()