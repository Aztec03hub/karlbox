import os
import sys

# create a reference to the module instance that can be used from other modules
this = sys.modules[__name__]

# configuration file where profiles are stored
this.karlboxConfigFilePath = 'karlboxconfig.json' #os.path.join(os.path.join(os.getcwd(), 'static'), 'karlboxconfig.json')

# logging settings
this.logConfigWebapp = {'logname': 'webapp', 'basefilename': 'webapp.log', 'logdirectory': os.path.join('log', 'webapp'), 'loglevel': 'DEBUG', 'loghandler': None, 'logformatter': None, 'logmsgformat': '%(asctime)s|%(levelname)-8s|%(message)s', 'logdateformat':'%Y/%m/%d %H:%M:%S', 'logrotatecount': 30}
this.logConfigBarcode = {'logname': 'barcode', 'basefilename': 'barcode.log', 'logdirectory': os.path.join('log', 'barcodes'), 'loglevel': 'INFO', 'loghandler': None, 'logformatter': None, 'logmsgformat': '%(asctime)s|%(levelname)-8s|%(message)s', 'logdateformat':'%Y/%m/%d %H:%M:%S', 'logrotatecount': 30}

# global variables
# TODO determine if these are necessary
this.activeProfile = '' # tracks the active scanner profile
this.dictProfiles = {} # holds all profile data 

this.scannerBarcodes = {} # scannerBarcodes['192.168.188.1'] = []
this.scannerTimers = {} # scannerTimers['192.168.188.1'] = []
this.scannerTimestamps = {} # scannerTimestamps['192.168.188.1'] = []

this.scannerData = {}
this.scannerTimelimit = 0.1 # in seconds
this.barcodeOutputTimelimit = 30 # in seconds
this.barcodeSleepTime = 10 # in seconds

this.currentBarcode = '' # global
this.currentBarcodeTimestamp = 0

# TODO probably remove this
# config options in ini file
this.possibleIniValues = ['bsmodel', 'bsname', 'bsmac', 'bscommtype', 'bsip', 'bsport', 'bsbaud', 'bsbytesize', 'bsstopbit', 'bsparity', 'tsmodel', 'tsname', 'tsmac', 'tscommtype', 'tsip', 'tsport', 'tsbaud', 'tsbytesize', 'tsstopbit', 'tsparity']

# TODO probably not use this for 1.0 release with plans for later release after better integration
# model names
this.possibleModelValues = ['microhawk mv', 'microhawk mv-20', 'microhawk mv-30', 'microhawk mv-40', 'microhawk mv-45', 'microhawk id-20', 'microhawk id-30', 'microhawk id-40', 'microhawk id-45', 'id-45', 'f420', 'f420-f', 'f430', 'f430-f']

this.testLAN = {} # used to track temporary data between threads


