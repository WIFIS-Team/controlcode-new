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
import matplotlib.pyplot as mpl
import Tkinter as _tk
import WIFISastrometry as WA
import WIFIStelescope as WG

from sys import exit
import os, time, threading, Queue
from glob import glob
import traceback

from PyQt5.QtCore import QThread, QObject, pyqtSignal

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.visualization import (PercentileInterval,\
                                LinearStretch, ImageNormalize)

plate_scale = 0.29125
homedir = os.path.dirname(os.path.realpath(__file__))

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
                if centroids[3][brightstar] == 1:
                    continue
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
    astrometryCalc = pyqtSignal(list)

    def __init__(self, guidevariables):
        '''Initialize the GUI and load the Devices into memory'''

        super(WIFISGuider, self).__init__()
        self.RAMoveBox, self.DECMoveBox,self.focStep,self.expType,self.expTime,\
                self.ObjText,self.SetTempValue,self.FilterVal, self.XPos,\
                self.YPos, self.rotangle, self.coords = guidevariables

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

        if (self.cam == None) or (self.foc == None) or (self.flt == None):
            self.guiderready = False
        else:
            self.guiderready = True

    ## Telescope Functions

    def calcOffset(self):
        #Get rotation solution
        currentcoord = self.getSkyCoord()
        decdeg = currentcoord.dec.deg

        guidevals = WA.read_defaults()
        guideroffsets = [float(guidevals['GuideRA']), float(guidevals['GuideDEC']), decdeg]

        offsets,x_rot,y_rot = WG.get_rotation_solution(float(self.rotangle.text()), guideroffsets)
        yc = float(self.XPos.text())
        xc = float(self.YPos.text())

        offsetx = xc - 512
        offsety = yc - 512
        dx = offsetx*x_rot
        dy = offsety*y_rot
        radec = dx + dy

        self.updateText.emit("### MOVE ###\nRA:\t%f\nDEC:\t%f\n" % (-1*radec[1], -1*radec[0]))

        return

    def getSkyCoord(self):

        RA = self.coords[0].text()
        DEC = self.coords[1].text()

        RA = RA[0:2] + ' ' + RA[3:5] + ' ' + RA[6:]
        DEC = DEC[0:3] + ' ' + DEC[4:6] + ' ' + DEC[7:]

        currentcoord = SkyCoord(RA, DEC, unit=(u.hourangle, u.deg))

        return currentcoord

    def moveTelescope(self):
        if self.telSock:
            try:
                float(self.RAMoveBox.text())
                float(self.DECMoveBox.text())
            except:
                self.updateText.emit("NON-FLOAT ENTRY IN RA/DEC")
                return
                
            result = WG.move_telescope(self.telSock,float(self.RAMoveBox.text()), \
                    float(self.DECMoveBox.text()))
            self.updateText.emit(result)

    def moveTelescopeBack(self):
        if self.telSock:
            try:
                float(self.RAMoveBox.text())
                float(self.DECMoveBox.text())
            except:
                self.updateText.emit("NON-FLOAT ENTRY IN RA/DEC")
                return

            result = WG.move_telescope(self.telSock,-1.*float(self.RAMoveBox.text()), \
                    -1.*float(self.DECMoveBox.text()))
            self.updateText.emit(result)

    def moveTelescopeNod(self, ra, dec):
        if self.telSock:
            result = WG.move_telescope(self.telSock,ra, dec)
            self.updateText.emit(result)

    def offsetToGuider(self):
        if self.telSock:
            self.updateText.emit("### OFFSETTING TO GUIDER FIELD")

            currentcoord = self.getSkyCoord()
            decdeg = currentcoord.dec.deg

            guidevals = WA.read_defaults()
            guideroffsets = [float(guidevals['GuideRA']), float(guidevals['GuideDEC']), decdeg]
            print guideroffsets

            offsets = WA.get_rotation_solution_offset(float(self.rotangle.text()), guideroffsets[:2], decdeg)
            print offsets

            result = WG.move_telescope(self.telSock, offsets[0], offsets[1]) 
            self.updateText.emit(result)
            #self.offsetButton.configure(text='Move to WIFIS',\
            #    command=self.offsetToWIFIS)
            time.sleep(3)

    def offsetToWIFIS(self):
        if self.telSock:
            self.updateText.emit("### OFFSETTING TO WIFIS FIELD")

            currentcoord = self.getSkyCoord()
            decdeg = currentcoord.dec.deg

            guidevals = WA.read_defaults()
            guideroffsets = [float(guidevals['GuideRA']), float(guidevals['GuideDEC']), decdeg]

            offsets = WA.get_rotation_solution_offset(float(self.rotangle.text()), guideroffsets[:2], decdeg)
            result = WG.move_telescope(self.telSock, -1.0*offsets[0], -1.0*offsets[1])
            self.updateText.emit(result)
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
    def saveImage(self, dark=True):

        if self.cam:

            exptime = int(self.expTime.text())
            objtextval = self.ObjText.text()
            if (self.expType.currentText() == 'Dark') and (dark == True):
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(exptime, frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='normal')
                img = self.cam.take_photo()  

            telemDict = WG.get_telemetry(self.telSock)
            telemDict['IIS'] = self.rotangle.text()
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

            return img

        return False

    def takeImage(self, dark = True):
        if self.cam and self.foc:
            exptime = int(self.expTime.text())
            objtextval = self.ObjText.text()

            if (self.expType.currentText() == 'Dark') and (dark == True):
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='dark')
                img = self.cam.take_photo()  
                self.cam.set_exposure(exptime, frametype='normal')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='normal')
                img = self.cam.take_photo()  
   
            self.plotSignal.emit(img, objtextval)
            
            return img

        return False

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
                self.cam.set_exposure(exptime, frametype='normal')
                img = self.cam.take_photo()  
                self.cam.set_exposure(exptime, frametype='dark')
            else:
                self.cam.end_exposure()
                self.cam.set_exposure(exptime, frametype='normal')
                img = self.cam.take_photo()  

            if not auto:
                self.plotSignal.emit(img, "Centroids")

            currentcoord = self.getSkyCoord()
            decdeg = currentcoord.dec.deg

            guidevals = WA.read_defaults()
            guideroffsets = [float(guidevals['GuideRA']), float(guidevals['GuideDEC']), decdeg]
                
            offsets, x_rot, y_rot = WG.get_rotation_solution(float(self.rotangle.text()), guideroffsets)
            
            centroids = WA.centroid_finder(img)
            for a in centroids:
                print a
            if centroids == False:
                self.updateText.emit("NO STARS FOUND -- TRY INCREASING EXP TIME")
                return
                
            barr = np.argsort(centroids[2])[::-1]

            try:
                b = np.argmax(centroids[2])
            except:
                self.updateText.emit("NO STARS FOUND -- TRY INCREASING EXP TIME")
                return
                
      
            #self.updateText.emit("X pixelscale: %f, %f" % (x_rot[0], x_rot[1]))
            #self.updateText.emit("Y pixelscale: %f, %f" % (y_rot[0], y_rot[1]))

            self.updateText.emit("PRINTING THE CENTROIDS FOR THE\nFOUR BRIGHTEST STARS IN THE IMAGE")
            d = -1
            for i,b in enumerate(barr):  
                if i > 3:
                    break
                offsetx = centroids[0][b] - 512
                offsety = centroids[1][b] - 512
                dx = offsetx * x_rot
                dy = offsety * y_rot
                radec = dx + dy

                self.updateText.emit("#### STAR %i ####" % (i+1))
                self.updateText.emit("X, X Offset: %f, %f" % (centroids[0][b], offsetx))
                self.updateText.emit("Y, Y Offset: %f, %f" % (centroids[1][b], offsety))
                self.updateText.emit("RA Move: %f" % (d*radec[1]))
                self.updateText.emit("DEC Move: %f" % (d*radec[0]))
                self.updateText.emit("#################")
                self.updateText.emit("\n")

            b = np.argmax(centroids[2])
            offsetx = centroids[0][b] - 512
            offsety = centroids[1][b] - 512
            dx = offsetx * x_rot
            dy = offsety * y_rot
            radec = dx + dy
            self.updateText.emit("### FINISHED CHECK CENTROIDS")

        return img, d*radec[1], d*radec[0]

    def doAstrometry(self):
        if self.cam:
            exptime = int(self.expTime.text())
            self.updateText.emit("TAKING ASTROMETRIC IMAGE")
            img = self.takeImage(dark=False)

            self.plotSignal.emit(img, 'Astrometry')
            self.updateText.emit("STARTING ASTROMETRIC DERIVATION")
            try:
                results = WA.getAstrometricSoln(img, self.telSock, self.rotangle.text())
                if len(results) < 3:
                    self.updateText.emit("NO ASTROMETRIC SOLUTION...NOT ENOUGH STARS? >=3")
                    self.updateText.emit("Try increasing exp time, or moving to a different field")
                else:
                    platesolve, fieldoffset, realcenter, solvecenter, guideroffsets,plotting = results
                    self.updateText.emit("Real Guider Center is: \nRA:\t%s\n DEC:\t%s" % \
                            (self.returnhmsdmsstr(solvecenter.ra.hms), self.returnhmsdmsstr(solvecenter.dec.dms)))
                    #self.updateText.emit('Guider Offset (") is: \nRA: %s\n DEC: %s' % (fieldoffset[0].to(u.arcsec).to_string(),\
                    #        fieldoffset[1].to(u.arcsec).to_string()))
                    self.astrometryCalc.emit([solvecenter, guideroffsets, plotting])

            except Exception as e:
                print e
                print traceback.print_exc()
                self.updateText.emit("SOMETHING WENT WRONG WITH ASTROMETRY....\nCHECK TERMINAL")

    def returnhmsdmsstr(self,angle):

        return str(int(angle[0])) + ' '+ str(int(angle[1])) + ' ' + str(float(angle[2]))


    def focusCamera(self):

        focusthread = FocusCamera(self.cam, self.foc,self.expTime)
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
    
    def __init__(self, cam, foc, expTime):
        QThread.__init__(self)
        self.cam = cam
        self.foc = foc
        self.expTime = int(expTime.text())
        self.stopThread = False

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopThread = True

    def run(self):
        self.updateText.emit("STARTING GUIDE CAMERA FOCUSING...")
        current_focus = self.foc.get_stepper_position() 
        step = 200

        if self.expTime > 4000:
            self.updateText.emit("EXPTIME TOO LONG, FIND BRIGHTER FIELD OR CHANGE TIME")
            return

        #self.cam.set_exposure(3000)
        self.cam.set_exposure(self.expTime)
        img = self.cam.take_photo()
        focus_check1, bx, by = measure_focus(img)
        direc = 1 #forward

        #plotting
        self.plotSignal.emit(img[bx-20:bx+20,by-20:by+20], "Focusing")

        while step > 5:
            self.foc.step_motor(direc*step)
            img = self.cam.take_photo()


            #plotting
            self.plotSignal.emit(img[bx-20:bx+20,by-20:by+20], "Focusing")

            focus_check2,bx2,by2 = measure_focus(img)
            
            self.updateText.emit("STEP IS: %i\nPOS IS: %i" % (step,current_focus))
            self.updateText.emit("Old Focus: %f, New Focus: %f" % (focus_check1, focus_check2))

            #if focus gets go back to beginning, change direction and reduce step
            if (focus_check2 > focus_check1) or (focus_check2 == np.NaN):
                direc = direc*-1
                self.foc.step_motor(direc*step)
                step = int(step / 2)
                self.updateText.emit("Focus is worse: changing direction!\n")
            
            focus_check1 = focus_check2
            current_focus = self.foc.get_stepper_position() 
        
        self.updateText.emit("### FINISHED FOCUSING")

