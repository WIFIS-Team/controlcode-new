import numpy as np
import astropy.io.fits as fits
import socket
import os
import sys
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
import matplotlib.pyplot as plt
from astropy.visualization import (PercentileInterval, LinearStretch,
                                   ImageNormalize)
from time import time

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
    def __init__(self):
        self.servername = servername
        self.port = serverport
        self.buffersize = buffersize
        self.path = path_to_watch
        
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.initialized = False
    
    def connect(self):
        self.s.connect((self.servername,self.port))
        self.connected = True
        
        return(True)
    
    def disconnect(self):
        if(self.connected):
            self.s.close() 
            self.connected = False
            self.initialized = False 
            return(True)
        
        return(False)
        
    def initialize(self):
        if(self.connected):
            self.s.send("INITIALIZE1")
            response = self.s.recv(self.buffersize)
            self.initialized = True            
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
        watchpath = self.path+"/Reference"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        
        self.s.send("ACQUIRESINGLEFRAME")
        response = self.s.recv(buffersize)
        
        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]

        finalPath = watchpath+"/"+added[0]
        return(finalPath)
        
    def exposeRamp(self,nreads,nramps,obsType,sourceName):
        print "ACQUIRING RAMP for "+sourceName
        commandstring = "SETRAMPPARAM(1,%d,1,1.5,%d)" % (nreads,nramps)
        self.s.send(commandstring)
        response = self.s.recv(buffersize)
        
        watchpath = self.path+"/UpTheRamp"
        before = dict ([(f, None) for f in os.listdir (watchpath)])

        self.s.send("ACQUIRERAMP")
        response = self.s.recv(buffersize)

        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]
        
        finalPath = watchpath+"/"+added[0]
        self.writeObsData(finalPath,obsType,sourceName)
        print "FINISHED ACQUIRING RAMP"        
        return(finalPath)
    
    @pyqtSlot(str,str,str)    
    def plotImage(self,obsType,fileName1,fileName2):
        hdu = fits.open(fileName1)
        image = hdu[0].data*1.0
        
        norm = ImageNormalize(image, interval=PercentileInterval(99.5),
                              stretch=LinearStretch())
                              
        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
        ax.format_coord = Formatter(im)
        ax.set_title(fileName1)
        fig.colorbar(im)
        plt.show()
	
class h2rgExposeThread(QThread):

    finished = pyqtSignal(str,str,str)

    def __init__(self,detector,exposureType,nreads=2,nramps=1,sourceName="None"):
        QThread.__init__(self)
        self.detector = detector
        self.exposureType = exposureType
        self.exposureTypeText = self.exposureType.currentText()
        self.nreads = nreads
        self.nreadsText = int(self.nreads.toPlainText())
        self.nramps = nramps
        self.nrampsText = int(self.nramps.toPlainText())
        self.sourceName = sourceName
        self.sourceNameText = self.sourceName.toPlainText()
        
    def __del__(self):
        self.wait()
        
    def run(self):
        self.exposureTypeText = self.exposureType.currentText()
        self.nreadsText = int(self.nreads.toPlainText())
        self.nrampsText = int(self.nramps.toPlainText())
        self.sourceNameText = self.sourceName.toPlainText()
        if(self.exposureTypeText == "Single Frame"):
            output = self.detector.exposeSF()
            print(output)
            self.finished.emit("SF",output,"None")
        elif(self.exposureTypeText == "CDS"):
            output = self.detector.exposeCDS()
        elif(self.exposureTypeText == "Ramp"):
            output = self.detector.exposeRamp(self.nreadsText, self.nrampsText, "Ramp", \
                    self.sourceNameText)

class h2rgProgressThread(QThread):

    finished = pyqtSignal(str,str,str)

    def __init__(self,progressbar, exposureType, nreads=2,nramps=1):
        QThread.__init__(self)

        self.progressbar = progressbar
        self.nreads = nreads
        self.nreadsText = int(self.nreads.toPlainText())
        self.nramps = nramps
        self.nrampsText = int(self.nramps.toPlainText())
        self.exposureType = exposureType
        self.exposureTypeText = self.exposureType.currentText()
        
        self.progressbar.setMinimum(0)
        self.progressbar.setMaximum(100)
        self.progressbar.setValue(0)

    def __del__(self):
        self.wait()
        
    def run(self):
        self.exposureTypeText = self.exposureType.currentText()

        if self.exposureTypeText != 'Ramp':
            return
       
        self.sleep(4)
        self.nreadsText = int(self.nreads.toPlainText())
        self.nrampsText = int(self.nramps.toPlainText())
        t1 = time()
        n_seconds = self.nreadsText * self.nrampsText * 1.5
        while (time() - t1) < n_seconds:
            self.progressbar.setValue(int((time() - t1)/n_seconds * 100))
        self.progressbar.setValue(0)



