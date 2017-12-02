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
import wifisguidingfunctions as WG
import os, time, threading, Queue
from glob import glob
from astropy.visualization import (PercentileInterval,\
                                LinearStretch, ImageNormalize)
from PyQt5.QtCore import QThread, QObject, pyqtSignal

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
                cx = int(centroids[0][brightstar])
                cy = int(centroids[1][brightstar])
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
                    mpl.pause(0.0001)

                try:

                    popt, pcov = WA.gaussian_fit(xs, star_x, [30000., 3.0, 10.0])
                    starsx = np.append(starsx,popt[1])
                    popt, pcov = WA.gaussian_fit(xs, star_y, [30000., 3.0, 10.0])
                    starsy = np.append(starsy,popt[1])
                except:
                    continue

    xavg = np.mean(starsx)
    yavg = np.mean(starsy)

    return [np.mean([xavg, yavg]), brightestx, brightesty]

################################################################################
class WIFISGuider(QObject): 
    '''Creates the FLI GUI window and also contains a number of 
    functions for controlling the Filter Wheel, Focuser, and
    Camera.'''

    updateText = pyqtSignal(str)
    plotSignal = pyqtSignal(np.ndarray,str)

    def __init__(self, guidevariables):
        '''Initialize the GUI and load the Devices into memory'''

        super(WIFISGuider, self).__init__()
        self.RAMoveBox, self.DECMoveBox,self.focStep,self.expType,self.expTime,\
                self.ObjText,self.SetTempValue,self.FilterVal, self.XPos,\
                self.YPos, self.rotangle = guidevariables

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

    ## Telescope Functions

    def calcOffset(self):
        #Get rotation solution
        offsets,x_rot,y_rot = WG.get_rotation_solution(self.telSock, float(self.rotangle.text()))
        yc = float(self.XPos.text())
        xc = float(self.YPos.text())

        offsetx = xc - 512
        offsety = yc - 512
        dx = offsetx*x_rot
        dy = offsety*y_rot
        radec = dx + dy

        self.updateText.emit("### MOVE ###\nRA:\t%f\nDEC:\t%f\n" % (-1*radec[1], -1*radec[0]))

        return

    def moveTelescope(self):
        if self.telSock:
            WG.move_telescope(self.telSock,float(self.RAMoveBox.text()), \
                    float(self.DECMoveBox.text()))

    def moveTelescopeBack(self):
        if self.telSock:
            WG.move_telescope(self.telSock,-1.*float(self.RAMoveBox.text()), \
                    -1.*float(self.DECMoveBox.text()))

    def moveTelescopeNod(self, ra, dec):
        if self.telSock:
            WG.move_telescope(self.telSock,ra, dec)

    def offsetToGuider(self):
        if self.telSock:
            self.updateText.emit("### OFFSETTING TO GUIDER FIELD ###")
            offsets, x_rot, y_rot = WG.get_rotation_solution(self.telSock, float(self.rotangle.text()))
            WG.move_telescope(self.telSock, offsets[0], offsets[1]) 
            #self.offsetButton.configure(text='Move to WIFIS',\
            #    command=self.offsetToWIFIS)
            time.sleep(3)

    def offsetToWIFIS(self):
        if self.telSock:
            self.updateText.emit("### OFFSETTING TO WIFIS FIELD ###")
            offsets, x_rot, y_rot = WG.get_rotation_solution(self.telSock, float(self.rotangle.text()))
            WG.move_telescope(self.telSock, -1.0*offsets[0], -1.0*offsets[1])
            #self.offsetButton.configure(text='Move to Guider',\
            #    command=self.offsetToGuider)
            time.sleep(3)

    ## Filter Wheel Functions
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

    def goToFilter(self):
        if self.flt:
            flttype = self.FilterVal.currentText()
             
            if flttype == 'Z':
                self.flt.set_filter_pos(0)
            elif flttype == 'I':
                self.flt.set_filter_pos(1)
            elif flttype == 'R':
                self.flt.set_filter_pos(2)
            elif flttype == 'G':
                self.flt.set_filter_pos(3)
            elif flttype == 'H-Alpha':
                self.flt.set_filter_pos(4)

    ## Focuser Functions
    def homeFocuser(self):
        if self.foc:
            self.foc.home_focuser()

    def stepForward(self):
        if self.foc:
            self.foc.step_motor(int(self.focStep.text()))

    def stepBackward(self):
        if self.foc:
            self.foc.step_motor(-1*int(self.focStep.text()))    

    ## Camera Functions
    def saveImage(self):

        if self.cam:

            exptime = int(self.expTime.text())
            objtextval = self.ObjText.text()
            if self.expType.currentText() == 'Dark':
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(exptime, frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='normal')
                img = self.cam.take_photo()  

            telemDict = WG.get_telemetry(self.telSock)
            hduhdr = self.makeHeader(telemDict)

            if objtextval == "":
                self.updateText.emit("Writing to: "+self.direc+self.todaydate+'T'+time.strftime('%H%M%S')+'.fits')
                fits.writeto(self.direc+self.todaydate+'T'+\
                        time.strftime('%H%M%S')+'.fits', img, hduhdr,clobber=True)
            else:
                self.updateText.emit("Writing to: "+self.direc+self.todaydate+'T'+\
                        time.strftime('%H%M%S')+'_'+objtextval+".fits")
                fits.writeto(self.direc+self.todaydate+'T'+\
                        time.strftime('%H%M%S')+'_'+objtextval+".fits",\
                        img, hduhdr,clobber=True)

            self.plotSignal.emit(img, objtextval)

    def takeImage(self):
        if self.cam and self.foc:
            exptime = int(self.expTime.text())
            objtextval = self.ObjText.text()

            if self.expType.currentText() == 'Dark':
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(exptime, frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='normal')
                img = self.cam.take_photo()  
   
            self.plotSignal.emit(img, objtextval)

    def makeHeader(self, telemDict):

        hdr = fits.Header()
        hdr['DATE'] = self.todaydate 
        hdr['SCOPE'] = 'Bok Telescope, Steward Observatory'
        hdr['ObsTime'] = time.strftime('%H:%M"%S')
        hdr['ExpTime'] = self.expTime.text()
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
            self.cam.set_temperature(int(self.SetTempValue.text()))


    def checkCentroids(self, auto=False):

        if self.cam and self.foc:
            exptime = int(self.expTime.text())
            if self.expType.currentText() == 'Dark':
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(exptime, frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='normal')
                img = self.cam.take_photo()  
            
            offsets, x_rot, y_rot = WG.get_rotation_solution(self.telSock, float(self.rotangle.text()))
            
            centroids = WA.centroid_finder(img)
            #for i in centroids:
            #    print i

            barr = np.argsort(centroids[2])[::-1]
            b = np.argmax(centroids[2])
      
            self.updateText.emit("X pixelscale: %f, %f" % (x_rot[0], x_rot[1]))
            self.updateText.emit("Y pixelscale: %f, %f" % (y_rot[0], y_rot[1]))

            d = -1
            for i,b in enumerate(barr):  
                if i > 3:
                    break
                offsetx = centroids[0][b] - 512
                offsety = centroids[1][b] - 512
                dx = offsetx * x_rot
                dy = offsety * y_rot
                radec = dx + dy

                self.updateText.emit("Y, Y Offset, RA Move: %f, %f" % (centroids[1][b], offsety))
                self.updateText.emit("X, X Offset, DEC Move: %f, %f" % (centroids[0][b], offsetx))
		self.updateText.emit("RA Move: %f" % (d*radec[1]))
		self.updateText.emit("DEC Move: %f" % (d*radec[0]))
                self.updateText.emit("\n")

            if not auto:
                self.plotSignal.emit(img, "Centroids")

            b = np.argmax(centroids[2])
            offsetx = centroids[0][b] - 512
            offsety = centroids[1][b] - 512
            dx = offsetx * x_rot
            dy = offsety * y_rot
            radec = dx + dy

        return img, d*radec[1], d*radec[0]

    def focusCamera(self):

        focusthread = FocusCamera(self.cam, self.foc)
        focusthread.start()

    def startGuiding(self):

        guidinginstance = RunGuiding(self.telSock, self.cam, self.ObjText)
        guidinginstance.start()
        