class RunGuiding(QThread):

    updateText = pyqtSignal(str)
    setSkySignal = pyqtSignal(str)
    plotSignal = pyqtSignal(np.ndarray, str)
    endNodding = pyqtSignal(bool)

    def __init__(self, telsock, cam, guideTargetVar, rotangle, guideexp, overguidestar, coords, sky=False):
        QThread.__init__(self)
        self.telsock = telsock
        self.guideTargetVar = guideTargetVar
        self.exptime= int(guideexp)
        self.cam = cam
        self.deltRA = 0
        self.deltDEC = 0
        self.stopThread = False
        self.sky = sky
        self.rotangle = float(rotangle.text())
        self.overguidestar = overguidestar
        self.coords = coords
        self.guidevals = WA.read_defaults()

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopThread = True

    def getSkyCoord(self):

        RA = self.coords[0].text()
        DEC = self.coords[1].text()

        RA = RA[0:2] + ' ' + RA[3:5] + ' ' + RA[6:]
        DEC = DEC[0:3] + ' ' + DEC[4:6] + ' ' + DEC[7:]

        currentcoord = SkyCoord(RA, DEC, unit=(u.hourangle, u.deg))

        return currentcoord

    def run(self):
    
        if self.stopThread: #Re-initializing hack?
            self.stopThread = False

        if self.sky:
            self.guideTargetText = self.guideTargetVar.text() + 'Sky'
        else:
            self.guideTargetText = self.guideTargetVar.text()

        self.updateText.emit("### STARTING GUIDING ON %s" % (self.guideTargetText))
        gfls = self.checkGuideVariable()

        guidingstuff = self.wifis_simple_guiding_setup(gfls)
        #guidingstuff = [offsets, x_rot, y_rot, stary1, starx1, boxsize, img1, fieldinfo]

        if (guidingstuff[3] == 'NoStar') or (guidingstuff[4] == 'NoStar'):
            self.updateText.emit("NO STARS IN CENTER FIELD...INCREASING GUIDE TIME...")
            self.exptime += 1000

            while (guidingstuff[3] == 'NoStar') and (self.exptime < 9000):
                self.updateText.emit("TRYING GUIDE EXPTIME: %i" % (self.exptime))
                guidingstuff = self.wifis_simple_guiding_setup(gfls)
                self.exptime += 1000

            #if guidingstuff[3] == 'NoStar':
            #    self.updateText.emit("NO STARS TO GUIDE ON AT 9s, QUITTING")
            #    self.endNodding.emit(True)
            #    return 

        if (guidingstuff[3] == None) or (guidingstuff[4] == None):
            self.updateText.emit("NO STARS TO GUIDE ON...INCREASING GUIDE TIME...")
            self.exptime += 1000

            while (guidingstuff[3] == None) and (self.exptime < 9000):
                self.updateText.emit("TRYING GUIDE EXPTIME: %i" % (self.exptime))
                guidingstuff = self.wifis_simple_guiding_setup(gfls)
                self.exptime += 1000

            #if guidingstuff[3] == None:
            #    self.updateText.emit("NO STARS TO GUIDE ON AT 9s, QUITTING")
            #    self.endNodding.emit(True)
            #    return 

        elif guidingstuff[3] == False:
            self.updateText.emit("ALL STARS IN FIELD SATURATED..DECREASING GUIDE TIME...")
            self.exptime -= 100

            while (guidingstuff[3] == False) and (self.exptime > 0):
                self.updateText.emit("TRYING GUIDE EXPTIME: %i" % (self.exptime))
                guidingstuff = self.wifis_simple_guiding_setup(gfls)
                if self.exptime < 150:
                    self.exptime -= 10
                else:
                    self.exptime -= 100

            if guidingstuff[3] == False:
                self.updateText.emit("ALL STARS IN FIELD SATURATED AT ALL EXPTIME, QUITTING")
                self.endNodding.emit(True)
                return 

        if guidingstuff[3] in [False, None, 'NoStar']:
            self.updateText.emit("SOMETHING WENT WRONG WITH GUIDE STAR ASSIGNMENT...")
            self.endNodding.emit(True)
            return

        fieldinfo = guidingstuff[7]
        try:
            if (fieldinfo != None) and (guidingstuff[3] != None):
                fieldinfofl = np.savetxt(homedir+'/data/guidefield/'+time.strftime('%Y%m%dT%H%M%S')+\
                        '_'+self.guideTargetText+'.txt', np.transpose(fieldinfo))
        except Exception as e:
            print e
        
        try:
            #Plot guide star for reference
            starybox = int(guidingstuff[3])
            starxbox = int(guidingstuff[4])
            boxsize = int(guidingstuff[5])
        except Exception as e:
            starybox = None
            starxbox = None
            print e
            self.updateText.emit("SOMETHING WENT WRONG WITH GUIDE STAR ASSIGNMENT...")
            return
            #self.quit()

        self.plotSignal.emit(guidingstuff[6][starybox-boxsize:starybox+boxsize, starxbox-boxsize:starxbox+boxsize],\
                self.guideTargetText + " GuideStar")

        guidingstuff = guidingstuff[:7]
        something_wrong_count = 0
        while True:
            if self.stopThread:
                self.cam.end_exposure()
                self.updateText.emit("### FINISHED GUIDING")
                break
            else:
                try:
                    dRA, dDEC = self.run_guiding(guidingstuff)
                    self.deltRA += dRA
                    self.deltDEC += dDEC
                    self.updateText.emit("DELTRA:\t%f\nDELTDEC:\t%f\n" % (self.deltRA, self.deltDEC))
                    something_wrong_count = 0
                except Exception as e:
                    print e
                    print traceback.print_exc()
                    self.updateText.emit("SOMETHING WRONG WITH GUIDING...CONTINUING...")
                    something_wrong_count += 1
                    #if something_wrong_count > 3:
                    #    self.updateText.emit("INCREASING GUIDE EXP TIME BY 1s...")
                    #    self.exptime += 1000
                        #self.cam.set_exposure(self.exptime, frametype="normal")
                    if something_wrong_count > 15:
                        self.updateText.emit("GUIDING NOT WORKING...QUITTING")
                        break

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
        gfl = homedir+'/data/guidefiles/'+time.strftime('%Y%m%d')+'_'+self.guideTargetText+'.txt'
        guidefls = glob(homedir+'/data/guidefiles/*.txt')
        if self.guideTargetText == '':
            return '', False
        if (gfl in guidefls) and (self.overguidestar.isChecked()):
            self.updateText.emit("OVERWRITING GUIDE STAR...UNCHECKING")
            os.remove(gfl)
            self.overguidestar.setChecked(False)
            return gfl, False
        elif gfl not in guidefls:
            self.updateText.emit("OBJECT NOT OBSERVED, INITIALIZING GUIDE STAR")
            return gfl, False
        else:
            self.updateText.emit("OBJECT ALREADY OBSERVED, USING ORIGINAL GUIDE STAR")
            return gfl, True

    def wifis_simple_guiding_setup(self, gfls):

        #Gets the rotation solution so that we can guide at any instrument rotation angle
        currentcoord = self.getSkyCoord()
        decdeg = currentcoord.dec.deg

        guideroffsets = [float(self.guidevals['GuideRA']), float(self.guidevals['GuideDEC']), decdeg]

        offsets, x_rot, y_rot = WG.get_rotation_solution(self.rotangle, guideroffsets)

        #Take image with guider (with shutter open)
        self.cam.set_exposure(self.exptime, frametype="normal")
        self.cam.end_exposure()

        #Takes initial image
        img1 = self.cam.take_photo()
        img1size = img1.shape
        boxsize = 30

        #Checks to see if there exists a guiding star for this target
        if gfls[1] and (gfls[0] != ''):
            #Sets the larger boxsize for guiding setup
            boxsize_f = 50
            
            #Get the original guidestar coordinates.
            f = open(gfls[0], 'r')
            lines = f.readlines()

            spl = lines[0].split()
            starx1old, stary1old = int(spl[0]), int(spl[1])

            centroidxold, centroidyold = [], []
            diffxold, diffyold = [], []
            if len(lines) > 1:
                for l in range(1, len(lines)):
                    spl = lines[l].split()
                    centroidxold.append(int(spl[0]))
                    centroidyold.append(int(spl[1]))
                    diffxold.append(int(spl[0]) - starx1old)
                    diffyold.append(int(spl[1]) - stary1old)

            if len(lines) > 1:
                inbox = self.numstarsinbox(centroidxold, centroidyold, starx1old, stary1old, boxsize_f)
            else:
                inbox = []

            if len(inbox) > 0:
                #Create box around star and check if star is in box. If star, correct it. If no star, reinitialize guiding
                imgbox = img1[stary1old-boxsize_f:stary1old+boxsize_f, starx1old-boxsize_f:starx1old+boxsize_f]
                worked, Iarr = self.checkstarinbox(imgbox, boxsize_f, multistar = [diffxold, diffyold, inbox])
            else:
                #Create box around star and check if star is in box. If star, correct it. If no star, reinitialize guiding
                imgbox = img1[stary1old-boxsize_f:stary1old+boxsize_f, starx1old-boxsize_f:starx1old+boxsize_f]
                worked, Iarr = self.checkstarinbox(imgbox, boxsize_f, multistar = False)
            
            if worked:
                #If we could put a star at the right coordinates, set the guiding coords to the old coords
                starx1 = starx1old
                stary1 = stary1old
                self.updateText.emit("FOUND OLD GUIDE STAR...CORRECTING")
                fieldinfo = None
            else:
                #If we could not move a star to the right coordinates, then restart guiding for this object
                self.updateText.emit("COULD NOT FIND OLD GUIDESTAR IN IMAGE...SELECTING NEW GUIDESTAR")
                starx1, stary1, centroidx,centroidy,Iarr,Isat,width, gs = self.findguidestar(img1, gfls)
                fieldinfo = [centroidx,centroidy,Iarr,Isat, width]
        else:
            #restart guiding by selecting a new guide star in the image 
            starx1, stary1, centroidx,centroidy,Iarr,Isat,width,gs = self.findguidestar(img1,gfls)
            fieldinfo = [centroidx,centroidy,Iarr,Isat, width]
            worked = False
        
        #Make sure were guiding on an actual star. If not maybe change the exptime for guiding.
        print starx1, stary1
        #Record this initial setup in the file
        if (gfls[0] != '') and (starx1 not in [None, False, "NoStar"]) and (not worked):
            f = open(gfls[0], 'w')
            f.write('%i\t%i\t%i\t%i\n' % (starx1, stary1, self.exptime, Iarr[gs]))
            for j in range(len(centroidx)):
                if j == gs:
                    continue
                f.write('%i\t%i\t%i\t%i\n' % (centroidy[j], centroidx[j], self.exptime, Iarr[j]))
            f.close()
        

        return [offsets, x_rot, y_rot, stary1, starx1, boxsize, img1, fieldinfo]

    def numstarsinbox(self, centroidx, centroidy, starx1, stary1, boxsize):
        
        inbox = []
        for i in range(len(centroidx)):
            if (centroidx[i]  > starx1 - boxsize) and (centroidx[i] < starx1 + boxsize) \
                    and (centroidy[i] > stary1 - boxsize) and (centroidy[i] < stary1 + boxsize):
                inbox.append(i)
        
        return inbox

    def findguidestar(self, img1, gfls):
        #check positions of stars    
        CFReturns = WA.centroid_finder(img1, plot=False)

        if CFReturns == False:
            return None, None, False, False, False, False, False, False

        centroidx, centroidy, Iarr, Isat, width = CFReturns 

        #for i in CFReturns:
        #    print i

        bright_stars = np.argsort(Iarr)[::-1]

        #Choose the brightest non-saturated star for guiding
        try:
            guiding_star = bright_stars[0]
        except:
            return None,None,centroidx,centroidy,Iarr,Isat,width, None

        #Checking to see if the star is in the "center" of the field and isn't saturated
        for star in bright_stars:
            if (centroidx[star] > 50) and (centroidx[star] < 950) and \
                (centroidy[star] > 50) and (centroidy[star] < 950):
                if Isat[star] != 1:
                    guiding_star = star
                    break 
        
        stary1 = centroidx[guiding_star]
        starx1 = centroidy[guiding_star] 

        if Iarr[guiding_star] < 9000:
            return None,None,centroidx,centroidy,Iarr,Isat,width, guiding_star

        if Isat[guiding_star] == 1:
            return False, False, centroidx, centroidy, Iarr, Isat, width, guiding_star

        if (centroidx[guiding_star] < 50) or (centroidx[guiding_star] > 950) or \
                (centroidy[guiding_star] > 50 and centroidy[guiding_star] > 950):
            return 'NoStar', 'NoStar', centroidx, centroidy, Iarr, Isat, width, guiding_star

        return starx1, stary1, centroidx,centroidy,Iarr,Isat,width,guiding_star

    def checkstarinbox(self, imgbox, boxsize, multistar = False):

        currentcoord = self.getSkyCoord()
        decdeg = currentcoord.dec.deg

        guideroffsets = [float(self.guidevals['GuideRA']), float(self.guidevals['GuideDEC']), decdeg]

        offsets, x_rot, y_rot = WG.get_rotation_solution(self.rotangle, guideroffsets)
        
        #Try centroiding
        CFReturns = WA.centroid_finder(imgbox, plot=False)

        if CFReturns == False:
            return False, False

        centroidx, centroidy, Iarr, Isat, width = CFReturns

        if not multistar:
            try:
                #If centroid worked, great
                new_loc = np.argmax(Iarr)
            except:
                #If centroid didn't work, exit and restart gudding
                return False, False

            newx = centroidx[new_loc]
            newy = centroidy[new_loc]

            #Figure out how to move based on the rotation solution
            dx = newx - boxsize 
            dy = newy - boxsize
            d_ra = dx * x_rot
            d_dec = dy * y_rot
            radec = d_ra + d_dec

            self.updateText.emit("INITIAL MOVEMENT TO GET SOURCE BACK IN CENTER")
            self.updateText.emit("X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f\n" \
               % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale))

            #Move the telescope if the required movement is greater than 0.5" 
            lim = 0.5
            r = -1
            d = -1

            if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
                self.updateText.emit("NOT MOVING, TOO SMALL SHIFT")
            elif abs(radec[1]) < lim:
                self.updateText.emit("MOVING DEC ONLY")
                WG.move_telescope(self.telsock, 0.0, d*radec[0], verbose=False)
            elif abs(radec[0]) < lim:
                self.updateText.emit("MOVING RA ONLY")
                WG.move_telescope(self.telsock, r*radec[1], 0.0, verbose=False)
            else:
                WG.move_telescope(self.telsock,r*radec[1],d*radec[0], verbose=False)
            
            time.sleep(2)

            return True, Iarr

        else:
            diffxold, diffyold, inbox = multistar
            inbox_xold, inbox_yold = [], []
            for i in inbox:
                inbox_xold.append(diffxold[i])
                inbox_yold.append(diffyold[i])

            try:
                #If centroid worked, great
                new_loc = np.argmax(Iarr)
            except:
                #If centroid didn't work, exit and restart guiding
                return False, False

            newx = centroidx[new_loc]
            newy = centroidy[new_loc]
            
            #Figure out how to move based on the rotation solution
            dx = newx - boxsize 
            dy = newy - boxsize
            d_ra = dx * x_rot
            d_dec = dy * y_rot
            radec = d_ra + d_dec
            
            self.updateText.emit("INITIAL MOVEMENT TO GET SOURCE BACK IN CENTER")
            self.updateText.emit("X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f\n" \
               % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale))

            #Move the telescope if the required movement is greater than 0.5" 
            lim = 0.5
            r = -1
            d = -1

            if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
                self.updateText.emit("NOT MOVING, TOO SMALL SHIFT")
            elif abs(radec[1]) < lim:
                self.updateText.emit("MOVING DEC ONLY")
                WG.move_telescope(self.telsock, 0.0, d*radec[0], verbose=False)
            elif abs(radec[0]) < lim:
                self.updateText.emit("MOVING RA ONLY")
                WG.move_telescope(self.telsock, r*radec[1], 0.0, verbose=False)
            else:
                WG.move_telescope(self.telsock,r*radec[1],d*radec[0], verbose=False)

            return True, Iarr

           #result.append("Checking if right guide star")

    def run_guiding(self, inputguiding):
       
        #Get all the parameters from the guiding input
        offsets, x_rot, y_rot, stary1, starx1, boxsize, img1  = inputguiding

        #Take an image
        img = self.cam.take_photo(shutter='open')
        starx_box = int(starx1)
        stary_box = int(stary1)
        imgbox = img[stary_box-boxsize:stary_box+boxsize, starx_box-boxsize:starx_box+boxsize]

        #FInd the star in the box
        CFReturns = WA.centroid_finder(imgbox, plot=False)
        if CFReturns == False:
            return
        
        centroidx, centroidy, Iarr, Isat, width = CFReturns

        try:
            new_loc = np.argmax(Iarr)
        except:
            return

        newx = centroidx[new_loc]
        newy = centroidy[new_loc]

        #Determine rotation solution 
        dx = newx - boxsize 
        dy = newy - boxsize
        d_ra = dx * x_rot
        d_dec = dy * y_rot
        radec = d_ra + d_dec

        self.updateText.emit("X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t%f" \
           % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale))

        ##### IMPORTANT GUIDING PARAMETERS #####
        lim = 0.6 #Changes the absolute limit at which point the guider moves the telescope
        d = -0.9 #Affects how much the guider corrects by. I was playing around with -0.8 but the default is -1. Keep this negative.
        #######################################

        deltRA = 0
        deltDEC = 0

        guidingon=True
        if guidingon:
            if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
                self.updateText.emit("NOT MOVING, TOO SMALL SHIFT\n")
            elif abs(radec[1]) < lim:
                self.updateText.emit("MOVING DEC ONLY\n")
                deltDEC = d*radec[0]
                WG.move_telescope(self.telsock, 0.0, d*radec[0], verbose=False)
            elif abs(radec[0]) < lim:
                self.updateText.emit("MOVING RA ONLY\n")
                deltRA = d*radec[1]
                WG.move_telescope(self.telsock, d*radec[1], 0.0, verbose=False)
            else:
                deltRA = d*radec[1]
                deltDEC = d*radec[0]
                WG.move_telescope(self.telsock,d*radec[1],d*radec[0], verbose=False)
                self.updateText.emit("\n")

        #Record for guiding checking later
        f = open(homedir+'/log/guidinglog/'+time.strftime('%Y%m%dT%H')+'.txt', 'a')
        f.write("%f\t%f\n" % (radec[1],radec[0]))
        f.close()

        self.plotSignal.emit(imgbox,self.guideTargetText + ' GuideStar')

        return deltRA, deltDEC











