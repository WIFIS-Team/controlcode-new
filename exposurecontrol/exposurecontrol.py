from pylab import * 
import serial
from time import *
from Tkinter import *
import ttk
import sys
import signal
import os
import socket
import matplotlib.pyplot as plt
import numpy as np
import astropy.io.fits as fits
from astropy.visualization import (PercentileInterval, LinearStretch,
                                   ImageNormalize)
import wifisWaveSol as waveSol
import wifisSlices as slices
import wifisIO
import numpy as np
from scipy.interpolate import griddata
from scipy.interpolate import interp1d

class Formatter(object):
    def __init__(self, im):
        self.im = im
    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
        return 'x={:.01f}, y={:.01f}, z={:.01f}'.format(x, y, z)

# Channel Correct
def channelrefcorrect(data,channel=32):
    corrfactor = np.zeros(channel)
    
    for i in range(channel):
         csize = 64*32/channel
         corrfactor[i] = np.mean(np.concatenate([data[0:4,i*csize:i*csize+csize],data[2044:2048,i*csize:i*csize+csize]]))
         data[:,i*csize:i*csize+csize] = data[:,i*csize:i*csize+csize] - corrfactor[i]


def arcfwhm(inputfile,pwd):
    limits = wifisIO.readImgsFromFile('limits.fits')[0] #must point to location of limits
    wave = wifisIO.readImgsFromFile(pwd+inputfile)[0][4:2044,:] #trim, if limits file doesn't include reference pixels, which is likely the case
    
    print('extracting wave slices')
    waveSlices = slices.extSlices(wave, limits, dispAxis=0)

    tmpLst = []
    dispSol = []

    print('getting mean templates')
    for w in waveSlices:
        mid = int(w.shape[0]/2)
        y = np.nanmean(w[mid-4:mid+5,:],axis=0)
        tmpLst.append(y)

    atlas = 'external_data/best_lines2.dat'

    #dispersion solutions for template slices
    dispTemp = [[6.94432076e+03,  -6.64823436e+00,   1.76614405e-03,-5.34567472e-07],
            [6.92071493e+03,  -6.58643402e+00,   1.71915780e-03,-5.21821679e-07],
            [ 6.84753705e+03,  -6.38834210e+00,   1.53920478e-03,-4.66558945e-07],
            [6.81231873e+03,  -6.29558259e+00,   1.46437240e-03,-4.45861833e-07],
            [6.68429143e+03,  -5.95333715e+00,   1.15927424e-03,-3.55071242e-07],
            [6.67497223e+03,  -5.91997038e+00,   1.12949634e-03,-3.45789655e-07],
            [6.60583640e+03,  -5.73866976e+00,   9.65454922e-04,-2.96461930e-07],
            [6.60191806e+03,  -5.72682246e+00,   9.57496137e-04,-2.94615309e-07],
            [6.58640181e+03,  -5.68493758e+00,   9.15028716e-04,-2.80684206e-07],
            [6.58022938e+03,  -5.67318200e+00,   9.08690459e-04,-2.79809200e-07],
            [  6.58344796e+03,  -5.68753082e+00,   9.19169946e-04,-2.82559581e-07],
            [  6.61836504e+03,  -5.79039083e+00,   1.01497156e-03,-3.11983041e-07],
            [  6.91494545e+03,  -6.60140133e+00,   1.74015653e-03,-5.26725524e-07],
            [  6.68846942e+03,  -5.99041161e+00,   1.19365263e-03,-3.65636458e-07],
            [6.72641404e+03,  -6.10327307e+00,   1.29371104e-03,-3.95806105e-07],
            [  6.75219240e+03,  -6.18322495e+00,   1.36783471e-03,-4.19092686e-07],
            [6.81670485e+03,  -6.37178475e+00,   1.53544599e-03,-4.69603182e-07],
            [  6.79383500e+03,  -6.31775216e+00,   1.49144616e-03,-4.58893942e-07]]

    print('Getting dispersion solution')
    result = waveSol.getWaveSol(waveSlices, tmpLst, atlas,3, dispTemp, winRng=9, mxCcor=30, weights=False, buildSol=False, allowLower=True, sigmaClip=2., lngthConstraint = True)

    print('Extracting solution results')
    dispSolLst = result[0]
    fwhmLst = result[1]
    pixCentLst = result[2]
    waveCentLst = result[3]
    rmsLst = result[4]
    pixSolLst = result[5]

    print('Building maps of results')
    npts = waveSlices[0].shape[1]
    waveMapLst = waveSol.buildWaveMap(dispSolLst,npts)
    fwhmMapLst = waveSol.buildFWHMMap(pixCentLst, fwhmLst, npts)

    #determine length along dispersion direction
    ntot = 0
    for r in rmsLst:
        ntot += len(r)

    #build "detector" map images
    #wavelength solution
    waveMap = np.empty((npts,ntot),dtype='float32')
    strt=0
    for m in waveMapLst:
        waveMap[:,strt:strt+m.shape[0]] = m.T
        strt += m.shape[0]

    wifisIO.writeFits(waveMap, pwd+'wavelength_map.fits')

    #fwhm map
    fwhmMap = np.empty((npts,ntot),dtype='float32')
    strt=0
    for f in fwhmMapLst:
        fwhmMap[:,strt:strt+f.shape[0]] = f.T
        strt += f.shape[0]

    wifisIO.writeFits(fwhmMap, pwd+'fwhm_map.fits')

    fwhmmedian = np.nanmedian(fwhmMap)
    plt.figure()
    plt.imshow(fwhmMap, aspect='auto')
    plt.title("FWHM median %5f pixels" % fwhmmedian)
    plt.colorbar()
    plt.show()
    plt.savefig(pwd+'fwhm_map_interp.png', dpi=300)