class ExposeGuider(QThread):

    def __init__(self, guider, save):
        QThread.__init__(self)
        self.stopThread = False
        self.guider = guider
        self.save=save

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopThread = True

    def run(self):
        if self.save:
            self.guider.saveImage()
        else:
            self.guider.takeImage()


class FocusCamera(QThread):

    updateText = pyqtSignal(str)
    plotSignal = pyqtSignal(np.ndarray, str)
    
    def __init__(self, cam, foc):
        QThread.__init__(self)
        self.cam = cam
        self.foc = foc
        self.stopThread = False

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopThread = True

    def run(self):
        self.updateText.emit("STARTING GUIDE CAMERA FOCUSING...")
        current_focus = self.foc.get_stepper_position() 
        step = 200

        self.cam.set_exposure(3000)
        #self.cam.set_exposure(int(self.entryExpVariable.get()))
        img = self.cam.take_photo()
        focus_check1, bx, by = measure_focus(img)
        direc = 1 #forward

        #plotting
        self.plotSignal(img[bx-20:bx+20,by-20:by+20], "Focusing")

        while step > 5:
            self.foc.step_motor(direc*step)
            img = self.cam.take_photo()


            #plotting
            self.plotSignal(img[bx-20:bx+20,by-20:by+20], "Focusing")

            focus_check2,bx2,by2 = measure_focus(img)
            
            self.updateText.emit("STEP IS: %i\nPOS IS: %i" % (step,current_focus))
            self.updateText.emit("Old Focus: %f, New Focus: %f" % (focus_check1, focus_check2))

            #if focus gets go back to beginning, change direction and reduce step
            if focus_check2 > focus_check1:
                direc = direc*-1
                self.foc.step_motor(direc*step)
                step = int(step / 2)
                self.updateText.emit("Focus is worse: changing direction!\n")
            
            focus_check1 = focus_check2
            current_focus = self.foc.get_stepper_position() 
        
        self.updateText.emit("### FINISHED FOCUSING ####")


