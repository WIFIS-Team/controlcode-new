import numpy as np
import astropy.io.fits as fits
import socket
import os
import sys
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
import matplotlib.pyplot as plt
from astropy.visualization import (PercentileInterval, LinearStretch,
                                   ImageNormalize)

# Define global variables here
servername = "192.168.0.20"
serverport = 5000
path_to_watch = "/Data/WIFIS/H2RG-G17084-ASIC-08-319/"
buffersize = 1024

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
            f.write("Obs Type: "+self.obsType+"\n")
            f.write("Source: "+self.sourceName.g+"\n")

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
        self.writeObs(self,finalPath,obsType,sourceName)
        
        return(finalPath)
    
    @pyqtSlot(str,str,str)    
    def plotImage(obsType,fileName1,fileName2):
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

class h2rgExposeThread(QThread):

    plotImage = pyqtSignal(str,str,str)

    def __init__(self,detector,exposureType,nreads=2,nramps=1,obsType="None",sourceName="None"):
        QThread.__init__(self)
        self.detector = detector
        self.exposureType = exposureType
        self.nreads = nreads
        self.nramps = nramps
        self.obsType = obsType
        self.sourceName = sourceName
        
    def __del__(self):
        self.wait()
        
    def run(self):
        if(self.exposureType == "SF"):
            output = detector.exposeSF()
            self.plotImage.emit("SF",output,"None")
        elif(self.exposureType == "CDS"):
            output = detector.exposeCDS()
        elif(self.exposureType == "Ramp"):
            output = detector.exposeRamp()
            
            
        
            
            
            
                
                
