import numpy as np
import astropy.io.fits as fits
import socket
import os
import sys 
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

from PyQt5.QtWidgets import QDialog, QApplication, QPushButton, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt

from astropy.visualization import (PercentileInterval, LinearStretch,
                                   ImageNormalize)
from time import time, sleep
from calibration_functions import CalibrationControl
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

class h2rg:
    def __init__(self, h2rgstatus, switch1, switch2, plotwindow, OutputText):
        self.servername = servername
        self.port = serverport
        self.buffersize = buffersize
        self.path = path_to_watch
        self.h2rgstatus = h2rgstatus
        self.switch1 = switch1
        self.switch2 = switch2
        self.calibrationcontrol = CalibrationControl(self.switch1, self.switch2) 
        self.plotwindow = plotwindow
        self.OutputText = OutputText

        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.initialized = False
    
    def connect(self):
        self.OutputText.setText("#### CONNECTING TO DETECTOR ####"
        self.s.connect((self.servername,self.port))
        self.connected = True
        self.h2rgstatus.setStyleSheet('color: blue')
        self.h2rgstatus.setText("H2RG Connected")
        self.OutputText.setText("#### CONNECTED TO DETECTOR ####"

        return(True)
    
    def disconnect(self):
        if(self.connected):
            self.OutputText.setText("#### DISCONNECTING FROM THE DETECTOR ####")
            self.s.close() 
            self.connected = False
            self.initialized = False 
            self.OutputText.setText("#### DISCONNECTED ####")
            return(True)
        
        return(False)
        
    def initialize(self):
        if(self.connected):
            self.s.send("INITIALIZE1")
            response = self.s.recv(self.buffersize)
            self.initialized = True            
            self.h2rgstatus.setSyleSheet('color: green')
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
                
    def exposeSF(self):
        self.OutputText.setText("ACQUIRING SINGLE FRAME")
        watchpath = self.path+"/Reference"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        
        self.s.send("ACQUIRESINGLEFRAME")
        response = self.s.recv(buffersize)
        self.OutputText.setText(response)
        
        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]

        finalPath = watchpath+"/"+added[0]
        self.plotImage("Single Frame",1,finalPath, None)
        self.h2rgstatus.setStyleSheet('color: green')
        self.h2rgstatus.setText('H2RG Initialized')
        self.OutputText.setText("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+sourceName)

        return(finalPath)

    def exposeCDS(self, sourceName):
        self.OutputText.setText("ACQUIRING CDS Frame")

        watchpath = self.path+"/CDSReference"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        
        self.s.send("ACQUIRECDS")
        response = self.s.recv(buffersize)
        self.OutputText.setText(response)
 
        self.l1["text"] = response
       
        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]

        self.OutputText.setText("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+sourceName +'\n')

        self.writeObsData(finalPath,'CDS',sourceName)
        self.h2rgstatus.setStyleSheet('color: green')
        self.h2rgstatus.setText('H2RG Initialized')

        self.plotImage("CDS",1,finalPath+"/Result/CDSResult.fits", None)

    def exposeRamp(self,nreads,nramps,obsType,sourceName):
        if sourceName != "":
            self.OutputText.setText("ACQUIRING RAMP FOR "+sourceName)
        else:
            self.OutputText.setText("ACQUIRING RAMP")
        commandstring = "SETRAMPPARAM(1,%d,1,1.5,%d)" % (nreads,nramps)
        self.s.send(commandstring)
        response = self.s.recv(buffersize)
        
        watchpath = self.path+"/UpTheRamp"
        before = dict ([(f, None) for f in os.listdir (watchpath)])

        self.s.send("ACQUIRERAMP")
        response = self.s.recv(buffersize)
        self.OutputText.setText(response)

        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]
        
        finalPath = watchpath+"/"+added[0]
        self.writeObsData(finalPath,obsType,sourceName)
        self.h2rgstatus.setStyleSheet('color: green')

        self.OutputText.setText("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+sourceName +'\n')

        if nreads < 2:
            self.plotImage("Ramp",nreads,finalPath+"/H2RG_R01_M01_N01.fits", None)
        else:
            self.plotImage("Ramp",nreads,finalPath+"/H2RG_R01_M01_N01.fits", \
                    finalPath+"/H2RG_R01_M01_N%02d.fits" % nreads)
        
        return(finalPath)

    
    @pyqtSlot(str,str,str)    
    def plotImage(self,obsType,nreads,fileName1,fileName2):

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

        norm = ImageNormalize(image, interval=PercentileInterval(99.5),
                      stretch=LinearStretch())

        try:
            self.plotwindow.figure.clear()

            ax = self.plotwindow.figure.add_subplot(1, 1, 1)
            im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
            ax.format_coord = Formatter(im)
            ax.set_title(fileName1.split('/')[-1])
            self.plotwindow.figure.colorbar(im)

            self.plotwindow.canvas.draw()
        except Exception as e:
            self.OutputText.setText(e)
            self.OutputText.setText(traceback.print_exc())
            self.OutputText.setText("SOMETHING WENT WRONG WITH THE PLOTTING")


    def flatramp(self,sourcename):
        self.calibrationcontrol.flatsetup()
        sleep(7)
        sourcename = 'CalFlat ' + sourcename
        added = self.exposeRamp(5, 1, 'Ramp',sourcename)

        f1 = open('flat.lst','w')
        f1.write(str(added[0]))
        f1.close()

        self.calibrationcontrol.sourcesetup()

    def arcramp(self,sourcename, flat=False):
        self.calibrationcontrol.arcsetup()
        sleep(3)
        sourcename = 'CalArc ' + sourcename
        added = self.exposeRamp(5, 1, 'Ramp', sourcename)
        
        f1 = open('wave.lst','w')
        f1.write(str(added[0]))
        f1.close()

        if not flat:
            self.calibrationcontrol.sourcesetup()

    def takecalibrations(self, sourcename):
        self.OutputText.setText("STARTING CALIBRATIONS")
        self.arcramp(sourcename,flat=True)
        self.calibrationcontrol.flatsetup()
        sleep(7)
        self.flatramp(sourcename)
        self.OutputText.setText("FINISHED CALIBRATIONS")
	
class h2rgExposeThread(QThread):

    finished = pyqtSignal(str,str,str)

    def __init__(self,detector,exposureType, progressbar,OutputText,nreads=2,nramps=1,sourceName="None"):
        QThread.__init__(self)
        self.detector = detector
        self.exposureType = exposureType
        if exposureType == "Calibrations":
            self.exposureTypeText = "Calibrations"
        else:
            self.exposureTypeText = self.exposureType.currentText()
        self.nreads = nreads
        self.nreadsText = int(self.nreads.text())
        self.nramps = nramps
        self.nrampsText = int(self.nramps.text())
        self.sourceName = sourceName
        self.sourceNameText = self.sourceName.text()
        self.progressbar = progressbar
        self.OutputText = OutputText
        
    def __del__(self):
        self.wait()
        
    def run(self):

        if self.detector.connected == False:
            self.OutputText.setText("####### Please connect the detector "+'\n'+\
                    "and initialize if not done already #######")
            return

        self.OutputText.setText("####### STARTING EXPOSURE #######")
        if self.exposureTypeText != "Calibrations":
            self.exposureTypeText = self.exposureType.currentText()
        self.nreadsText = int(self.nreads.text())
        self.nrampsText = int(self.nramps.text())
        self.sourceNameText = self.sourceName.text()

        progressbar = h2rgProgressThread(self.progressbar, self.exposureType, nreads=self.nreads,\
                nramps=self.nramps)
        progressbar.start()

        if(self.exposureTypeText == "Single Frame"):
            output = self.detector.exposeSF()
            self.finished.emit("SF",output,"None")
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
        progressbar.reset()
        self.OutputText.setText("####### FINISHED EXPOSURE #######")

class h2rgProgressThread(QThread):

    finished = pyqtSignal(str,str,str)

    def __init__(self,progressbar, exposureType, nreads=2,nramps=1):
        QThread.__init__(self)

        self.progressbar = progressbar
        self.nreads = nreads
        self.nreadsText = int(self.nreads.text())
        self.nramps = nramps
        self.nrampsText = int(self.nramps.text())
        self.exposureType = exposureType
        if self.exposureType != "Calibrations":
            self.exposureTypeText = self.exposureType.currentText()
        
        self.progressbar.setMinimum(0)
        self.progressbar.setMaximum(100)
        self.progressbar.setValue(0)

    def __del__(self):
        self.wait()
        
    def run(self):
        if self.exposureType != "Calibrations":
            self.exposureTypeText = self.exposureType.currentText()
        else:
            return
       
        self.sleep(4)
        self.nreadsText = int(self.nreads.text())
        self.nrampsText = int(self.nramps.text())
        t1 = time()
        n_seconds = self.nreadsText * self.nrampsText * 1.5
        while (time() - t1) < n_seconds:
            self.progressbar.setValue(int((time() - t1)/n_seconds * 100))

    def reset(self):
        self.progressbar.setValue(0)