class RunGuiding(QThread):

    updateText = pyqtSignal(str)
    setSkySignal = pyqtSignal(str)
    plotSignal = pyqtSignal(np.ndarray, str)

    def __init__(self, telsock, cam, guideTargetVar, rotangle, sky=False):
        QThread.__init__(self)
        self.telsock = telsock
        self.guideTargetVar = guideTargetVar
        #self.guideExpVariable = guideExpVariable
        self.guideExpVariable = 1500
        self.cam = cam
        self.deltRA = 0
        self.deltDEC = 0
        self.stopThread = False
        self.sky = False
        self.rotangle = float(rotangle.text())

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopThread = True

    def run(self):
    
        if self.stopThread: #Re-initializing hack?
            self.stopThread = False

        if sky:
            self.guideTargetText = self.guideTargetVar.text() + 'Sky'
        else:
            self.guideTargetText = self.guideTargetVar.text()

        self.updateText.emit("###### STARTING GUIDING ON %s" % (self.guideTargetText))
        #self.guideButtonVar.set("Stop Guiding")
        gfls = self.checkGuideVariable()
        guidingstuff = WG.wifis_simple_guiding_setup(self.telsock, self.cam, \
            int(self.guideExpVariable),gfls, self.rotangle)

        #Plot guide star for reference
        starybox = int(guidingstuff[3])
        starxbox = int(guidingstuff[4])
        boxsize = int(guidingstuff[5])
        self.plotSignal.emit(guidingstuff[-1][starybox-boxsize:starybox+boxsize, starxbox-boxsize:starxbox+boxsize],\
                "Guide Star")
        while True:
            if self.stopThread:
                self.cam.end_exposure()
                self.updateText.emit("###### FINISHED GUIDING")
                break
            else:

                try:
                    dRA, dDEC, guideinfo, guideresult, img = WG.run_guiding(guidingstuff,\
                            self.cam, self.telsock,self.rotangle)
                    self.plotSignal.emit(img[starybox-boxsize:starybox+boxsize,\
                            starxbox-boxsize:starxbox+boxsize],"Guide Star")
                    self.deltRA += dRA
                    self.deltDEC += dDEC
                    self.updateText.emit(guideinfo)
                    self.updateText.emit(guideresult)
                    self.updateText.emit("DELTRA:\t%f\nDELTDEC:\t%f\n" % (self.deltRA, self.deltDEC))
                except Exception as e:
                    print e
                    self.updateText.emit("SOMETHING WRONG WITH GUIDING...CONTINUING...")

    def setSky(self):
        self.setSkySignal.emit("True")
        self.sky = True
        self.guidetargettext = self.guideTargetVar.text() + 'Sky'

    def setObj(self):
        if self.sky:
            self.setSkySignal.emit("False")
            self.guidetargettext = self.guideTargetVar.text()[:-3]
            self.sky=False

    def checkGuideVariable(self):
        gfl = '/home/utopea/elliot/guidefiles/'+time.strftime('%Y%m%d')+'_'+self.guideTargetText+'.txt'
        guidefls = glob('/home/utopea/elliot/guidefiles/*.txt')
        if self.guideTargetText == '':
            return '', False
        if gfl not in guidefls:
            self.updateText.emit("OBJECT NOT OBSERVED, INITIALIZING GUIDE STAR")
            return gfl, False
        else:
            self.updateText.emit("OBJECT ALREADY OBSERVED, USING ORIGINAL GUIDE STAR")
            return gfl, True
    

