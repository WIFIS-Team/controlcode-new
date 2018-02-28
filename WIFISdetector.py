import numpy as np
import astropy.io.fits as fits
import socket
import os
import sys 
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QObject
from PyQt5.QtWidgets import QDialog, QApplication, QPushButton, QVBoxLayout
import matplotlib.pyplot as plt

from astropy.visualization import (PercentileInterval, LinearStretch,
                                   ImageNormalize)
from time import time, sleep
import traceback

# Define global variables here
servername = "192.168.0.20"
serverport = 5000
path_to_watch = "/Data/WIFIS/H2RG-G17084-ASIC-08-319/"
buffersize = 1024

 
class Formatter(object):
    def __init__(self, im):
        self.im = im
    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
	return 'x={:.01f}, y={:.01f}, z={:.01f}'.format(x, y, z)

class h2rg(QObject):

    updateText = pyqtSignal(str)
    plotSignal = pyqtSignal(np.ndarray,str)

    def __init__(self, h2rgstatus, switch1, switch2, calibrationcontrol):
        super(h2rg, self).__init__()

        self.servername = servername
        self.port = serverport
        self.buffersize = buffersize
        self.path = path_to_watch
        self.h2rgstatus = h2rgstatus
        self.switch1 = switch1
        self.switch2 = switch2
        self.calibrationcontrol = calibrationcontrol

        if self.calibrationcontrol == None:
            self.calibon = False
        else:
            self.calibon = True

        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.initialized = False
    
    def connect(self):
        self.printTxt("#### CONNECTING TO DETECTOR")
        self.s.connect((self.servername,self.port))
        self.connected = True
        self.h2rgstatus.setStyleSheet('color: blue')
        self.h2rgstatus.setText("H2RG Connected")
        self.printTxt("#### CONNECTED TO DETECTOR")

        return(True)
    
    def disconnect(self):
        if(self.connected):
            self.printTxt("#### DISCONNECTING FROM THE DETECTOR")
            self.s.close() 
            self.connected = False
            self.initialized = False 
            self.printTxt("#### DISCONNECTED")
            self.h2rgstatus.setStyleSheet('color: red')
            self.h2rgstatus.setText("H2RG Disconnected")
            return(True)
        
        return(False)
        
    def initialize(self):
        if(self.connected):
            self.printTxt("#### INITIALIZING")
            self.s.send("INITIALIZE1")
            response = self.s.recv(self.buffersize)
            self.printTxt(response)

            self.s.send("SETGAIN(12)")
            self.printTxt("#### Setting Gain")
            response = self.s.recv(buffersize)
            self.printTxt(response)

            self.s.send("SETDETECTOR(2,32)")
            self.printTxt("#### Setting Detector Channels")
            response = self.s.recv(buffersize)
            self.printTxt(response)

            self.s.send("SETENHANCEDCLK(1)")
            self.printTxt("#### Setting Clocking")
            response = self.s.recv(buffersize)
            self.printTxt(response)

            self.printTxt("#### INITIALIZED")
            self.initialized = True            
            self.h2rgstatus.setStyleSheet('color: green')
            return(True)
        
        return(False)
        
    def setParams(self):
        if(self.initialized):
            # Set to 18 dB gain setting
            self.s.send("SETGAIN(12)")
            response = self.s.recv(self.buffersize)
            
            # Set detector to 32 channel readout
            self.s.send("SETDETECTOR(2,32)")
            response = self.s.recv(self.buffersize)
        
            # Set to enhanced clocking
            self.s.send("SETENHANCEDCLK(1)")
            response = self.s.recv(self.buffersize)
            
            return(True)
        
        return(False)
      
    def writeObsData(self,directory,obsType,sourceName):
            f = open(directory+"/obsinfo.dat","w")
            f.write("Obs Type: "+obsType+"\n")
            f.write("Source: "+sourceName+"\n")

            telemf = open("/home/utopea/WIFIS-Team/controlcode/BokTelemetry.txt","r")

            for line in telemf:
                f.write(line)

            telemf.close()
            f.close()
                
    def exposeSF(self, sourceName):
        self.printTxt("ACQUIRING SINGLE FRAME")
        watchpath = self.path+"/Reference"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        
        self.s.send("ACQUIRESINGLEFRAME")
        response = self.s.recv(buffersize)
        self.printTxt(response)
        
        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]

        finalPath = watchpath+"/"+added[0]
        self.plotImage("Single Frame",1,finalPath, None)
        self.h2rgstatus.setStyleSheet('color: green')
        self.h2rgstatus.setText('H2RG Initialized')
        self.printTxt("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+sourceName)

        return(finalPath)

    def exposeCDS(self, sourceName):
        self.printTxt("ACQUIRING CDS FRAME")

        watchpath = self.path+"/CDSReference"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        
        self.s.send("ACQUIRECDS")
        response = self.s.recv(buffersize)
        self.printTxt(response)
 
        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]

        self.printTxt("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+sourceName +'\n')

        finalPath = watchpath+"/"+added[0]

        self.writeObsData(finalPath,'CDS',sourceName)
        self.h2rgstatus.setStyleSheet('color: green')
        self.h2rgstatus.setText('H2RG Initialized')

        self.plotImage("CDS",1,finalPath+"/Result/CDSResult.fits", None)

    def exposeRamp(self,nreads,nramps,obsType,sourceName, calib=False):
        if sourceName != "":
            self.printTxt("ACQUIRING RAMP FOR "+sourceName)
        else:
            self.printTxt("ACQUIRING RAMP")
        commandstring = "SETRAMPPARAM(1,%d,1,1.5,%d)" % (nreads,nramps)
        self.s.send(commandstring)
        response = self.s.recv(buffersize)
        
        watchpath = self.path+"/UpTheRamp"
        before = dict ([(f, None) for f in os.listdir (watchpath)])

        self.s.send("ACQUIRERAMP")
        response = self.s.recv(buffersize)
        self.printTxt(response)

        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]
        
        finalPath = watchpath+"/"+added[0]
        self.writeObsData(finalPath,obsType,sourceName)
        self.h2rgstatus.setStyleSheet('color: green')

        if not calib:
            f1 = open('/home/utopea/WIFIS-Team/wifiscontrol/obs.lst','w')
            f1.write(str(added[0]))
            f1.close()

        self.printTxt("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+sourceName +'\n')

        if nreads < 2:
            self.plotImage("Ramp",nreads,finalPath+"/H2RG_R01_M01_N01.fits", None, sourcename=sourceName)
        else:
            self.plotImage("Ramp",nreads,finalPath+"/H2RG_R01_M01_N01.fits", \
                    finalPath+"/H2RG_R01_M01_N%02d.fits" % nreads, sourcename=sourceName)
        
        return added

    def plotImage(self,obsType,nreads,fileName1,fileName2, sourcename=''):

        if(nreads < 2):
            hdu = fits.open(fileName1)
            image = hdu[0].data*1.0
            hdu.close()
        else:
            hdu1 = fits.open(fileName1)
            hdu2 = fits.open(fileName2)
            image = hdu2[0].data*1.0 - hdu1[0].data*1.0
            hdu1.close()
            hdu2.close()

        if fileName2 != None:
            self.plotSignal.emit(image, fileName2.split('/')[-1] + ' '+sourcename)
        else:
            self.plotSignal.emit(image, fileName1.split('/')[-1] + ' '+sourcename)


    def flatramp(self,sourcename, notoggle = False):
        if self.calibon:
            self.calibrationcontrol.flatsetup()
            sleep(7)
            sourcename = 'CalFlat ' + sourcename
            added = self.exposeRamp(5, 1, 'Ramp',sourcename, calib=True)

            f1 = open('/home/utopea/WIFIS-Team/wifiscontrol/flat.lst','w')
            f1.write(str(added[0]))
            f1.close()

            if not notoggle:
                self.calibrationcontrol.sourcesetup()
        else:
            self.printTxt("CALIBRATION CONTROL OFF...CONNECT AND RESTART GUI")

    def arcramp(self,sourcename, flat=False):
        if self.calibon:
            self.calibrationcontrol.arcsetup()
            sleep(3)
            sourcename = 'CalArc ' + sourcename
            added = self.exposeRamp(5, 1, 'Ramp', sourcename, calib=True)
            
            f1 = open('/home/utopea/WIFIS-Team/wifiscontrol/wave.lst','w')
            f1.write(str(added[0]))
            f1.close()

            if not flat:
                self.calibrationcontrol.sourcesetup()
        else:
            self.printTxt("CALIBRATION CONTROL OFF...CONNECT AND RESTART GUI")

    def takecalibrations(self, sourcename):
        if self.calibon:
            self.printTxt("STARTING CALIBRATIONS")
            self.arcramp(sourcename,flat=True)
            #self.calibrationcontrol.flatsetup()
            #sleep(7)
            self.flatramp(sourcename)
            self.printTxt("FINISHED CALIBRATIONS")
        else:
            self.printTxt("CALIBRATION CONTROL OFF...CONNECT AND RESTART GUI")


    def printTxt(self, s):
        self.updateText.emit(s)
	
class h2rgExposeThread(QThread):

    finished = pyqtSignal()
    updateText = pyqtSignal(str)

    def __init__(self,detector,exposureType,nreads=2,nramps=1,sourceName=""):
        QThread.__init__(self)

        self.detector = detector
        self.exposureType = exposureType
        #if exposureType == "Calibrations":
        #    self.exposureTypeText = "Calibrations"
        #else:
        #    self.exposureTypeText = self.exposureType.currentText()
        self.nreads = nreads
        #self.nreadsText = int(self.nreads.text())
        self.nramps = nramps
        #self.nrampsText = int(self.nramps.text())
        self.sourceName = sourceName
        #self.sourceNameText = self.sourceName.text()
        #self.progressbar = progressbar
        
    def __del__(self):
        self.wait()
        
    def run(self):

        try:
            if self.detector.connected == False:
                self.printTxt("####### Please connect the detector "+'\n'+\
                        "and initialize if not done already")
                return

            self.printTxt("####### STARTING EXPOSURE")
            #if self.exposureTypeText != "Calibrations":
            #    self.exposureTypeText = self.exposureType.currentText()
            #self.nreadsText = int(self.nreads.text())
            #self.nrampsText = int(self.nramps.text())
            #self.sourceNameText = self.sourceName.text()

            self.nreadsText = self.nreads
            self.nrampsText = self.nramps
            self.sourceNameText = self.sourceName
            self.exposureTypeText = self.exposureType

            if(self.exposureTypeText == "Single Frame"):
                output = self.detector.exposeSF(self.sourceNameText)
            elif(self.exposureTypeText == "CDS"):
                output = self.detector.exposeCDS(self.sourceNameText)
            elif(self.exposureTypeText == "Ramp"):
                output = self.detector.exposeRamp(self.nreadsText, self.nrampsText, "Ramp", \
                        self.sourceNameText)
            elif(self.exposureTypeText == "Flat Ramp"):
                output = self.detector.flatramp(self.sourceNameText)
            elif(self.exposureTypeText == "Arc Ramp"):
                output = self.detector.arcramp(self.sourceNameText)
            elif(self.exposureTypeText == "Calibrations"):
                output = self.detector.takecalibrations(self.sourceNameText)

            self.printTxt("####### FINISHED EXPOSURE")

        except Exception as e:
            print e
            print traceback.print_exc()
            self.printTxt("Something Went Wrong with the Exposure, check terminal")
            return

        self.finished.emit()

    def printTxt(self, s):
        self.updateText.emit(s)

class h2rgProgressThread(QThread):

    finished = pyqtSignal()
    updateBar = pyqtSignal(int)

    def __init__(self, exposureType, nreads=2,nramps=1):
        QThread.__init__(self)

        self.nreads = nreads
        #self.nreadsText = int(self.nreads.text())
        self.nramps = nramps
        #self.nrampsText = int(self.nramps.text())
        self.exposureType = exposureType

        #if self.exposureType != "Calibrations":
        #    self.exposureTypeText = self.exposureType.currentText()
        
    def __del__(self):
        self.wait()
        
    def run(self):
        #if self.exposureType != "Calibrations":
        #    self.exposureTypeText = self.exposureType.currentText()
        #else:
        #    return
        if self.exposureType in ["Calibrations", "Single Frame","CDS"]:
            return
       
        self.sleep(4)
        t1 = time()
        n_seconds = self.nreads * self.nramps * 1.5
        while (time() - t1) < n_seconds:
            self.updateBar.emit(int((time() - t1)/n_seconds * 100))
            #self.progressbar.setValue(int((time() - t1)/n_seconds * 100))

        self.finished.emit()



