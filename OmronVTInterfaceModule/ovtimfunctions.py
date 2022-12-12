import serial
from timeit import default_timer as clk
import time
import json
import os
import logging
import logging.handlers
import ipaddress
from telnetlib import Telnet
import threading
import socket

class TimeManager(object):
	def __init__(self, port, baudrate=9600):
		self.ser = serial.Serial(port, baudrate=baudrate, bytesize=8, stopbits=1, parity='N')
		time.sleep(3)
		self.ser.reset_input_buffer()
		self.ser.reset_output_buffer()

	def send(self, tx):
		tx = bytearray(tx)
		#print(tx)
		try:
			self.ser.write(tx)
			time.sleep(2)
			self.ser.flush()
			time.sleep(2)
		except serial.SerialException as e:
			if e.args == (5, "WriteFile", "Access is denied."):
				raise IOError(serial.SerialException.errno.ENOENT, "Serial port disappeared.", self.ser.portstr)
			else:
				raise

	def receive(self):
		rx = bytearray()
		delay = 10e-3 # s
		timeout = 5 # s
		end_time = clk() + timeout
		while True:
			time_remaining = end_time - clk()
			if time_remaining < 0:
				break
			rx += self.ser.read(self.ser.inWaiting())
			if 0 in rx:
				break
			time.sleep(delay)
		if time_remaining <= 0:
			raise IOError(serial.SerialTimeoutException, "Communication timed out.")
		return rx

# initialize logging
# returns configured logger object
# Usage: app.logger = initLogging(app.instance_path, ovtimconfig.logConfigWebapp)
def initLogging(appInstancePath, configDict):
	# create log directory if it doesnt exist
	logDirectoryPath = os.path.join(appInstancePath, configDict['logdirectory'])
	if not os.path.isdir(logDirectoryPath):
		os.makedirs(logDirectoryPath, exist_ok=True)

	# initialize handler, formatter, and log level
	logFilepath = os.path.join(logDirectoryPath, configDict['basefilename'])
	configDict['loghandler'] = logging.handlers.TimedRotatingFileHandler(filename=logFilepath, when='midnight', backupCount=configDict['logrotatecount'])
	configDict['logformatter'] = logging.Formatter(configDict['logmsgformat'], datefmt=configDict['logdateformat'])
	configDict['loghandler'].setFormatter(configDict['logformatter'])
	logger = logging.getLogger(configDict['logname'])
	logger.addHandler(configDict['loghandler'])
	logger.setLevel(configDict['loglevel'])
	logger.critical('Logging started for ' + str(configDict['logname']))
	return logger

