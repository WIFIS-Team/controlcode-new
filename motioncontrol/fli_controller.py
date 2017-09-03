# -*- coding: utf-8 -*-
#
#----------------------------------------------------------
# Name:     fli_controller.py
# Purpose:  Provide control interface for the FLI devices
# Author:   Elliot Meyer
# Email:    meyer@astro.utoronto.ca
# Date:     November 2015
#----------------------------------------------------------
#
#

import numpy as np
from astropy.io import fits
import matplotlib.pyplot as mpl
import Tkinter as _tk
import WIFISastrometry as WA
from sys import exit
import wifis_guiding as WG
import os, time, threading, Queue
from glob import glob
from astropy.visualization import (PercentileInterval,\
                                LinearStretch, ImageNormalize)
try:
    import FLI
except (ImportError, RuntimeError):
    print "FLI cannot be imported"

class Formatter(object):
    def __init__(self, im):
        self.im = im
    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
        return 'x={:.01f}, y={:.01f}, z={:.01f}'.format(x, y, z)

###########################################################
def load_FLIDevices():
    '''Loads the FLI devices into variables and sets the 
    default parameters'''
    
    camSN = 'ML0240613'
    focSN = 'PDF0184509'
    fltSN = 'CFW-1-5-001'

    ## Load the FLI devices into variables ##

    cam = FLI.USBCamera.locate_device(camSN)
    foc = FLI.USBFocuser.locate_device(focSN)
    flt = FLI.USBFilterWheel.locate_device(fltSN)
    
    ## Set default parameters for the FLI devices and ensure 
    if flt != None:
        flt.set_filter_pos(0)
        pass
    if foc != None:
        #foc.home_focuser()
        pass
    if cam:
    #    cam.end_exposure()
        cam.set_temperature(-20)
    # ??? any other default params ???
   
    return [cam, foc, flt]

def measure_focus(img, sideregions = 3, fitwidth = 10, plot=False, verbose=False):

    imgshape = img.shape

    regionx = imgshape[0]/sideregions
    regiony = imgshape[1]/sideregions

    starsx = np.array([])
    starsy = np.array([])
    brightestx = 0
    brightesty = 0
    bright = 0
    for i in range(sideregions):
        for j in range(sideregions):
            imgregion = img[regionx*i:regionx*(i+1),regiony*j:regiony*(j+1)]
            centroids = WA.centroid_finder(imgregion, plot=False)
            imgregionshape = imgregion.shape
            brightstar = WA.bright_star(centroids, imgregionshape)
            if brightstar != None:
                if verbose:
                    print "BRIGHTSTAR: %f %f %f" % (centroids[0][brightstar], \
                        centroids[1][brightstar], centroids[2][brightstar])
                cx = centroids[0][brightstar]
                cy = centroids[1][brightstar]
                if centroids[2] > bright:
                    bright = centroids[2]
                    brightestx = cx+regionx*i
                    brightesty = cy+regiony*j
                star_x = imgregion[cx-fitwidth:cx+fitwidth+1, cy]
                star_y = imgregion[cx, cy-fitwidth:cy+fitwidth+1]
                xs = np.arange(len(star_x)) 

                if plot: 
                    mpl.imshow(imgregion, origin='lower')
                    mpl.plot(cy,cx, 'rx')
                    mpl.show()

                popt, pcov = WA.gaussian_fit(xs, star_x, [30000., 3.0, 10.0])
                starsx = np.append(starsx,popt[1])
                popt, pcov = WA.gaussian_fit(xs, star_y, [30000., 3.0, 10.0])
                starsy = np.append(starsy,popt[1])
    
    xavg = np.mean(starsx)
    yavg = np.mean(starsy)

    return [np.mean([xavg, yavg]), brightestx, brightesty]