def pointing(file):
    slices = [[34,135],[147,247],[255,357],[367,471],[481,585],[595,697],[707,809],[819,923],[935,1039],[1047,1149],[1163,1265],[1277,1377],[1387,1489], [1503,1607], [1613,1715], [1731,1832], [1843,1943], [1957,2048]]
    sliceorder = [8,9,7,10,6,11,5,12,4,13,3,14,2,15,1,16,0,17]
    #sliceorder = [9,8,10,7,11,6,12,5,13,4,14,3,15,2,16,1,17,0]

    hdu = fits.open(file)

    data = hdu[0].data

    summedrows = np.median(data[1600:1900,:],axis=0)

    #plt.plot(summedrows)

    wifisimg = np.zeros((36,100))

    for i in range(18):
        pixrange = slices[i]
        if((pixrange[1] - pixrange[0]) >= 100):
            wifisimg[sliceorder[i]*2,:] = (summedrows[pixrange[0]:pixrange[0]+100])/2.0
            wifisimg[sliceorder[i]*2+1,:] = (summedrows[pixrange[0]:pixrange[0]+100])/2.0
                                    
    plt.figure()
    plt.imshow(wifisimg,interpolation='none')
    plt.show()

plt.ion()

servername = "192.168.0.20"
serverport = 5000
path_to_watch = "/Data/WIFIS/H2RG-G17084-ASIC-08-319/"
buffersize = 1024