# read and parse config file
# returns tuple: (returncode, dict containing all profiles, name of active profile, active profile has bottom side = 1 else 0, active profile has top side = 1 else 0)
# returncode values:
# 	0	no error
#	1	warning but all values could be parsed correctly (example no active profile)
#	2	error which prevents at least 1 profile from being parsed. (example no IP set) dictProfiles and activeprofiles will still return values
#	3	error which prevents the config file from being parsed (no profiles, both top and bottom sides have errors, etc)
def readConfig(weblogger, karlboxConfigFilePath, possibleIniValues, possibleModelValues):

	dictProfiles = {}
	returnCode = 0
	activeProfile = ''
	bottomEnabled = 0
	topEnabled = 0
	#returnTuple = ((returnCode, dictProfiles, activeProfile, bottomEnabled, topEnabled))

	karlboxConfig = json.load(open(karlboxConfigFilePath, 'r'))

	# check for existence of main section and if active profile is set
	try:
		if len(karlboxConfig['profiles']) <= 1:
			weblogger.error('Config file: no profiles saved or main section missing')
			returnCode = 3
			return ((returnCode, dictProfiles, activeProfile, bottomEnabled, topEnabled))
		if 'main' in karlboxConfig:
			if 'activeProfile' in karlboxConfig['main']:
				if len([x for x in karlboxConfig['profiles'] if x['profilename'] == karlboxConfig['main']['activeProfile']]) > 0:
					activeProfile = karlboxConfig['main']['activeProfile']
					weblogger.debug('Config file: active profile: ' + str(activeProfile))
				else:
					weblogger.warning('Config file: active profile not in config file')
					returnCode = 1
			else:
				weblogger.warning('Config file: active profile not set')
				returnCode = 1
		else:
			weblogger.error('Config file: error reading config- missing main section')
			returnCode = 3
			return ((returnCode, dictProfiles, activeProfile, bottomEnabled, topEnabled))
	except Exception as e:
		weblogger.error('Config file: error reading config- general exception reading sections: ' + str(e))
		returnCode = 3
		return ((returnCode, dictProfiles, activeProfile, bottomEnabled, topEnabled))
	
	# store all profiles
	for profile in karlboxConfig["profiles"]:
		profilename = profile['profilename']
		try:
			dictProfiles[profilename] = {}
			for key in possibleIniValues:
				if key in profile.keys():
					dictProfiles[profilename][key] = profile[key]
				else:
					dictProfiles[profilename][key] = ''
		except Exception as e:
			weblogger.error('Config file: general exception reading profile values: ' + str(e))
			returnCode = 2
			continue
 
		# check for existence of and validate values
		# bottom scanner
		dictProfiles[profilename]['bsenabled'] = 1
		if str(dictProfiles[profilename]['bscommtype']).lower() != 'rs232': # if commtype is not rs 232, it should be ethernet or "unknown" (default to ethernet)
			# check for valid IP
			dictProfiles[profilename]['bscommtype'] = 'ethernet'
			try:
				ip = ipaddress.ip_address(dictProfiles[profilename]['bsip'])
			except Exception as e:
				weblogger.warning('Config file: invalid bsip for ethernet commType: ' + str(dictProfiles[profilename]['bsip']) + ' (error msg): ' + str(e))
				dictProfiles[profilename]['bsenabled'] = 0
				returnCode = 2

			# check for valid port
			try:
				port = int(dictProfiles[profilename]['bsport'])
				if 1 <= port <= 65535:
					pass
				else:
					raise Exception
			except Exception:
				weblogger.warning('Config file: invalid bsport for ethernet commType: ' + str(dictProfiles[profilename]['bsport']))
				dictProfiles[profilename]['bsenabled'] = 0
				returnCode = 2
		else: # commtype is rs232
			# (attempt to) check for valid port
			try:
				if not str(dictProfiles[profilename]['bsport']).lower().startswith('com') and str(dictProfiles[profilename]['bsport']).lower().find('tty') == -1:
					# port doesnt start with com or contain tty in the value
					weblogger.warning('Config file: invalid bsport for serial commType: ' + str(dictProfiles[profilename]['bsport']))
					dictProfiles[profilename]['bsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid bsport for serial commType: ' + str(dictProfiles[profilename]['bsport']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['bsenabled'] = 0
				returnCode = 2
			
			# check for valid baud rate
			try:
				if int(dictProfiles[profilename]['bsbaud']) not in serial.Serial.BAUDRATES:
					weblogger.warning('Config file: invalid bsbaud for serial commType: ' + str(dictProfiles[profilename]['bsbaud']))
					dictProfiles[profilename]['bsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid bsbaud for serial commType: ' + str(dictProfiles[profilename]['bsbaud']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['bsenabled'] = 0
				returnCode = 2
			
			# check for valid byte size
			try:
				if int(dictProfiles[profilename]['bsbytesize']) not in serial.Serial.BYTESIZES:
					weblogger.warning('Config file: invalid bsbytesize for serial commType: ' + str(dictProfiles[profilename]['bsbytesize']))
					dictProfiles[profilename]['bsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid bsbytesize for serial commType: ' + str(dictProfiles[profilename]['bsbytesize']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['bsenabled'] = 0
				returnCode = 2
			
			# check for valid stop bit
			try:
				if int(dictProfiles[profilename]['bsstopbit']) not in serial.Serial.STOPBITS:
					weblogger.warning('Config file: invalid bsstopbit for serial commType: ' + str(dictProfiles[profilename]['bsstopbit']))
					dictProfiles[profilename]['bsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid bsstopbit for serial commType: ' + str(dictProfiles[profilename]['bsstopbit']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['bsenabled'] = 0
				returnCode = 2
			
			# check for valid parity
			try:
				if str(dictProfiles[profilename]['bsparity']) not in serial.Serial.PARITIES:
					weblogger.warning('Config file: invalid bsparity for serial commType: ' + str(dictProfiles[profilename]['bsparity']))
					dictProfiles[profilename]['bsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid bsparity for serial commType: ' + str(dictProfiles[profilename]['bsparity']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['bsenabled'] = 0
				returnCode = 2
		# check for valid model number
		try:
			if str(dictProfiles[profilename]['bsmodel']).lower() not in possibleModelValues:
				dictProfiles[profilename]['bsmodel'] = 'Other Scanner'
		except Exception:
			dictProfiles[profilename]['bsmodel'] = 'Other Scanner'

		# top scanner
		dictProfiles[profilename]['tsenabled'] = 1
		if str(dictProfiles[profilename]['tscommtype']).lower() != 'rs232':
			dictProfiles[profilename]['tscommtype'] = 'ethernet'
			# check for valid IP
			try:
				ip = ipaddress.ip_address(dictProfiles[profilename]['tsip'])
			except Exception as e:
				weblogger.warning('Config file: invalid tsip for ethernet commType: ' + str(dictProfiles[profilename]['tsip']) + ' (error msg): ' + str(e))
				dictProfiles[profilename]['tsenabled'] = 0
				returnCode = 2

			# check for valid port
			try:
				port = int(dictProfiles[profilename]['tsport'])
				if 1 <= port <= 65535:
					pass
				else:
					raise Exception
			except Exception:
				weblogger.warning('Config file: invalid tsport for ethernet commType: ' + str(dictProfiles[profilename]['tsport']))
				dictProfiles[profilename]['tsenabled'] = 0
				returnCode = 2
		else:
			# (attempt to) check for valid port
			try:
				if not str(dictProfiles[profilename]['tsport']).lower().startswith('com') and str(dictProfiles[profilename]['tsport']).lower().find('tty') == -1:
					# port doesnt start with com or contain tty in the value
					weblogger.warning('Config file: invalid tsport for serial commType: ' + str(dictProfiles[profilename]['tsport']))
					dictProfiles[profilename]['tsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid tsport for serial commType: ' + str(dictProfiles[profilename]['tsport']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['tsenabled'] = 0
				returnCode = 2
			
			# check for valid baud rate
			try:
				if int(dictProfiles[profilename]['tsbaud']) not in serial.Serial.BAUDRATES:
					weblogger.warning('Config file: invalid tsbaud for serial commType: ' + str(dictProfiles[profilename]['tsbaud']))
					dictProfiles[profilename]['tsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid tsbaud for serial commType: ' + str(dictProfiles[profilename]['tsbaud']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['tsenabled'] = 0
				returnCode = 2
			
			# check for valid byte size
			try:
				if int(dictProfiles[profilename]['tsbytesize']) not in serial.Serial.BYTESIZES:
					weblogger.warning('Config file: invalid tsbytesize for serial commType: ' + str(dictProfiles[profilename]['tsbytesize']))
					dictProfiles[profilename]['tsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid tsbytesize for serial commType: ' + str(dictProfiles[profilename]['tsbytesize']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['tsenabled'] = 0
				returnCode = 2
			
			# check for valid stop bit
			try:
				if int(dictProfiles[profilename]['tsstopbit']) not in serial.Serial.STOPBITS:
					weblogger.warning('Config file: invalid tsstopbit for serial commType: ' + str(dictProfiles[profilename]['tsstopbit']))
					dictProfiles[profilename]['tsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid tsstopbit for serial commType: ' + str(dictProfiles[profilename]['tsstopbit']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['tsenabled'] = 0
				returnCode = 2
			
			# check for valid parity
			try:
				if str(dictProfiles[profilename]['tsparity']) not in serial.Serial.PARITIES:
					weblogger.warning('Config file: invalid tsparity for serial commType: ' + str(dictProfiles[profilename]['tsparity']))
					dictProfiles[profilename]['tsenabled'] = 0
					returnCode = 2
			except Exception as e:
				weblogger.warning('Config file: invalid tsparity for serial commType: ' + str(dictProfiles[profilename]['tsparity']) + '(error msg): ' + str(e))
				dictProfiles[profilename]['tsenabled'] = 0
				returnCode = 2
		# check for valid model number
		try:
			if str(dictProfiles[profilename]['tsmodel']).lower() not in possibleModelValues:
				dictProfiles[profilename]['tsmodel'] = 'Other Scanner'
		except Exception:
			dictProfiles[profilename]['tsmodel'] = 'Other Scanner'
		# check if there is an active profile and if not, set it to first available profile that does not have errors
		if activeProfile == '':
			weblogger.debug('Config file: No active profile set; setting to first found valid profile: ' + str(profilename))
			activeProfile = profilename
		if profilename == activeProfile:
			bottomEnabled = dictProfiles[profilename]['bsenabled']
			topEnabled = dictProfiles[profilename]['tsenabled']
	return ((returnCode, dictProfiles, activeProfile, bottomEnabled, topEnabled))

def testTelnetConn(deviceIP, devicePort, testLAN, weblogger):
	try:
		tnclient = Telnet(str(deviceIP), int(devicePort), 5) #timeout is 5 seconds
		tnclient.close()
		testLAN[threading.current_thread().name] = 1
	except socket.timeout:
		pass
	except Exception as e:
		weblogger.debug('Scanner (' + str(deviceIP) + ':' + str(devicePort) + ') not connected via LAN- encountered error while connecting: ' + str(e))
		testLAN[threading.current_thread().name] = 0

def ethernetAutoDetect(side, testLAN, weblogger, socketio):
	devicesFound = {}
	broadcastIP = '192.168.188.255'
	
	def listenerHandler(listener):
		weblogger.debug('ScannerAutoDetect- Listener started')
		while testLAN[threading.current_thread().name] == 0:
			if time.time() - searchTimeoutTimer > 10:
				#app.logger.debug('ScannerAutoDetect- Timeout reached for finding new devices')
				return
			try:
				data, addr = listener.recvfrom(1024)
				deviceParameters = data.decode().split(',')
				if deviceParameters[6] != 'espip':
					devicesFound["deviceMac"] = deviceParameters[5]
					#if deviceMac not in devicesFound:
					devicesFound["deviceIP"] = deviceParameters[6]
					devicesFound["deviceTCP1"] = deviceParameters[14]
					devicesFound["deviceTCP2"] = deviceParameters[15]
					devicesFound["deviceUserName"] = deviceParameters[17]
					devicesFound["deviceModel"] = str(deviceParameters[19]).split('=')[1]
					devicesFound["deviceSerial"] = str(deviceParameters[22]).split('=')[1]
					devicesFound["deviceFirmware"] = str(deviceParameters[23]).split('=')[1]
					devicesFound["deviceWeblink"] = str(deviceParameters[24]).split('=')[1]
					weblogger.debug('ScannerAutoDetect- Found new device: deviceMac: {}, deviceIP: {}, deviceTCP1: {}, deviceTCP2: {}, deviceUserName: {}, deviceModel: {}, deviceSerial: {}, deviceFirmware: {}, deviceWeblink: {}'.format(devicesFound["deviceMac"], devicesFound["deviceIP"], devicesFound["deviceTCP1"], devicesFound["deviceTCP2"], devicesFound["deviceUserName"], devicesFound["deviceModel"], devicesFound["deviceSerial"], devicesFound["deviceFirmware"], devicesFound["deviceWeblink"]))
					testLAN[threading.current_thread().name] = 1
					return
					#devicesFound.append(deviceMac) # add to devices list
					#searchTimeoutTimer = time.time() # reset timer to continue scanning for other devices
				time.sleep(1)
			except Exception as e:
				weblogger.debug('ScannerAutoDetect- Thread ' + str(threading.current_thread().name) + ' encountered error while listening for broadcast message: ' + str(e))
				time.sleep(1)
				pass

	weblogger.info('ScannerAutoDetect- Trying to auto-detect compatible microhawk device connected via ethernet...')
	weblogger.debug('ScannerAutoDetect- Creating socket connections')
	server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
	listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
	listener.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
	#server.settimeout(10)
	server.settimeout(0)
	listener.settimeout(0)

	weblogger.debug('ScannerAutoDetect- Binding sockets')
	listener.bind(("<broadcast>", 30717))
	server.bind(("", 30717))
	
	weblogger.debug('ScannerAutoDetect- Setting up listener thread')
	searchTimeoutTimer = time.time()
	t = threading.Thread(target=listenerHandler, args=(listener, ))
	t.setDaemon(True)
	testLAN[t.name] = 0
	t.start()

	startTimer = time.time()
	message = b"<op,019,00,FF:FF:FF:FF:FF:FF,255.255.255.255,espmac,espip,0,0>"
	server.sendto(message, (broadcastIP, 30717))
	weblogger.debug("ScannerAutoDetect- Broadcast message sent")
	attempts = 1
	while testLAN[t.name] == 0:
		if time.time() - startTimer > 5: # timeout 5 seconds
			if attempts > 2:
				weblogger.info('ScannerAutoDetect- Search finished, no compatible devices found')
				socketio.emit('Event_detectScannerInfoResult', {'result':'failure', 'side':side, 'ip':str(-1), 'tcp1':str(-1), 'name': '', 'model': '', 'mac':''})
				testLAN[t.name] = 0
				return
			else:
				attempts += 1
				startTimer = time.time()
				weblogger.debug('ScannerAutoDetect- No response in 5 seconds, resending broadcast (attempt ' + str(attempts) + ')')
				server.sendto(message, (broadcastIP, 30717))

	#app.logger.debug('ScannerAutoDetect- Search finished, found device')
	#app.logger.debug(devicesFound)
	if "deviceIP" in devicesFound.keys():
		weblogger.info('ScannerAutoDetect- Compatible Device Found: ' + str(devicesFound["deviceIP"]))
		socketio.emit('Event_detectScannerInfoResult', {'result':'success', 'side':side, 'ip':str(devicesFound["deviceIP"]), 'tcp1':str(devicesFound["deviceTCP1"]), 'name': str(devicesFound["deviceUserName"]), 'model': str(devicesFound["deviceModel"]), 'mac':str(devicesFound["deviceMac"])})
		return
	else:
		weblogger.info('ScannerAutoDetect- No compatible devices found')
		socketio.emit('Event_detectScannerInfoResult', {'result':'failure', 'side':side, 'ip':str(-1), 'tcp1':str(-1), 'name': '', 'model': '', 'mac':''})
		return