################################################################################
class FLIApplication(_tk.Frame): 
    '''Creates the FLI GUI window and also contains a number of 
    functions for controlling the Filter Wheel, Focuser, and
    Camera.'''

    def __init__(self,parent):
        '''Initialize the GUI and load the Devices into memory'''

        _tk.Frame.__init__(self,parent)
        self.parent = parent
        self.deltRA = 0
        self.deltDEC = 0

        #Try to import FLI devices
        try:
            self.cam, self.foc, self.flt = load_FLIDevices()
        except (ImportError, RuntimeError, NameError):
            self.cam, self.foc, self.flt = [None,None,None]

        try: self.telSock = WG.connect_to_telescope()
        except:
            self.telSock = None

        self.todaydate = time.strftime("%Y%m%d")
        self.direc = u'/Data/WIFISGuider/'+self.todaydate+'/'
        if not os.path.exists(self.direc):
            os.makedirs(self.direc)

        self.guideButtonVar = _tk.StringVar()
        self.guideButtonVar.set('Start Guiding')

        self.skyMoveVar = _tk.StringVar()
        self.skyMoveVar.set('Move to Sky')

        self.initialize()

        # Call the functions to continuously update the reporting fields    
        # An error will most likely appear after you close the window as
        # the mainloop will still attempt to run these commands.
        self.writeFilterNum()
        self.getCCDTemp()
        self.writeStepNum()

    def initialize(self):
        '''Creates the actual GUI elements as well as run the various
        tasks'''

        self.grid()

        ##### Filter Wheel Settings #####
         
        # Check if FW is connected & colour label appropriately
        if self.flt == None:
            fltbg = 'red3'
        else:
            fltbg = 'green3'
         
        label = _tk.Label(self, text='Filter Settings', relief='ridge',\
            anchor="center", fg = "black", bg=fltbg,font=("Helvetica", 20))
        label.grid(column=0,row=0,columnspan=2, sticky='EW')
    
        # Filter position report label
        label = _tk.Label(self, text='Filter Position', \
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=0,row=1, sticky='EW')

        self.filterNumText = _tk.StringVar()        
        self.filterNumText.set(self.getFilterType())
        label = _tk.Label(self, textvariable=self.filterNumText, \
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=0,row=2, sticky='EW')
        
        # Change filter buttons
        _tk.Button(self, text=u"Z",\
            command=self.gotoFilter1).grid(column = 1,row = 1, sticky='EW')
        _tk.Button(self, text=u"I",\
            command=self.gotoFilter2).grid(column = 1,row = 2, sticky='EW')
        _tk.Button(self, text=u"R",\
            command=self.gotoFilter3).grid(column = 1,row = 3, sticky='EW')
        _tk.Button(self, text=u"G",\
            command=self.gotoFilter4).grid(column = 1,row = 4, sticky='EW')
        _tk.Button(self, text=u"H-Alpha",\
            command=self.gotoFilter5).grid(column = 1,row = 5, sticky='EW')

        ##### Focuser Settings #####

        #Check to see if Focuser is connected & colour label appropriately
        if self.foc == None:
            focbg = 'red3'
        else:
            focbg = 'green3'

        label = _tk.Label(self, text='Focuser Settings', relief='ridge',\
            anchor="center", fg = "black", bg=focbg,font=("Helvetica", 20))
        label.grid(column=2,row=0,columnspan=2, sticky='EW')

        # Focuser step value setting entry field
        label = _tk.Label(self, text='Step Value', \
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=2,row=1, sticky='EW')

        self.entryfocVariable = _tk.StringVar()
        self.entryfoc = _tk.Entry(self, width = 10,\
            textvariable=self.entryfocVariable)
        self.entryfoc.grid(column=2, row=2, sticky='EW')
        self.entryfocVariable.set(u"100")

        # Focuser step position report label
        label = _tk.Label(self, text='Step Position', \
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=2,row=3, sticky='EW')

        self.stepNumText = _tk.StringVar()        
        label = _tk.Label(self, textvariable=self.stepNumText, \
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=2,row=4, sticky='EW')
        self.writeStepNum()

        # Buttons for focuser
        _tk.Button(self, text=u"Home Focuser",\
            command=self.homeFocuser).grid(column = 3, row = 1, sticky='EW')
        _tk.Button(self, text=u"Step Forward",\
            command=self.stepForward).grid(column = 3, row = 2, sticky='EW')
        _tk.Button(self, text=u"Step Backward",\
            command=self.stepBackward).grid(column = 3, row = 3, sticky='EW')

        ##### Camera Settings #####

        # Check to see if Camera is connected & colour label appropriately
        if self.cam == None:
            cambg = 'red3'
        else:
            cambg = 'green3'

        label = _tk.Label(self, text='Camera Settings', relief='ridge',\
            anchor="center", fg = "black", bg=cambg,font=("Helvetica", 20))
        label.grid(column=1,row=6,columnspan=2, sticky='EW')

        self.imgtypeVariable = _tk.StringVar()
        self.imgtypeVariable.set("Normal")
        imgtypeOption = _tk.OptionMenu(self, self.imgtypeVariable, "Normal", "Dark")
        imgtypeOption.grid(column=2, row=7, sticky='EW')

        # Exposure time set entry field
        label = _tk.Label(self, text='Exposure Time', relief='ridge',\
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=1,row=7, sticky='EW')

        self.entryExpVariable = _tk.StringVar()
        self.entryExp = _tk.Entry(self, width=10,\
            textvariable=self.entryExpVariable)
        self.entryExp.grid(column=1, row=8, sticky='EW')
        self.entryExpVariable.set(u"3000")

        # CCD temperature set entry field
        label = _tk.Label(self, text='Set Temperature',  relief='ridge',\
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=1,row=9, sticky='EW')

        self.entryCamTempVariable = _tk.StringVar()
        self.entryCamTemp = _tk.Entry(self, width=10,\
            textvariable=self.entryCamTempVariable)
        self.entryCamTemp.grid(column=1, row=10, sticky='EW')
        self.entryCamTempVariable.set(u"-20")

        # CCD Temp reporting label
        label = _tk.Label(self, text='CCD Temperature',  relief='ridge',\
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=0,row=9, sticky='EW')

        self.ccdTempText = _tk.StringVar()        
        label = _tk.Label(self, textvariable=self.ccdTempText, relief='ridge',\
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=0,row=10, sticky='EW')

        # Image filepath set entry field
        label = _tk.Label(self, text='Force Filename',  relief='ridge',\
            anchor="center", fg = "black", bg="white",font=("Helvetica", 12))
        label.grid(column=0,row=7, sticky='EW')

        self.entryFilepathVariable = _tk.StringVar()
        self.entryFilepath = _tk.Entry(self, width=30, \
            textvariable=self.entryFilepathVariable)
        self.entryFilepath.grid(column=0, row=8, sticky='EW')
        self.entryFilepathVariable.set("")

        # Camera buttons
        _tk.Button(self, text=u"Save Image",\
            command=self.saveImage).grid(column = 2, row = 8, sticky='EW')
        _tk.Button(self, text=u"Set Temperature",\
            command=self.setTemperature).grid(column = 2, row = 10,\
            sticky='EW')
        _tk.Button(self, text=u"Take Image",\
            command=self.takeImage).grid(column = 3, row = 7, sticky='EW')
        _tk.Button(self, text=u"Focus Camera",\
            command=self.focusCamera).grid(column = 3, row = 8, sticky='EW')
        _tk.Button(self, text=u"Centroids",\
            command=self.checkCentroids).grid(column=3, row=9, sticky='EW')


        self.grid_columnconfigure(0,weight=1)
        self.grid_columnconfigure(1,weight=1)
        self.grid_columnconfigure(2,weight=1)
        self.grid_columnconfigure(3,weight=1)
        #self.resizable(True, False)

        ##### Telescope Settings #####
        # Check to see if Camera is connected & colour label appropriately
        if self.telSock == None:
            telbg = 'red3'
        else:
            telbg = 'green3'

        label = _tk.Label(self, text='Telescope', relief='ridge',\
            anchor="center", fg = "black", bg=cambg,font=("Helvetica", 20))
        label.grid(column=4,row=0,columnspan=3, sticky='EW')
        
        #self.raGuideVariable = _tk.StringVar()
        #self.raGuideBox = _tk.Entry(self, \
        #    textvariable=self.raGuideVariable)
        #self.raGuideBox.grid(column=6, row=4, sticky='EW')
        #self.raGuideVariable.set("")

        #self.decGuideVariable = _tk.StringVar()
        #self.decGuideBox = _tk.Entry(self, \
        #    textvariable=self.decGuideVariable)
        #self.decGuideBox.grid(column=6, row=5, sticky='EW')
        #self.decGuideVariable.set("")

        _tk.Button(self, text=u'Move Telescope',\
            command=self.moveTelescope).grid(column=4, row=1, sticky='EW')

        _tk.Button(self, text=u'Print Telemetry',\
            command=self.printTelemetry).grid(column=4, row=4, sticky='EW')    

        self.guideButton = _tk.Button(self, textvariable=self.guideButtonVar,\
            command=self.initGuiding).grid(column=5, row=3, sticky='EW')

        self.skyMoveButton = _tk.Button(self, text=u'Sky Move',\
                command=self.skyMove).grid(column=6, row=3, sticky='EW')

        self.guidingOnVariable = _tk.IntVar()
        self.guidingOnVariable.set(0)

        label = _tk.Label(self, text='RA Adj (\"):',\
            anchor="center", fg = "black", font=("Helvetica", 12))
        label.grid(column=5,row=1, sticky='EW')
        
        label = _tk.Label(self, text='DEC Adj (\"):',\
            anchor="center", fg = "black",font=("Helvetica", 12))
        label.grid(column=5,row=2, sticky='EW')

        label = _tk.Label(self, text='Guide Target:',\
            anchor="center", fg = "black",font=("Helvetica", 12))
        label.grid(column=5,row=4, sticky='EW')
        self.guideTargetVariable = _tk.StringVar()
        self.guideTarget = _tk.Entry(self, width=15, \
            textvariable=self.guideTargetVariable)
        self.guideTarget.grid(column=6, row=4, sticky='EW')
        self.guideTargetVariable.set("")

        label = _tk.Label(self, text='Guide Exp:',\
            anchor="center", fg = "black",font=("Helvetica", 12))
        label.grid(column=5,row=5, sticky='EW')
        self.guideExpVariable = _tk.StringVar()
        self.guideExp = _tk.Entry(self, width=15, \
            textvariable=self.guideExpVariable)
        self.guideExp.grid(column=6, row=5, sticky='EW')
        self.guideExpVariable.set("1500")

        self.raAdjVariable = _tk.StringVar()
        self.raAdj = _tk.Entry(self, width=15, \
            textvariable=self.raAdjVariable)
        self.raAdj.grid(column=6, row=1, sticky='EW')
        self.raAdjVariable.set("0.00")
    
        self.decAdjVariable = _tk.StringVar()
        self.decAdj = _tk.Entry(self, width=15, \
            textvariable=self.decAdjVariable)
        self.decAdj.grid(column=6, row=2, sticky='EW')
        self.decAdjVariable.set("0.00")

        self.offsetButton = _tk.Button(self, text=u'Move to Guider',\
            command=self.offsetToGuider)
        self.offsetButton.grid(column=4, row=2, sticky='EW')

        self.offsetButton = _tk.Button(self, text=u'Move to WIFIS',\
            command=self.offsetToWIFIS)
        self.offsetButton.grid(column=4, row=3, sticky='EW')

        self.offsetAutoButton = _tk.Button(self, text=u'Corr Offset',\
            command=self.brightStarCorrect).grid(column=4, row=5, sticky='EW')

        label = _tk.Label(self, text='X Offset:',\
            anchor="center", fg = "black",font=("Helvetica", 12)).grid(column=5,row=6, sticky='EW')
        self.xOffsetVar = _tk.StringVar()
        self.xOffsetVar.set("0")
        self.xOffset = _tk.Entry(self, width=15, \
            textvariable=self.xOffsetVar).grid(column=6, row=6, sticky='EW')

        label = _tk.Label(self, text='Y Offset:',\
            anchor="center", fg = "black",font=("Helvetica", 12)).grid(column=5,row=7, sticky='EW')
        self.yOffsetVar = _tk.StringVar()
        self.yOffsetVar.set("0")
        self.yOffset = _tk.Entry(self, width=15, \
            textvariable=self.yOffsetVar).grid(column=6, row=7, sticky='EW')

        self.calcmov = _tk.Button(self, text=u'Calc Offset',\
            command=self.calcOffset).grid(column=4, row=6, sticky='EW')

        
    ## Functions to perform the above actions ##

    ## Telescope Functions

    def calcOffset(self):
        #Get rotation solution
        offsets,x_rot,y_rot = WG.get_rotation_solution(self.telSock)
        yc = float(self.xOffsetVar.get())
        xc = float(self.yOffsetVar.get())

        offsetx = xc - 512
        offsety = yc - 512
        dx = offsetx*x_rot
        dy = offsety*y_rot
        radec = dx + dy

        print "### MOVE ###\nRA:\t%f\nDEC:\t%f\n" % (-1*radec[1], -1*radec[0])

        return

    def printTelemetry(self):
        if self.telSock:
            telemDict = WG.get_telemetry(self.telSock)
            WG.clean_telem(telemDict)
            #WG.write_telemetry(telemDict)

    def moveTelescope(self):
        if self.telSock:
            if self.guidingOnVariable.get():
                self.guidingOnVariable.set(0)
                time.sleep(4)
            WG.move_telescope(self.telSock,float(self.raAdjVariable.get()), \
                float(self.decAdjVariable.get()))

    #def initGuiding(self):
    #    if self.telSock:
    #        if not self.guidingOnVariable.get():
    #            print "Guiding not enabled. Please check the box."
    #        elif not self.guideTargetVariable.get():
    #            print "Please enter a target for guiding"
    #        else:
    #            gfls = self.checkGuideVariable()
    #            guidingstuff = WG.wifis_simple_guiding_setup(self.telSock, self.cam, \
    #                int(self.guideExpVariable.get()),gfls)
    #            self.startGuiding(guidingstuff)
    
    def initGuiding(self):
        if self.telSock:
            self.deltRA = 0
            self.deltDEC = 0
            if self.guidingOnVariable.get():
                self.guidingOnVariable.set(0)
                return
            elif not self.guidingOnVariable.get():
                self.guidingOnVariable.set(1)
                print "###### STARTING GUIDING ######"
                self.guideButtonVar.set("Stop Guiding")
                gfls = self.checkGuideVariable()
                guidingstuff = WG.wifis_simple_guiding_setup(self.telSock, self.cam, \
                    int(self.guideExpVariable.get()),gfls)
                self.startGuiding(guidingstuff)
                #print "Guiding not enabled. Please check the box."

    def startGuiding(self, guidingstuff):
        if self.telSock:
            if not self.guidingOnVariable.get():
                self.cam.end_exposure()
                self.guideButtonVar.set("Start Guiding")
                print "###### FINISHED GUIDING ######"
                return
            else:
                try:
                    dRA, dDEC = WG.run_guiding(guidingstuff, \
                        self.parent, self.cam, self.telSock)
                    self.deltRA += dRA
                    self.deltDEC += dDEC
                    print "DELTRA:\t\t%f\nDELTDEC:\t%f\n" % (self.deltRA, self.deltDEC)
                except Exception as e:
                    print e
                    print "SOMETHING WENT WRONG... CONTINUING"
                    pass
                self.parent.after(3000, lambda: self.startGuiding(guidingstuff))

    def skyMove(self):
        if self.telSock:
            if self.guidingOnVariable.get():
                self.guidingOnVariable.set(0)
                self.after(4000, self.moveTelescope)
                self.after(4000, self.initGuiding)
            else:
                return

    def checkGuideVariable(self):
        gfl = '/home/utopea/elliot/guidefiles/'+time.strftime('%Y%m%d')+'_'+self.guideTargetVariable.get()+'.txt'
        guidefls = glob('/home/utopea/elliot/guidefiles/*.txt')
        if self.guideTargetVariable.get() == '':
            return '', False
        if gfl not in guidefls:
            print "OBJECT NOT OBSERVED, INITIALIZING GUIDE STAR"
            return gfl, False
        else:
            print "OBJECT ALREADY OBSERVED, USING ORIGINAL GUIDE STAR"
            return gfl, True
                
    def offsetToGuider(self):
        if self.telSock:
            offsets, x_rot, y_rot = WG.get_rotation_solution(self.telSock)
            WG.move_telescope(self.telSock, offsets[0], offsets[1]) 
            #self.offsetButton.configure(text='Move to WIFIS',\
            #    command=self.offsetToWIFIS)
            time.sleep(3)

    def offsetToWIFIS(self):
        if self.telSock:
            offsets, x_rot, y_rot = WG.get_rotation_solution(self.telSock)
            WG.move_telescope(self.telSock, -1.0*offsets[0], -1.0*offsets[1])
            #self.offsetButton.configure(text='Move to Guider',\
            #    command=self.offsetToGuider)
            time.sleep(3)

    def brightStarCorrect(self):
        if self.telSock:
            offsets, x_rot, y_rot = WG.get_rotation_solution(self.telSock)
            WG.move_telescope(self.telSock, offsets[0], offsets[1])
            time.sleep(5)
            img, dra, ddec = self.checkCentroids(auto=True)
            time.sleep(3)
            WG.move_telescope(self.telSock, dra, ddec)
            time.sleep(3)
            WG.move_telescope(self.telSock, -1.0*offsets[0], -1.0*offsets[1])
            time.sleep(5)

    ## Filter Wheel Functions
    def gotoFilter1(self):
        if self.flt:
            self.flt.set_filter_pos(0)

    def gotoFilter2(self):
        if self.flt:
            self.flt.set_filter_pos(1)

    def gotoFilter3(self):
        if self.flt:
            self.flt.set_filter_pos(2)

    def gotoFilter4(self):
        if self.flt:
            self.flt.set_filter_pos(3)

    def gotoFilter5(self):
        if self.flt:
            self.flt.set_filter_pos(4)

    def getFilterType(self):
        if self.flt:
            filterpos = (self.flt.get_filter_pos() + 1)
            if filterpos == 1:
                flttype = 'Z'
            if filterpos == 2:
                flttype = 'I'
            if filterpos == 3:
                flttype = 'R'
            if filterpos == 4:
                flttype = 'G'
            if filterpos == 5:
                flttype = 'H-Alpha'

            return flttype

    def writeFilterNum(self):
        if self.flt:
            filterpos = (self.flt.get_filter_pos() + 1)
            if filterpos == 1:
                self.filterNumText.set("Z")
            if filterpos == 2:
                self.filterNumText.set("I")
            if filterpos == 3:
                self.filterNumText.set("R")
            if filterpos == 4:
                self.filterNumText.set("G")
            if filterpos == 5:
                self.filterNumText.set("H-Alpha")
            self.after(500,self.writeFilterNum)

    ## Focuser Functions
    def homeFocuser(self):
        if self.foc:
            self.foc.home_focuser()

    def stepForward(self):
        if self.foc:
            self.foc.step_motor(int(self.entryfocVariable.get()))

    def stepBackward(self):
        if self.foc:
            self.foc.step_motor(-1*int(self.entryfocVariable.get()))    

    def writeStepNum(self):
        if self.foc:
            self.stepNumText.set(str(self.foc.get_stepper_position()))
            self.after(2000, self.writeStepNum)

    ## Camera Functions
    def saveImage(self):
        if self.cam:
            if self.imgtypeVariable.get() == 'Dark':
                self.cam.end_exposure()
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='normal')
                img = self.cam.take_photo()  

            telemDict = WG.get_telemetry(self.telSock)
            hduhdr = self.makeHeader(telemDict)
            #hdu = fits.PrimaryHDU(header=hduhdr)
            #hdulist = fits.HDUList([hdu])
            if self.entryFilepathVariable.get() == "":
                print "Writing to: "+self.direc+self.todaydate+'T'+time.strftime('%H%M%S')+'.fits'
                fits.writeto(self.direc+self.todaydate+'T'+time.strftime('%H%M%S')+'.fits', img, hduhdr,clobber=True)
                #hdulist.writeto(self.direc+self.todaydate+'T'+time.strftime('%H%M%S')+'.fits', clobber=True)
            else:
                print "Writing to: "+self.direc+self.todaydate+'T'+time.strftime('%H%M%S')+'_'+self.entryFilepathVariable.get()+".fits"
                fits.writeto(self.direc+self.todaydate+'T'+time.strftime('%H%M%S')+'_'+self.entryFilepathVariable.get()+".fits", img, hduhdr,clobber=True)
                #hdulist.writeto(self.entryFilepathVariable.get(),clobber=True)
                #self.entryFilepathVariable.set("")

            mpl.close()
            fig = mpl.figure()
            ax = fig.add_subplot(1,1,1)

            norm = ImageNormalize(img, interval=PercentileInterval(99.5), stretch=LinearStretch())
            #norm = ImageNormalize(img,  stretch=LinearStretch())
            
            im = ax.imshow(img, interpolation='none', norm= norm, cmap='gray', origin='lower')
            ax.format_coord = Formatter(im)
            fig.colorbar(im)
            mpl.show()

    def makeHeader(self, telemDict):

        hdr = fits.Header()
        hdr['DATE'] = self.todaydate 
        hdr['SCOPE'] = 'Bok Telescope, Steward Observatory'
        hdr['ObsTime'] = time.strftime('%H:%M"%S')
        hdr['ExpTime'] = self.entryExpVariable.get()
        hdr['RA'] = telemDict['RA']
        hdr['DEC'] = telemDict['DEC']
        hdr['IIS'] = telemDict['IIS']
        hdr['EL'] = telemDict['EL']
        hdr['AZ'] = telemDict['AZ']
        hdr['Filter'] = self.getFilterType()
        hdr['FocPos'] = self.foc.get_stepper_position()
        hdr['AM'] = telemDict['SECZ']

        return hdr

    def setTemperature(self):
        if self.cam:
            self.cam.set_temperature(int(self.entryCamTempVariable.get()))    

    def getCCDTemp(self):
        if self.cam:
            self.ccdTempText.set(str(self.cam.get_temperature()))
            self.after(1000,self.getCCDTemp)        
    
    def takeImage(self):
        if self.cam and self.foc:
            if self.imgtypeVariable.get() == 'Dark':
                self.cam.end_exposure()
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='normal')
                img = self.cam.take_photo()  
   
            mpl.close()
            fig = mpl.figure()
            ax = fig.add_subplot(1,1,1)
            
            norm = ImageNormalize(img, interval=PercentileInterval(99.5), stretch=LinearStretch())

            im = ax.imshow(img, interpolation='none', norm= norm, cmap='gray', origin='lower')
            ax.format_coord = Formatter(im)
            fig.colorbar(im)
            mpl.show()
        return img

    def checkCentroids(self, auto=False):
        if self.cam and self.foc:
            if self.imgtypeVariable.get() == 'Dark':
                self.cam.end_exposure()
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(int(self.entryExpVariable.get()), frametype='normal')
                img = self.cam.take_photo()  
            
            offsets, x_rot, y_rot = WG.get_rotation_solution(self.telSock)
            
            centroids = WA.centroid_finder(img)
            #for i in centroids:
            #    print i

            barr = np.argsort(centroids[2])[::-1]
            b = np.argmax(centroids[2])
      
            print "X pixelscale: %f, %f" % (x_rot[0], x_rot[1])
            print "Y pixelscale: %f, %f" % (y_rot[0], y_rot[1])

            d = -1
            for i,b in enumerate(barr):  
                if i > 5:
                    break
                offsetx = centroids[0][b] - 512
                offsety = centroids[1][b] - 512
                dx = offsetx * x_rot
                dy = offsety * y_rot
                radec = dx + dy

                print "Y, Y Offset, RA Move: %f, %f" % (centroids[1][b], offsety)
                print "X, X Offset, DEC Move: %f, %f" % (centroids[0][b], offsetx)
		print "RA Move: %f" % (d*radec[1])
		print "DEC Move: %f" % (d*radec[0])
                print '\n'

            if not auto:
                mpl.close()
                fig = mpl.figure()
                ax = fig.add_subplot(1,1,1)
                im = ax.imshow(np.log10(img), interpolation='none', cmap='gray', origin='lower')
                ax.format_coord = Formatter(im)
                fig.colorbar(im)
                mpl.show()

            b = np.argmax(centroids[2])
            offsetx = centroids[0][b] - 512
            offsety = centroids[1][b] - 512
            dx = offsetx * x_rot
            dy = offsety * y_rot
            radec = dx + dy

        return img, d*radec[1], d*radec[0]

    def focusCamera(self):

        current_focus = self.foc.get_stepper_position() 
        step = 200

        self.cam.set_exposure(3000)
        #self.cam.set_exposure(int(self.entryExpVariable.get()))
        img = self.cam.take_photo()
        focus_check1, bx, by = measure_focus(img)
        direc = 1 #forward

        #plotting
        mpl.ion()
        fig, ax = mpl.subplots(1,1)
       
        imgplot = ax.imshow(img[bx-20:bx+20,by-20:by+20], interpolation = 'none', origin='lower')
        fig.canvas.draw()
        while step > 5:
            self.foc.step_motor(direc*step)
            img = self.cam.take_photo()


            #plotting
            ax.clear()
            imgplot = ax.imshow(img[bx-20:bx+20, by-20:by+20], interpolation = 'none', \
                origin='lower')
            fig.canvas.draw()
            #fig.canvas.restore_region(background)
            #ax.draw_artist(imgplot)
            #fig.canvas.blit(ax.bbox)

            focus_check2,bx2,by2 = measure_focus(img)
            
            print "STEP IS: %i\nPOS IS: %i" % (step,current_focus)
            print "Old Focus: %f, New Focus: %f" % (focus_check1, focus_check2)

            #if focus gets go back to beginning, change direction and reduce step
            if focus_check2 > focus_check1:
                direc = direc*-1
                self.foc.step_motor(direc*step)
                step = int(step / 2)
                print "Focus is worse: changing direction!\n"
            
            focus_check1 = focus_check2
            current_focus = self.foc.get_stepper_position() 
        
        print "### FINISHED FOCUSING ####"

def run_fli_gui_standalone():

    root = _tk.Tk()
    root.title("WIFIS Guider Control")
    
    app = FLIApplication(root)

    root.mainloop()

if __name__ == "__main__":
    run_fli_gui_standalone()