class MainApplication(Frame): 
    """Defines the GUI including the buttons as well as the button functions."""
    
    def __init__(self,master):#,switch1,switch2): #setup basic gui stuff
        Frame.__init__(self, master)
        self.grid()
 
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.currentStatus = "Disconnected"
	self.correctData = IntVar(value=0)
        self.histogram = IntVar(value=0)
        self.arcfwhm = IntVar(value=0)
        self.nreads = IntVar(value=1)
        self.nramps = IntVar(value=1)
        self.obstype = StringVar(self)
        self.sourcename = StringVar(self)
 
        self.create_widgets()

    def create_widgets(self): #create all the buttons and labels and stuff
        
        ######################################################################
        # Connecting and Initializing
        ######################################################

        Label(self, text="H2RG State", font='bold').grid(row=0, column=1, padx=15)
        Button(self, text="Connect", command=self.connect, width=7, bg="yellow").grid(row=0, column=2, padx=15)
        Button(self, text="Disconnect", command=self.disconnect, width=7, bg="red").grid(row=0, column=3, padx=15)
        Button(self, text="Initialize", command=self.initialize, width=7, bg="light green").grid(row=0, column=4, padx=15)
        Label(self, text="Status:", font='bold').grid(row=0, column=5, padx=15)
        
        self.status = Label(self, text=self.currentStatus, font='bold', bg ='red',width=10)
        self.status.grid(row=0, column=6, padx=15)

        Label(self, text="Observation Type:", font='bold').grid(row=1, column=1, columnspan=2, padx=15)
        choices = { 'Science','Sky','Flat','Arc','Ronchi','Other'}
        self.obstype.set('Science')

        self.obstypemenu = OptionMenu(self,self.obstype,*choices)
        self.obstypemenu.grid(row=1,column=3,columnspan=1,padx=15)
        Label(self, text="Source:").grid(row=1, column=4, padx=15)
        self.esource=Entry(self,textvariable=self.sourcename)
        self.esource.grid(row=1, column=5, padx=15)

        Label(self, text="Expose:", font='bold').grid(row=2, column=1, columnspan=2, padx=15)
        self.b1=Button(self, text="Single Frame", command=self.exposeSF)
        self.b1.grid(row=2, column=3, padx=15)
        self.b2=Button(self, text="CDS", command=self.exposeCDS)
        self.b2.grid(row=2, column=4, padx=15)
        self.b3=Button(self, text="Ramp", command=self.exposeRamp)
        self.b3.grid(row=2, column=5, padx=15)

        Label(self, text="Ramp Parameters:", font='bold').grid(row=3, column=1, columnspan=2, padx=15)
        Label(self, text="Ramps").grid(row=3, column=4, padx=15)
        Label(self, text="Reads").grid(row=3, column=6, padx=15)
        self.e1=Entry(self,textvariable=self.nramps)
        self.e1.grid(row=3, column=3, padx=15)
        self.e2=Entry(self,textvariable=self.nreads)
        self.e2.grid(row=3, column=5, padx=15)

        Label(self, text="Options:", font='bold').grid(row=4, column=1, columnspan=2, padx=15)
        self.c1 = Checkbutton(self,text="Channel Correct",variable=self.correctData)
        self.c1.grid(row=4, column=3, columnspan=1,padx=15)
        self.c2 = Checkbutton(self,text="Histogram",variable=self.histogram)
        self.c2.grid(row=4, column=4, columnspan=1,padx=15)
        self.c3 = Checkbutton(self,text="Arc FWHM",variable=self.arcfwhm)
        self.c3.grid(row=4, column=5, columnspan=1,padx=15)

        self.l1=Label(self, text="",width=50,font=(None,8))
        self.l1.grid(row=5, column=1, columnspan=6,padx=15)

        self.b4 = Button(self, text="Arc Ramp", command=self.arcramp).grid(row=1, column=6)
        self.b5 = Button(self, text="Flat Ramp", command=self.flatramp).grid(row=2, column=6)
        

    def connect(self):
        self.s.connect((servername,serverport))
        self.currentStatus = "Connected"
        self.status["text"] = self.currentStatus
        self.status["bg"] = "yellow"
    
    def disconnect(self):
        self.s.close()
        self.currentStatus = "Disconnected"
        self.status["text"] = self.currentStatus
        self.status["bg"] = "red"
 
    def initialize(self):
        self.s.send("INITIALIZE1")
        print("Initializing")
        response = self.s.recv(buffersize)
        print(response)
        self.status["text"] = "Initialized"
        self.status["bg"] = "light green"

        self.s.send("SETGAIN(12)")
        print("Setting Gain")
        response = self.s.recv(buffersize)
        print(response)

        self.s.send("SETDETECTOR(2,32)")
        print("Setting Detector Channels")
        response = self.s.recv(buffersize)
        print(response)

        self.s.send("SETENHANCEDCLK(1)")
        print("Setting Clocking")
        response = self.s.recv(buffersize)
        print(response)
        self.l1["text"] = response

        self.currentStatus = "ready"
        self.status["text"] = "READY"
        self.status["bg"] = "green"
    
    def writeObsdata(self,directory):
        f = open(directory+"/obsinfo.dat","w")
        f.write("Obs Type: "+self.obstype.get()+"\n")
        f.write("Source: "+self.sourcename.get()+"\n")

        telemf = open("/home/utopea/WIFIS-Team/controlcode/BokTelemetry.txt","r")

        for line in telemf:
            f.write(line)

        telemf.close()
        f.close()
    	
    def exposeSF(self):
        watchpath = path_to_watch+"/Reference"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        print("Acquiring Single Frame")
        
        self.s.send("ACQUIRESINGLEFRAME")
        response = self.s.recv(buffersize)
        print(response)
        self.l1["text"] = response

        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]
        self.status["text"] = "READY"
        self.status["bg"] = "green"

        print("Added File: "+added[0])

        hdu = fits.open(watchpath+"/"+added[0])
        image = hdu[0].data
        if(self.correctData):
            channelrefcorrect(image)

        norm = ImageNormalize(image, interval=PercentileInterval(99.5),
                      stretch=LinearStretch())

        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
        ax.format_coord = Formatter(im)
        ax.set_title(added[0])
        fig.colorbar(im)
        
    def exposeCDS(self):
        watchpath = path_to_watch+"/CDSReference"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        print("Acquiring CDS Frame")
        
        self.s.send("ACQUIRECDS")
        response = self.s.recv(buffersize)
        print(response)
 
        self.l1["text"] = response
       
        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]
        self.status["text"] = "READY"
        self.status["bg"] = "green"

        print("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+self.sourcename.get())

        self.writeObsdata(watchpath+'/'+added[0])

        hdu = fits.open(watchpath+"/"+added[0]+"/Result/CDSResult.fits")
        image = hdu[0].data*1.0
        if(self.correctData.get()):
            channelrefcorrect(image)

        norm = ImageNormalize(image, interval=PercentileInterval(99.5),
                      stretch=LinearStretch())

        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
        ax.format_coord = Formatter(im)
        ax.set_title(added[0])
        fig.colorbar(im)

        if(self.histogram.get()):
            fig = plt.figure()
            subimage = image[900:1100,900:1100].flatten()
            mean = np.mean(subimage)
            std = np.std(subimage)
            plt.hist(subimage,bins=200)
            plt.xlim([mean-3*std,mean+3*std])
            plt.title("Mean = %f5, Std = %f5" % (mean, std))
            plt.show()

        if(self.arcfwhm.get()):
            pointing(watchpath+"/"+added[0]+'/Result/CDSResult.fits')

        hdu.close()
    def exposeRamp(self):
        commandstring = "SETRAMPPARAM(1,%d,1,1.5,%d)" % (self.nreads.get(),self.nramps.get())
        self.s.send(commandstring)
        response = self.s.recv(buffersize)
        print(response)

        watchpath = path_to_watch+"/UpTheRamp"
        before = dict ([(f, None) for f in os.listdir (watchpath)])
        print("Acquiring Ramp")

        self.s.send("ACQUIRERAMP")
        response = self.s.recv(buffersize)
        print(response)
 
        self.l1["text"] = response
       
        after = dict ([(f, None) for f in os.listdir (watchpath)])
        added = [f for f in after if not f in before]
        self.status["text"] = "READY"
        self.status["bg"] = "green"

        print("Added Directory: "+added[0][:8]+" "+added[0][8:]+', '+self.sourcename.get())

        self.writeObsdata(watchpath+'/'+added[0])

        totreads = self.nreads.get()

        if(totreads < 2):
            hdu = fits.open(watchpath+"/"+added[0]+"/H2RG_R01_M01_N01.fits")
            image = hdu[0].data*1.0
            hdu.close()
        else:
            f1 = 'H2RG_R01_M01_N01.fits'
            f2 = "H2RG_R01_M01_N%02d.fits" % totreads
        
            hdu1 = fits.open(watchpath+"/"+added[0]+"/"+f1)
            hdu2 = fits.open(watchpath+"/"+added[0]+"/"+f2)
            image = hdu2[0].data*1.0 - hdu1[0].data*1.0
            hdu1.close()
            hdu2.close()

        if(self.correctData.get()):
            channelrefcorrect(image)

        norm = ImageNormalize(image, interval=PercentileInterval(99.5),
                      stretch=LinearStretch())

        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
        ax.format_coord = Formatter(im)
        ax.set_title(added[0])
        fig.colorbar(im)

        if(self.histogram.get()):
            fig = plt.figure()
            subimage = image[900:1100,900:1100].flatten()
            mean = np.mean(subimage)
            std = np.std(subimage)
            plt.hist(subimage,bins=100,range=(mean-3*std,mean+3*std))
            plt.xlim([mean-3*std,mean+3*std])
            plt.title("Mean = %f5, Std = %f5" % (mean, std))
            plt.show()

    def flatramp(self):
        self.nreads.set(5)
        sourcetemp = self.sourcename.get()
        self.sourcename.set('CalFlat '+self.sourcename.get()) 
        self.exposeRamp()
        self.sourcename.set(sourcetemp)

    def arcramp(self):
        self.nreads.set(3)
        sourcetemp = self.sourcename.get()
        self.sourcename.set('CalArc '+self.sourcename.get()) 
        self.exposeRamp()
        self.sourcename.set(sourcetemp)

def run_exposure_gui_standalone():
    """Standalone version of this script for use in case launch_controls fails
    or for testing"""

    print 'Activating GUI'
    root = Tk() #gui set up stuff
    root.title("H2RG Exposure Control") #gui name

    app = MainApplication(root) #set up gui class

    root.mainloop() #run gui loop
    
if __name__ == '__main__':
    run_exposure_gui_standalone()     
    
