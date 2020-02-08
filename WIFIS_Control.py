####################################################
# WIFIS Control Software GUI
#
# Developed by: R Elliot Meyer, PhD 2019
####################################################

from wifis_new import Ui_MainWindow
from PyQt5.QtWidgets import QApplication, QMainWindow, QDesktopWidget
from PyQt5.QtCore import QThread, QCoreApplication, QTimer, pyqtSlot, pyqtSignal, Qt
from PyQt5.QtWidgets import QDialog, QApplication, QPushButton, QVBoxLayout, QMessageBox, QHBoxLayout,QLabel

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as mpl

from astropy.visualization import (PercentileInterval, LinearStretch,
                                    ImageNormalize, ZScaleInterval)
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits

import WIFISpower as pc
import WIFISmotor as wm
import WIFIStelescope as wg
import WIFISdetector as wd
import WIFISguider as gf
import WIFISastrometry as wa
from WIFIScalibration import CalibrationControl

import traceback
import numpy as np
import get_src_pos
import time
import sys
from pymodbus.client.sync import ModbusSerialClient as ModbusClient  

# Global setting for the motors.
# Default is False due to the currently buggy behaviour of the motor code
# with the GuI code. 
motors = False

class Formatter(object):
    '''Class that formats the mouseover readout for matplotlib plots'''

    def __init__(self, im):
        self.im = im
    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
	return 'x={:.01f}, y={:.01f}, z={:.01f}'.format(x, y, z)

class CustomWIFISToolbar(NavigationToolbar):
    '''Custom matplotlib toolbar that removes some unncessary functions. 
    Ultimately used to save space on the monitor in order to see mouseover'''

    toolitems = [t for t in NavigationToolbar.toolitems if t[0] in ('Home','Back','Forward','Pan','Zoom')]


class PlotWindow(QDialog):
    '''Creates a single plot window. Now depreciated for the double plot window'''

    def __init__(self, title, parent=None):
        super(PlotWindow, self).__init__(parent)
       
        self.setWindowTitle(title)
        self.figure = mpl.figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)

        # set the layout
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.canvas)
        self.setLayout(self.layout)
        self.fullclose = False

    def closeEvent(self, event):
        
        if not self.fullclose:
            reply = QMessageBox.question(self, "Message", \
                    "Close the main window to exit the GUI.\nClosing this window will break plotting.",\
                    QMessageBox.Cancel)
            event.ignore()
        else:
            event.accept()

class DoublePlotWindow(QDialog):
    '''Creates a window with plots for the H2RG and the Guider.
    Simplifies the number of GUI windows'''

    def __init__(self, title, parent=None):
        super(DoublePlotWindow, self).__init__(parent)
       
        # Define the windows and figures
        self.setWindowTitle(title)
        self.objfigure = mpl.figure()
        self.objcanvas = FigureCanvas(self.objfigure)
        #self.objtoolbar = NavigationToolbar(self.objcanvas, self)
        self.objtoolbar = CustomWIFISToolbar(self.objcanvas, self)
        self.guidefigure = mpl.figure()
        self.guidecanvas = FigureCanvas(self.guidefigure)
        #self.guidetoolbar = NavigationToolbar(self.guidecanvas, self)
        self.guidetoolbar = CustomWIFISToolbar(self.guidecanvas, self)
        self.ObjPlotLabel = QLabel()
        self.ObjPlotLabel.setText("Detector Plot")
        self.GuidePlotLabel = QLabel()
        self.GuidePlotLabel.setText("Guider Plot")

        self.objtoolbar.setStyleSheet("QToolBar { border: 0px }")
        self.guidetoolbar.setStyleSheet("QToolBar { border: 0px }")

        # set the layout
        self.layout = QVBoxLayout()
        self.objtoolbarlayout = QHBoxLayout()
        self.guidetoolbarlayout = QHBoxLayout()

        # Add the various components
        self.layout.addLayout(self.objtoolbarlayout)
        self.objtoolbarlayout.addWidget(self.objtoolbar)
        self.objtoolbarlayout.addWidget(self.ObjPlotLabel)
        self.layout.addWidget(self.objcanvas)
        self.layout.addLayout(self.guidetoolbarlayout)
        self.guidetoolbarlayout.addWidget(self.guidetoolbar)
        self.guidetoolbarlayout.addWidget(self.GuidePlotLabel)
        #self.layout.addWidget(self.guidetoolbar)
        self.layout.addWidget(self.guidecanvas)

        # Create the window
        screen = QDesktopWidget().screenGeometry()
        self.setGeometry(0,0,screen.width()/2.5, screen.height()-60)

        self.setLayout(self.layout)
        self.fullclose = False

    def closeEvent(self, event):
        
        if not self.fullclose:
            reply = QMessageBox.question(self, "Message",\
                    "Close the main window to exit the GUI.\nClosing this window will break plotting.",\
                    QMessageBox.Cancel)

            event.ignore()
        else:
            event.accept()

class WIFISUI(QMainWindow, Ui_MainWindow):
    '''WIFIS Control Software Primary GUI Program.
    '''

    def __init__(self):
        super(WIFISUI, self).__init__()

        # Load all of the GUI elements
        self.setupUi(self)

        #Create the plotting windows
        #self.plotwindow = PlotWindow('WIFIS Plot Window')
        #self.plotwindow.show()
        #self.guideplotwindow = PlotWindow('Guider Plot Window')
        #self.guideplotwindow.show()

        # Create the double plot window.
        self.plotwindow = DoublePlotWindow("WIFIS Plot Window")
        self.plotwindow.show()

        # Read in the previous guide offset values and update the gui forms
        self.guidevals = self.read_defaults()
        self.GuideRA.setText(self.guidevals['GuideRA'])
        self.GuideDEC.setText(self.guidevals['GuideDEC'])

        # Set some default flags and values
        self.detector_in_use = False
        self.labelsThread = False
        self.motoraction = False
        self.targetsloaded = False
        self.expbaron = False
        # Flag for update thread
        self.updateon = False

        self.coords = [self.RALabel, self.DECLabel]

        # Defining GUI Variables to feed into the different control classes
        # Important that the classes only read the variables and never try to adjust them.
        self.guide_widgets = [self.RAMoveBox, self.DECMoveBox, self.FocStep, self.ExpType,\
                self.ExpTime, self.ObjText, self.SetTempValue, self.FilterVal, self.XPos, \
                self.YPos,self.IISLabel, self.coords]
        self.power_widgets = [self.Power11, self.Power12, self.Power13, self.Power14, self.Power15,\
                        self.Power16, self.Power17, self.Power18, self.Power21, self.Power22,\
                        self.Power23, self.Power24, self.Power25, self.Power26, self.Power27,\
                        self.Power28]
        self.caliblabels = [self.CalibModeButton,self.ObsModeButton,\
                self.ArclampModeButton,self.ISphereModeButton]
        self.textlabels = [self.ObjText, self.RAObj, self.DECObj, self.NodRAText, self.NodDecText]
        # Update other forms with saved values from the last execution
        self.readLabels()

        # Set the main tab widget to the first page (Telescope Control)
        self.WIFISTabWidget.setCurrentIndex(0)

        # Connect the give separate WIFIS components in order. 
        self.connectTelescopeAction()
        self.connectPowerAction()
        self.connectCalibAction()
        self.connectGuiderAction()
        self.connectH2RGAction()

        #Connecting to Motor Controller
        #/// Currently disabled due to unknown crashes caused by the Motor Serial connection
        if motors:
            self.motorcontrol = wm.MotorControl()
            self.motorcontrol.updateText.connect(self._handleMotorText)

            self.MotorsEnabledLabel.setText("Enabled")
            self.MotorsEnabledLabel.setAlignment(Qt.AlignCenter)
            self.MotorsEnabledLabel.setStyleSheet("QLabel {background-color: green;}")
        else:
            self.motorcontrol = None

            self.MotorsEnabledLabel.setText("Disabled")
            self.MotorsEnabledLabel.setAlignment(Qt.AlignCenter)
            self.MotorsEnabledLabel.setStyleSheet("QLabel {background-color: red;}")

        # Iniializae telemetry label update thread
        if self.telescope:
            updatevals = [self.RAObj, self.DECObj]
            self.labelsThread = UpdateLabels(self.guider, self.guideron, updatevals,\
                    self.EnableForceIIS, self.ForceIISEntry, self.textlabels)
            self.labelsThread.updateText.connect(self._handleUpdateLabels)
            self.labelsThread.start()
            self.updateon = True
        
        # Defining settings for exposure progress bar
        self.ExpProgressBar.setMinimum(0)
        self.ExpProgressBar.setMaximum(100)
        self.ExpProgressBar.setValue(0)
        
        ### Connecting GUI elements to the various functions

        # Connecting functions for Exposure Control
        if self.scideton and not self.scidet.connected:
            self.DetectorStatusLabel.setStyleSheet('color: red')
        #Detector control functions that don't reference the detector
        self.ExposureButton.clicked.connect(self.initExposure)
        self.TakeCalibButton.clicked.connect(self.initCalibExposure)
        self.NodBeginButton.clicked.connect(self.checkStartNodding)
        self.CenteringCheck.clicked.connect(self.checkcentering)
        self.CheckResolution.clicked.connect(self.arcWidthMap)

        # Connecting Guider Control functions that don't require the guider class
        self.SaveImageButton.clicked.connect(self.initGuideExposureSave)
        self.TakeImageButton.clicked.connect(self.initGuideExposure)
        self.FocusCameraButton.clicked.connect(self.focusCamera) 
        self.StartGuidingButton.clicked.connect(self.startGuiding)

        #Defining actions for Motor Control IF ENABLED
        if motors:
            self.FocusGoTo.clicked.connect(self.motorcontrol.m1_step)
            self.FilterGoTo.clicked.connect(self.motorcontrol.m2_step)
            self.GratingGoTo.clicked.connect(self.motorcontrol.m3_step)
            self.FocusHome.clicked.connect(self.motorcontrol.m1_home)
            self.FilterHome.clicked.connect(self.motorcontrol.m2_home)
            self.GratingHome.clicked.connect(self.motorcontrol.m3_home)
            self.FocusStop.clicked.connect(self.motorcontrol.m1_stop)
            self.FilterStop.clicked.connect(self.motorcontrol.m2_stop)
            self.GratingStop.clicked.connect(self.motorcontrol.m3_stop)
            #self.TBButton.clicked.connect(self.motorcontrol.gotoTB)
            #self.HButton.clicked.connect(self.motorcontrol.gotoH)
            #self.BlankButton.clicked.connect(self.motorcontrol.gotoBlank)
            self.TBButton.setEnabled(False)
            self.HButton.setEnabled(False)
            self.BlankButton.setEnabled(False)

        # Connecting other functions to GUI elements
        self.SkyCheckBox.stateChanged.connect(self.skybuttonchanged)
        self.actionQuit.triggered.connect(self.close)
        
        self.ConnectGuider.triggered.connect(self.connectGuiderAction)
        self.ConnectCalib.triggered.connect(self.connectCalibAction)
        self.ConnectPower.triggered.connect(self.connectPowerAction)
        self.ConnectH2RG.triggered.connect(self.connectH2RGAction)
        self.ConnectTelescope.triggered.connect(self.connectTelescopeAction)
        self.ConnectAll.triggered.connect(self.connectAllAction)
        self.ConnectMotors.triggered.connect(self.connectMotorAction)
        
        self.SetNextButton.clicked.connect(self.setNextRADEC)
        self.MoveNextButton.clicked.connect(self.moveNext)

        self.LoadTargetsAction.triggered.connect(self.loadTargetList)
        self.ResetExposureFlagButton.clicked.connect(self.resetExposureFlag)
        self.SetGuideOffset.clicked.connect(self.setGuideOffset)

        # Load guider bias frame to remove from images
        guidebiasff = fits.open('/home/utopea/elliot/20190418T073052_Bias.fits')
        self.guidebias = guidebiasff[0].data
        self.guidebias = self.guidebias.astype('float')

    def read_defaults(self):
        '''Loads the default or saved values for some of the GUI entry forms'''

        # Opens the file and reads the variable and value into a dictionary
        f = open('/home/utopea/WIFIS-Team/wifiscontrol/defaultvalues.txt','r')
        valuesdict = {}
        for line in f:
            spl = line.split()
            valuesdict[spl[0]] = spl[1]
        f.close()

        # Returns the dict
        return valuesdict

    def loadTargetList(self):
        '''Loads the targets defined in the target list file. The targets are loaded
        as buttons in the Target List Menu'''

        tarlistfile = '/home/utopea/WIFIS-Team/wifiscontrol/targetlist.txt'
        self.tars = np.loadtxt(tarlistfile, dtype=str)
    
        if self.targetsloaded:
            for act in self.taractions:
                self.menuTarget_List.removeAction(act)

        self.taractions = []
        for i in range(len(self.tars)):
            act = self.menuTarget_List.addAction(self.tars[i][0])
            act.triggered.connect(lambda checked, val=i: self.enterTargetInfo(val))
            self.taractions.append(act)


        self.targetsloaded = True

    def enterTargetInfo(self, i):
        '''Takes the loaded Name, RA, and DEC from the loaded target info
        and places it in their respective text boxes'''

        self.ObjText.setText(self.tars[i][0])
        self.RAObj.setText(self.tars[i][1])
        self.DECObj.setText(self.tars[i][2])

    def setGuideOffset(self):
        '''Function that handles setting new guider offsets'''

        self._handleOutputTextUpdate('SETTING NEW GUIDE OFFSETS...')
        coord = SkyCoord(self.RALabel.text(), self.DECLabel.text(), unit=(u.hourangle, u.deg))
        dec_deg = coord.dec.deg

        #self.guidevals['DEC'] = str(dec_deg)
        self.guidevals['GuideRA'] = self.GuideRA.text() #str(float(self.GuideRA.text()) / np.cos(dec_deg * np.pi / 180.))
        self.guidevals['GuideDEC'] = self.GuideDEC.text()

        # Save the new offsets to file. 
        fl = open('/home/utopea/WIFIS-Team/wifiscontrol/defaultvalues.txt','w')
        for key, val in self.guidevals.iteritems():
            fl.write('%s\t\t%s\n' % (key, val))
        fl.close()
        self._handleOutputTextUpdate('NEW GUIDE OFFSETS SET')
        
    def connectGuiderAction(self):
        '''Function that connects to the WIFIS Guider Camera'''

        #Connecting to Guider
        try:
            #Guider Control and Threads
            self.guider = gf.WIFISGuider(self.guide_widgets)
            self.guider.updateText.connect(self._handleGuidingTextUpdate)
            self.guider.plotSignal.connect(self._handleGuidePlotting)
            self.guider.astrometryCalc.connect(self._handleAstrometryCalc)
            self.guideron = True
        except:
            print "### can't connect to guider -- something failed"
            self._handleOutputTextUpdate("### can't connect to guider -- something failed")

            self.guideron = False

        if not self.guider.guiderready:
            print "### Can't connect to one or all of the guider components"
            print "FOC: ",self.guider.foc
            print "CAM: ",self.guider.cam
            print "FLT: ",self.guider.flt
            self.guideron = False
            self.guiderToggle(False)
        else:
            self.guiderToggle(True)
            self.guiderSwitch()
            print "### Connected to Guider"

    def guiderSwitch(self):
        '''Connects all the guider elements to the proper functions'''

        if self.guideron:
            self.BKWButton.clicked.connect(self.guider.stepBackward)
            self.FWDButton.clicked.connect(self.guider.stepForward)
            self.CentroidButton.clicked.connect(self.guider.checkCentroids)
            self.SetTempButton.clicked.connect(self.guider.setTemperature)
            #self.doAstrometryButton.clicked.connect(self.guider.doAstrometry)
            self.doAstrometryButton.clicked.connect(self.doAstrometry)
            self.FilterVal.currentIndexChanged.connect(self.guider.goToFilter)

        if self.telescope:
            self.GuiderMoveButton.clicked.connect(self.guider.offsetToGuider)
            self.WIFISMoveButton.clicked.connect(self.guider.offsetToWIFIS)
            self.moveTelescopeButton.clicked.connect(self.guider.moveTelescope)
            self.MoveBackButton.clicked.connect(self.guider.moveTelescopeBack)
            self.CalOffsetButton.clicked.connect(self.guider.calcOffset)

    def guiderToggle(self, on):

        if on:
            s = ''
            en = True
            self.ConnectGuider.setText('Guider - O')
        else:
            s = 'background-color: red'
            en = False
            self.ConnectGuider.setText('Guider - X')

        self.BKWButton.setStyleSheet(s)
        self.FWDButton.setStyleSheet(s)
        self.SaveImageButton.setStyleSheet(s)
        self.TakeImageButton.setStyleSheet(s)
        self.FocusCameraButton.setStyleSheet(s)
        self.StartGuidingButton.setStyleSheet(s)
        self.CentroidButton.setStyleSheet(s)
        self.SetTempButton.setStyleSheet(s)
        self.StopGuidingButton.setStyleSheet(s)
        self.doAstrometryButton.setStyleSheet(s)

        self.BKWButton.setEnabled(en)
        self.FWDButton.setEnabled(en)
        self.SaveImageButton.setEnabled(en)
        self.TakeImageButton.setEnabled(en)
        self.FocusCameraButton.setEnabled(en)
        self.StartGuidingButton.setEnabled(en)
        self.CentroidButton.setEnabled(en)
        self.SetTempButton.setEnabled(en)
        self.FilterVal.setEnabled(en)
        self.StopGuidingButton.setEnabled(en)
        self.doAstrometryButton.setEnabled(en)

    def connectCalibAction(self):
        if self.poweron:
            try:
                #Calibration Control
                self.calibrationcontrol = CalibrationControl(self.switch1, self.switch2, self.caliblabels)
                self.calibon = True

                self.calibToggle(True)
                self.calibrationcontrol.checkStatus1()
                self.calibrationcontrol.checkStatus2()

                self.calibSwitch()
                print "### Connected to Calibration Unit"

            except Exception as e:
                print "### Can't connect to Calibraiton Unit -- Something Failed"
                print e
                self.calibon = False
                self.calibrationcontrol = None
                self.calibToggle(False)
                
        else:
            print "### Can't connect to Calibraiton Unit -- No Power Connection"
            self.calibon = False
            self.calibrationcontrol = None

            self.calibToggle(False)

    def calibSwitch(self):
        '''Connects all the calibration elements to the proper functions'''

        if self.calibon:
            self.CalibModeButton.clicked.connect(self.calibrationcontrol.flip2pos2)
            self.ObsModeButton.clicked.connect(self.calibrationcontrol.flip2pos1)
            self.ArclampModeButton.clicked.connect(self.calibrationcontrol.flip1pos2)
            self.ISphereModeButton.clicked.connect(self.calibrationcontrol.flip1pos1)
            
    def calibToggle(self, status):
        if status:
            s = ''
            val = True
            self.ConnectCalib.setText('Calib Unit - O')
        else:
            s = 'background-color: red'
            val = False
            self.ConnectCalib.setText('Calib Unit - X')

        self.CalibModeButton.setStyleSheet(s)
        self.ObsModeButton.setStyleSheet(s)
        self.ArclampModeButton.setStyleSheet(s)
        self.ISphereModeButton.setStyleSheet(s)
        self.TakeCalibButton.setStyleSheet(s)

        self.CalibModeButton.setEnabled(val)
        self.ObsModeButton.setEnabled(val)
        self.ArclampModeButton.setEnabled(val)
        self.ISphereModeButton.setEnabled(val)
        self.TakeCalibButton.setEnabled(val)
        self.ExpTypeSelect.model().item(3).setEnabled(val)
        self.ExpTypeSelect.model().item(4).setEnabled(val)

    def connectPowerAction(self):
        try:
            #Power Control
            self.powercontrol = pc.PowerControl(self.power_widgets)
            self.switch1 = self.powercontrol.switch1
            self.switch2 = self.powercontrol.switch2
            self.poweron = True
            self.ConnectPower.setText('Power - O')

            self.powercontrol.powerStatusUpdate()
            if self.switch1.verify() == True:
                val1 = True
            else:
                val1 = False

            if self.switch2.verify() == True:
                val2 = True
            else:
                val2 = False

            self.powerToggle(True, val1, val2)

            
            self.powerSwitch()
            if (val1 == False) and (val2 == False):
                print "### Can't connect to Power Controllers -- Something Failed"
            elif (val1 == False) and (val2 == True):
                print "### Can't connect to Power Controller 1 -- Something Failed"
            elif (val1 == True) and (val2 == False):
                print "### Can't connect to Power Controller 2 -- Something Failed"
            else:
                print "###Connected to Power Controllers"

        except Exception as e:
            print "### Can't connect to Power Controllers -- Something Failed"
            print e
            print traceback.print_exc()
            self.poweron = False
            self.ConnectPower.setText('Power - X')
            self.powerToggle(False, False, False)

    def powerSwitch(self):
        '''Connects all the Power elements to the proper functions'''

        if self.poweron:
            self.Power11.clicked.connect(self.powercontrol.toggle_plug9)
            self.Power12.clicked.connect(self.powercontrol.toggle_plug10)
            self.Power13.clicked.connect(self.powercontrol.toggle_plug11)
            self.Power14.clicked.connect(self.powercontrol.toggle_plug12)
            self.Power15.clicked.connect(self.powercontrol.toggle_plug13)
            self.Power16.clicked.connect(self.powercontrol.toggle_plug14)
            self.Power17.clicked.connect(self.powercontrol.toggle_plug15)
            self.Power18.clicked.connect(self.powercontrol.toggle_plug16)
            self.Power21.clicked.connect(self.powercontrol.toggle_plug1)
            self.Power22.clicked.connect(self.powercontrol.toggle_plug2)
            self.Power23.clicked.connect(self.powercontrol.toggle_plug3)
            self.Power24.clicked.connect(self.powercontrol.toggle_plug4)
            self.Power25.clicked.connect(self.powercontrol.toggle_plug5)
            self.Power26.clicked.connect(self.powercontrol.toggle_plug6)
            self.Power27.clicked.connect(self.powercontrol.toggle_plug7)
            self.Power28.clicked.connect(self.powercontrol.toggle_plug8)


    def powerToggle(self, status, switch1, switch2):
        if status: 
            if switch1:
                val1 = True
            else:
                val1 = False

            if switch2:
                val2 = True
            else:
                val2 = False
        else:
            self.Power11.setStyleSheet('background-color: red')
            self.Power12.setStyleSheet('background-color: red')
            self.Power13.setStyleSheet('background-color: red')
            self.Power14.setStyleSheet('background-color: red')
            self.Power15.setStyleSheet('background-color: red')
            self.Power16.setStyleSheet('background-color: red')
            self.Power17.setStyleSheet('background-color: red')
            self.Power18.setStyleSheet('background-color: red')
            self.Power21.setStyleSheet('background-color: red')
            self.Power22.setStyleSheet('background-color: red')
            self.Power23.setStyleSheet('background-color: red')
            self.Power24.setStyleSheet('background-color: red')
            self.Power25.setStyleSheet('background-color: red')
            self.Power26.setStyleSheet('background-color: red')
            self.Power27.setStyleSheet('background-color: red')
            self.Power28.setStyleSheet('background-color: red')

            val1 = False
            val2 = False

        self.Power11.setEnabled(val1)
        self.Power12.setEnabled(val1)
        self.Power13.setEnabled(val1)
        self.Power14.setEnabled(val1)
        self.Power15.setEnabled(val1)
        self.Power16.setEnabled(val1)
        self.Power17.setEnabled(val1)
        self.Power18.setEnabled(val1)
        self.Power21.setEnabled(val2)
        self.Power22.setEnabled(val2)
        self.Power23.setEnabled(val2)
        self.Power24.setEnabled(val2)
        self.Power25.setEnabled(val2)
        self.Power26.setEnabled(val2)
        self.Power27.setEnabled(val2)
        self.Power28.setEnabled(val2)

    def checkPowerStatus(self):

        #H2RG requires switch1[5]
        #Motors require switch1[2]
        #Guider requires switch2[3,5,6,7]
        #Calib unit requires switch2[3]
        #If any of these are toggled, lock out the controls.
        if self.switch1:
            if self.switch1[5].state == 'OFF':
                self.H2RGToggle(False)
        else:
            self.H2RGToggle(False)
        
        if self.switch2:

            if (self.switch2[3].state == 'OFF') or (self.switch2[5].state == 'OFF') or \
                    (self.switch2[6].state == 'OFF') or (self.switch2[7].state == 'OFF'):
                self.guiderToggle(False)
            if self.switch2[3].state == 'OFF':
                self.calibToggle(False)
        else:
            self.guiderToggle(False)
            self.calibToggle(False)
    
    def connectTelescopeAction(self):
        #Connect to telescope
        try:
            self.telsock = wg.connect_to_telescope()
            telemDict = wg.get_telemetry(self.telsock, verbose=False)
            if self.EnableForceIIS.isChecked():
                if self.ForceIISEntry.text() != '':
                    try:
                        float(self.ForceIISEntry.text())
                        self.IISLabel.setText(self.ForceIISEntry.text())
                    except:
                        self._handleOutputTextUpdate('### FORCED IIS NOT A FLOAT')
                        self.IISLabel.setText(telemDict['IIS']) 
            else:
                #Set IIS early because certain functions rely on this value
                self.IISLabel.setText(telemDict['IIS']) 

            self.telescope = True

            self.telescopeToggle(True)

            print "### Connected to Telescope"

        except Exception as e:
            print "### Can't connect to telescope -- Something Failed"
            print e
            print traceback.print_exc()
            self.telescope = False
            self.telescopeToggle(False)

    def telescopeToggle(self, status):
        if status:
            s = ''
            val = True
            self.ConnectTelescope.setText('Telescope - O')
        else:
            s = 'background-color: red'
            val = False
            self.ConnectTelescope.setText('Telescope - X')

        self.GuiderMoveButton.setStyleSheet(s)
        self.WIFISMoveButton.setStyleSheet(s)
        self.moveTelescopeButton.setStyleSheet(s)
        self.MoveBackButton.setStyleSheet(s)
        self.CalOffsetButton.setStyleSheet(s)
        self.SetNextButton.setStyleSheet(s)
        self.MoveNextButton.setStyleSheet(s)

        self.GuiderMoveButton.setEnabled(val)
        self.WIFISMoveButton.setEnabled(val)
        self.moveTelescopeButton.setEnabled(val)
        self.MoveBackButton.setEnabled(val)
        self.CalOffsetButton.setEnabled(val)
        self.SetNextButton.setEnabled(val)
        self.MoveNextButton.setEnabled(val)

    def connectH2RGAction(self):
        #Connecting to Detector
        if self.poweron:
            try:
                #Detector Control and Threads
                self.scidet = wd.h2rg(self.DetectorStatusLabel, self.switch1, self.switch2,\
                        self.calibrationcontrol)
                self.scidet.updateText.connect(self._handleOutputTextUpdate)
                self.scidet.plotSignal.connect(self._handlePlotting)

                if self.scidet.scideton:
                    self.scideton = True
                    self.H2RGToggle(True)
                    self.scidetSwitch()
                    print "### Connected to Science Array"
                else:
                    self.scideton = False
                    print "### Can't Connect to Science Array -- Something Failed"
                    print e
                    print traceback.print_exc()
                    self.H2RGToggle(False)
            except Exception as e:
                self.scideton = False
                print "### Can't Connect to Science Array -- Something Failed"
                print e
                print traceback.print_exc()
                self.H2RGToggle(False)
        else:
            print "### Can't Connect to Science Array -- No Power Connection"
            self.scideton = False
            self.H2RGToggle(False)

    def scidetSwitch(self):
        '''Connects all the detector functions to the proper functions'''

        if self.scideton:
            self.actionConnect.triggered.connect(self.scidet.connect)
            self.actionInitialize.triggered.connect(self.scidet.initialize)
            self.actionDisconnect.triggered.connect(self.scidet.disconnect)
            self.scidet.connect()

    def H2RGToggle(self, status):
        if status:
            s = ''
            val = True
            self.ConnectH2RG.setText('H2RG - O')
        else:
            s = 'background-color: red'
            val = False
            self.ConnectH2RG.setText('H2RG - X')

        self.ExposureButton.setStyleSheet(s)
        self.TakeCalibButton.setStyleSheet(s)
        self.NodBeginButton.setStyleSheet(s)
        self.CenteringCheck.setStyleSheet(s)
        self.ExposureButton.setEnabled(val)
        self.TakeCalibButton.setEnabled(val)
        self.NodBeginButton.setEnabled(val)
        self.CenteringCheck.setEnabled(val)

    def connectAllAction(self):

        if not self.telescope:
            self.connectTelescopeAction()
        if not self.poweron:
            self.connectPowerAction()
        if not self.scideton:
            self.connectH2RGAction()
        if not self.calibon:
            self.connectCalibAction()
        if not self.guideron:
            self.connectGuiderAction()

    def initGuideExposure(self):
        self.guideexp = gf.ExposeGuider(self.guider, False)
        self.guideexp.start()

    def initGuideExposureSave(self):
        self.guideexp = gf.ExposeGuider(self.guider, True)
        self.guideexp.start()

    def startGuiding(self):
        self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel, \
                self.GuiderExpTime.text(), self.OverGuideStar, self.coords)
        self.guideThread.updateText.connect(self._handleGuidingTextUpdate)
        self.guideThread.plotSignal.connect(self._handleGuidingPlotting)
        self.guideThread.setSkySignal.connect(self._handleGuidingSky)
        self.StopGuidingButton.clicked.connect(self.guideThread.stop)
        self.guideThread.start()

    def focusCamera(self):
        self.fcthread = gf.FocusCamera(self.guider.cam, self.guider.foc, self.ExpTime)
        self.fcthread.plotSignal.connect(self._handleGuidingPlotting)
        self.fcthread.updateText.connect(self._handleGuidingTextUpdate)
        self.fcthread.start()

    def skybuttonchanged(self):
        objtxt = self.ObjText.text()
        if self.SkyCheckBox.isChecked():
            self.ObjText.setText(objtxt+'Sky')
        else:
            if objtxt[-3:] == 'Sky':
                self.ObjText.setText(objtxt[:-3])

    def moveNext(self):
        reply = QMessageBox.question(self, "Message", \
                "Are you sure you want to move to Next?\nOnly use this for minor moves.", \
                QMessageBox.Yes | QMessageBox.Cancel)

        if reply == QMessageBox.Yes:
            wg.move_next(self.telsock)
            self._handleGuidingTextUpdate("### MOVING TELESCOPE TO NEXT")

    def _handleOutputTextUpdate(self, txt):
        self.OutputText.append(txt)
        #else:
        #    return

    def setNextRADEC(self):

        RAText = self.RAObj.text()
        DECText = self.DECObj.text()

        RA, DEC = parseRADECText(RAText, DECText)
        if RA == False:
            self._handleOutputTextUpdate(DEC)
            return

        RAText = float(RAText)
        DECText = float(DECText)
        RAText = '%.1f' % (RAText)
        DECText = '%.1f' % (DECText)
     
        return1 = wg.set_next_radec(self.telsock,RAText,DECText)
        self._handleOutputTextUpdate(return1)

    def resetExposureFlag(self):
        self.detector_in_use = False

    def initExposure(self):

        if self.detector_in_use == True:
            self._handleOutputTextUpdate('CANT EXPOSE, DETECTOR CURRENTLY IN USE!')
            self._handleOutputTextUpdate('If this is false, reset the detector flag in the Other tab')
            return

        nreads = int(round(int(self.NReadsText.text()) / 1.5))
        if nreads < 2:
            self._handleOutputTextUpdate('Exposure time must be at least 3 seconds')
            return

        self.scidetexpose = wd.h2rgExposeThread(self.scidet, self.ExpTypeSelect.currentText(),\
                nreads=nreads,nramps=int(self.NRampsText.text()),\
                sourceName=self.ObjText.text())
        self.scidetexpose.updateText.connect(self._handleOutputTextUpdate)
        self.scidetexpose.finished.connect(self._handleExpFinished)
        self.scidetexpose.startProgBar.connect(self._startProgBar)
        self.scidetexpose.endProgBar.connect(self._endProgBar)
        self.scidetexpose.started.connect(self._handleExpStarted)
        self.scidetexpose.start()

    def _startProgBar(self):
        self.progbar = wd.h2rgProgressThread(self.ExpTypeSelect.currentText(),\
                nreads=int(self.NReadsText.text()),nramps=int(self.NRampsText.text()))
        self.progbar.updateBar.connect(self._handleProgressBar)
        self.progbar.finished.connect(self._endProgBar)
        self.progbar.start()

    def _endProgBar(self):
        try:
            self.progbar.finish = True
        except Exception as e:
            print e
            self._handleOutputTextUpdate('Something went wrong with finishing prog bar')
        self.ExpProgressBar.setValue(0)

    def _startCalibProgBar(self):
        self.progbar = wd.h2rgProgressThread('Ramp',nreads=55,nramps=1)
        self.progbar.updateBar.connect(self._handleProgressBar)
        self.progbar.finished.connect(self._endProgBar)
        self.progbar.start()

    def initCalibExposure(self):

        if self.detector_in_use == True:
            self._handleOutputTextUpdate('CANT EXPOSE, DETECTOR CURRENTLY IN USE!')
            self._handleOutputTextUpdate('If this is false, reset the detector flag in the Other tab')
            return

        nreads = int(round(int(self.NReadsText.text()) / 1.5))

        self.calibexpose = wd.h2rgExposeThread(self.scidet, "Calibrations",\
                nreads=nreads,nramps=int(self.NRampsText.text()),\
                sourceName=self.ObjText.text())
        self.calibexpose.updateText.connect(self._handleOutputTextUpdate)
        self.calibexpose.startProgBar.connect(self._startCalibProgBar)
        self.calibexpose.started.connect(self._handleExpStarted)
        self.calibexpose.finished.connect(self._handleExpFinished)
        self.calibexpose.start()

    def checkStartNodding(self):
        choice = QMessageBox.question(self,\
                'Nodding Sequence',\
                "Start Nodding Sequence?\nReads and Sky Coords Set?",\
                QMessageBox.Yes | QMessageBox.No)
        if choice == QMessageBox.Yes:
            self.startNodding()
        else:
            pass

    def startNodding(self):

        if self.detector_in_use == True:
            self._handleOutputTextUpdate('CANT EXPOSE, DETECTOR CURRENTLY IN USE!')
            self._handleOutputTextUpdate('If this is false, reset the detector flag in the Other tab')
            return

        self.noddingexposure = NoddingExposure(self.scidet, self.guider, self.NodSelection, \
                self.NNods, self.NodsPerCal, self.NRampsText, self.NReadsText, \
                self.ObjText, self.NodRAText, self.NodDecText, self.SkipCalib,\
                self.OffsetNod, self.RADECNod, self.RAObj, self.DECObj)
        self.noddingexposure.updateText.connect(self._handleOutputTextUpdate)
        self.noddingexposure.startGuiding.connect(self._handleNoddingGuide)
        self.noddingexposure.stopGuiding.connect(self._handleNoddingGuideStop)
        self.noddingexposure.started.connect(self._handleNoddingStarted)
        self.noddingexposure.finished.connect(self._handleNoddingFinished)
        self.StopExpButton.clicked.connect(self.noddingexposure.stop)
        self.noddingexposure.progBar.connect(self._handleNoddingProgBar)

        self.noddingexposure.start()

    def _handleNoddingStarted(self):
        self.detector_in_use = True

    def _handleNoddingFinished(self):
        self.detector_in_use = False

    def _handleNoddingProgBar(self, nreads, nramps):

        self.progbar = wd.h2rgProgressThread('Ramp',nreads=nreads,nramps=nramps)
        self.progbar.updateBar.connect(self._handleProgressBar)
        self.progbar.finished.connect(self._endProgBar)
        self.progbar.start()

    def _handleNoddingGuide(self, s):
        if s == 'Sky':
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel, \
                    self.GuiderExpTime.text(), self.OverGuideStar, self.coords, sky=True)
        else:
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel, \
                    self.GuiderExpTime.text(), self.OverGuideStar, self.coords, sky=False)
        self.guideThread.updateText.connect(self._handleGuidingTextUpdate)
        self.guideThread.plotSignal.connect(self._handleGuidingPlotting)
        self.guideThread.setSkySignal.connect(self._handleGuidingSky)
        self.guideThread.endNodding.connect(self._endNodding)
        self.StopGuidingButton.clicked.connect(self.guideThread.stop)
        self.guideThread.start()

    def _endNodding(self, b):
        self.noddingexposure.stop()

    def _handleNoddingGuideStop(self):
        self.guideThread.stop()

    def _handleGuidingSky(self, s):
        if s == 'True':
            self.ObjText.setText(self.ObjText.text() + 'Sky')
        elif s == 'False':
            self.ObjText.setText(self.ObjText.text()[:-3])

    def _handleOutputTextUpdate(self, txt):
        self.OutputText.append(txt)

    def _handleGuidingTextUpdate(self, txt):
        self.GuidingText.append(txt)

    def _handleProgressBar(self, i):
        self.ExpProgressBar.setValue(i)

    def _handleExpStarted(self):
        self.detector_in_use = True

    def _handleExpFinished(self):
        self.detector_in_use = False

    def _handleUpdateLabels(self, labelupdates):
        telemDict,steppos,ccdtemp = labelupdates

        self.head = telemDict
        DECText = telemDict['DEC']
        RAText = telemDict['RA']

        self.RALabel.setText(RAText[0:2]+':'+RAText[2:4]+':'+RAText[4:])
        self.DECLabel.setText(DECText[0:3]+':'+DECText[3:5]+':'+DECText[5:])
        self.AZLabel.setText(telemDict['AZ'])
        self.ELLabel.setText(telemDict['EL'])
        #self.IISLabel.setText(telemDict['IIS'])
        if self.EnableForceIIS.isChecked():
            if self.ForceIISEntry.text() != '':
                try:
                    float(self.ForceIISEntry.text())
                    self.IISLabel.setText(self.ForceIISEntry.text())
                except:
                    self._handleOutputTextUpdate('### FORCED IIS NOT A FLOAT')
                    self.IISLabel.setText(telemDict['IIS']) 
        else:
            #Set IIS early because certain functions rely on this value
            self.IISLabel.setText(telemDict['IIS']) 
        self.HALabel.setText(telemDict['HA'])
        self.FocPosition.setText(steppos)
        self.CCDTemp.setText(ccdtemp)

    def checkcentering(self):
        fieldrecObj = get_src_pos.get_src_pos('/home/utopea/WIFIS-Team/wifiscontrol/wave.lst','/home/utopea/WIFIS-Team/wifiscontrol/flat.lst',\
                '/home/utopea/WIFIS-Team/wifiscontrol/obs.lst')
        fieldrecObj.plotField.connect(self._handleFRPlotting)
        fieldrecObj.doFieldRec()


        #Old implementation without classes
        #do_get_src_pos('/home/utopea/WIFIS-Team/wifiscontrol/wave.lst','/home/utopea/WIFIS-Team/wifiscontrol/flat.lst',\
        #        '/home/utopea/WIFIS-Team/wifiscontrol/obs.lst')

    def arcWidthMap(self):
        arcwidthObj = get_src_pos.arc_width_map('/home/utopea/WIFIS-Team/wifiscontrol/wave.lst','/home/utopea/WIFIS-Team/wifiscontrol/flat.lst')
        arcwidthObj.plotField.connect(self._handleArcPlotting)
        arcwidthObj.get_arc_map()

    def _handleArcPlotting(self, returns):
        fwhmMap, fwhmMed, waveMin, waveMax = returns

        try:
            print('Plotting Arc Data')
            self.plotwindow.objfigure.clear()
            ax = self.plotwindow.objfigure.add_subplot(111)

            interval=ZScaleInterval()
            lims=interval.get_limits(fwhmMap)

            im = ax.imshow(fwhmMap, aspect='auto', cmap='jet', clim=lims, origin='lower')
            self.plotwindow.objfigure.colorbar(im)
            self.plotwindow.objfigure.tight_layout()

            ax.set_title('Median FWHM is '+'{:3.1f}'.format(fwhmMed) +', min wave is '+'{:6.1f}'.format(waveMin)+', max wave is '+'{:6.1f}'.format(waveMax))

            self.plotwindow.objcanvas.draw()

        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE ARC PLOTTING")


    def _handlePlotting(self, image, flname):

        try:
            norm = ImageNormalize(image, interval=PercentileInterval(99.5),stretch=LinearStretch())

            self.plotwindow.objfigure.clear()

            ax = self.plotwindow.objfigure.add_subplot(1,1,1)
            im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
            ax.format_coord = Formatter(im)
            ax.set_title(flname)
            self.plotwindow.objfigure.colorbar(im)
            self.plotwindow.objfigure.tight_layout()

            self.plotwindow.objcanvas.draw()
        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")

    def _handleGuidePlotting(self, image, flname):
        try:
            image = image.astype('float') - self.guidebias
            norm = ImageNormalize(image, interval=PercentileInterval(98.5),stretch=LinearStretch())

            self.plotwindow.guidefigure.clear()

            ax = self.plotwindow.guidefigure.add_subplot(1,1,1)
            #im = ax.imshow(image, origin='lower', norm=norm, interpolation='none', cmap='gray')
            im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')

            rotAng = float(self.IISLabel.text()) - 90.
            rotMat = np.asarray([[np.cos(rotAng*np.pi/180.),np.sin(rotAng*np.pi/180.)],\
                    [-np.sin(rotAng*np.pi/180.),np.cos(rotAng*np.pi/180.)]])

            decAx = np.dot([-70,0], rotMat)
            raAx = np.dot([0,-70], rotMat)

            cent = np.asarray([150,780])
            ax.arrow(cent[0],cent[1], raAx[0],raAx[1], width = 5,\
                    head_width=15, head_length=15, fc='w', ec='k')
            ax.arrow(cent[0],cent[1], decAx[0],decAx[1], width = 5,\
                    head_width=15, head_length=15, fc='w', ec='k')

            #ax.text((cent+decAx+10)[0]+1, (cent+decAx+10)[1]+1,\
            #        "N",ha="left", va="top", rotation=rotAng, color='w', fontsize=20)
            #ax.text((cent+raAx+10)[0]+1, (cent+raAx+10)[1]+1,\
            #        "E",ha="left", va="bottom", rotation=rotAng, color='w', fontsize=20)
            ax.text((cent+decAx-50)[0], (cent+decAx-10)[1],\
                    "N",ha="left", va="top", rotation=rotAng, color='k', fontsize=17)
            ax.text((cent+raAx+10)[0], (cent+raAx-50)[1],\
                    "E",ha="left", va="bottom", rotation=rotAng, color='k', fontsize=17)
            print cent, decAx, raAx

            ax.format_coord = Formatter(im)
            ax.set_title(flname)
            self.plotwindow.guidefigure.colorbar(im)
            self.plotwindow.guidefigure.tight_layout()

            self.plotwindow.guidecanvas.draw()

        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")

    def _handleGuidingPlotting(self, image, flname):
        try:
            norm = ImageNormalize(image, interval=PercentileInterval(98.5),stretch=LinearStretch())

            self.plotwindow.guidefigure.clear()

            ax = self.plotwindow.guidefigure.add_subplot(1,1,1)
            #im = ax.imshow(image, origin='lower', norm=norm, interpolation='none', cmap='gray')
            im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
            ax.format_coord = Formatter(im)
            ax.set_title(flname)
            self.plotwindow.guidefigure.colorbar(im)
            self.plotwindow.guidefigure.tight_layout()

            self.plotwindow.guidecanvas.draw()

        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")

    def _handleFRPlotting(self, returns):

        try:
            dataImg, WCS, hdr, gFit, xScale, yScale = returns
            
            #Things that are needed for plotting the data
            #WCS, dataImg, hdr

            tarx = gFit.x_mean
            tary = gFit.y_mean

            print(tarx,tary)
            #wcent = WCS.wcs_pix2world(17.5,45,0)
            wcent = WCS.wcs_pix2world(45,17.5,0)
            wtar = WCS.wcs_pix2world(tarx,tary,0)

            skycent = SkyCoord(wcent[0], wcent[1], unit = 'deg')
            skytar = SkyCoord(wtar[0], wtar[1], unit = 'deg')

            centeroffset = skycent.spherical_offsets_to(skytar)
            offsetra = centeroffset[0].arcsec
            offsetdec = centeroffset[1].arcsec

            self._handleGuidingTextUpdate('Target Offset (") to WIFIS Center is:\nRA:\t%.2f\nDEC:\t%.2f\n' % \
                        (offsetra, offsetdec))

            print('Plotting FIELD REC data')
            self.plotwindow.objfigure.clear()
            ax = self.plotwindow.objfigure.add_subplot(111, projection=WCS)

            scaling = 'normal'
            if scaling=='zscale':
                interval=ZScaleInterval()
                lims=interval.get_limits(dataImg)
            else:
                lims=[dataImg.min(),dataImg.max()]
            im = ax.imshow(dataImg, origin='lower', cmap='jet', clim=lims)

            #if colorbar:
            #    plt.colorbar()
            self.plotwindow.objfigure.colorbar(im)
            self.plotwindow.objfigure.tight_layout()
                
            r = np.arange(360)*np.pi/180.
            fwhmX = np.abs(2.3548*gFit.x_stddev*xScale)
            fwhmY = np.abs(2.3548*gFit.y_stddev*yScale)
            x = fwhmX*np.cos(r) + gFit.x_mean
            y = fwhmY*np.sin(r) + gFit.y_mean

            im2 = ax.plot(x,y, 'r--')

            ax.set_ylim([-0.5, dataImg.shape[0]-0.5])
            ax.set_xlim([-0.5, dataImg.shape[1]-0.5])

            rotAng = hdr['CRPA']
            rotMat = np.asarray([[np.cos(rotAng*np.pi/180.),np.sin(rotAng*np.pi/180.)],\
                    [-np.sin(rotAng*np.pi/180.),np.cos(rotAng*np.pi/180.)]])

            raAx = np.dot([5,0], rotMat)
            decAx = np.dot([0,-5], rotMat)

            cent = np.asarray([10,25])
            ax.arrow(cent[0],cent[1], raAx[0],raAx[1], head_width=1, head_length=1, fc='w', ec='w')
            ax.arrow(cent[0],cent[1], decAx[0],decAx[1], head_width=1, head_length=1, fc='w', ec='w')

            ax.text((cent+decAx)[0]+1, (cent+decAx)[1]+1,"N",ha="left", va="top", rotation=rotAng, color='w')
            ax.text((cent+raAx)[0]+1, (cent+raAx)[1]+1,"E",ha="left", va="bottom", rotation=rotAng, color='w')

            ax.set_title(hdr['Object'] + ': FWHM of object is: '+'{:4.2f}'.format(fwhmX)+' in x and ' + '{:4.2f}'.format(fwhmY)+' in y, in arcsec')
            #ax.tight_layout()
            #plt.savefig('quick_reduction/'+rampFolder+'_quickRedImg.png', dpi=300)

            self.plotwindow.objcanvas.draw()
        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")

    def _handleMotorText(self, s, labeltype, motnum):
        
        if labeltype in ['Position', 'Status']:
            if labeltype == 'Position':
                if motnum == 0:
                    self.FocusPosition.setText(s)
                elif motnum == 1:
                    self.FilterPosition.setText(s)
                elif motnum == 2:
                    self.GratingPosition.setText(s)
                    
            if labeltype == 'Status':
                if motnum == 0:
                    self.FocusStatus.setText(s)
                elif motnum == 1:
                    self.FilterStatus.setText(s)
                elif motnum == 2:
                    self.GratingStatus.setText(s)
        else:
            #while self.labelsThread.updatemotors:
            #    pass

            if self.motoraction == True:
                self.OutputText.append("MOTORS BUSY, TRY AGAIN")
                return

            self.motoraction = True

            if labeltype == 'Step':
                if motnum == 0:
                    self.motorcontrol.stepping_operation(self.FocusStep.text(),\
                            unit=0x01)
                elif motnum == 1:
                    self.motorcontrol.stepping_operation(self.FilterStep.text(),\
                            unit=0x02)
                elif motnum == 2:
                    self.motorcontrol.stepping_operation(self.GratingStep.text(),\
                            unit=0x03)

            if (labeltype == 'Step') and (len(s) != 0):
                if motnum == 0:
                    self.motorcontrol.stepping_operation(s, unit=0x01)
                elif motnum == 1:
                    self.motorcontrol.stepping_operation(s, unit=0x02)
                elif motnum == 2:
                    self.motorcontrol.stepping_operation(s, unit=0x03)

           # if labeltype == 'Home':
           #     if motnum == 0:
           #         self.motorcontrol.homing_operation(0x01)
           #     elif motnum == 1:
           #         self.motorcontrol.homing_operation(0x02)
           #     elif motnum == 2:
           #         self.motorcontrol.homing_operation(0x03)

            self.motoraction = False

    def _handleMoveMotor(self, s1, s2, mot):
        if self.motoraction == True:
            self.OutputText.append("MOTORS BUSY, TRY AGAIN")
            return
        self.motoraction = True
        self.motorcontrol.stepping_operation(s1, unit=0x01)
        self.motoraction = False

        #self.motormove = wm.MotorThread(self.motorcontrol, mot, s1)
        #self.motormove.updateText.connect(self._handleMotorText)
        #self.motormove.start()

    def readLabels(self):
        #self.textlabels = [self.ObjText, self.RAObj, self.DECObj, self.NodRAText, self.NodDECText]
        try:
            f = open('/home/utopea/WIFIS-Team/wifiscontrol/textlabels.txt','r')
            values = []
            for l in f:
                values.append(l.split('\t')[-1][:-1])
            for i,label in enumerate(self.textlabels):
                label.setText(values[i])
        except:
            self.OutputText.append("### Old labels were not found")

    def doAstrometry(self):
        self.astrometrythread = wa.AstrometryThread(self.guider, self.RAObj,
                self.DECObj, self.ObjText, self.GuiderExpTime.text(), self.head,
                self.IISLabel.text())
        self.astrometrythread.updateText.connect(self._handleGuidingTextUpdate)
        self.astrometrythread.plotSignal.connect(self._handleGuidingPlotting)
        self.astrometrythread.astrometricPlotSignal.connect(self._handleAstrometricPlotting)
        self.astrometrythread.astrometryMove.connect(self._handleAstrometryMove)
        self.astrometrythread.start()
        
    def _handleAstrometryMove(self,FOffsethms, FOffsetdms):

        reply = QMessageBox.question(self, "Message", \
                "WIFIS Astrometry has determined a pointing adjustment of:\n RA: %.2f\nDEC: %.2f?\nWould you like to move the telescope by this amount?" % (FOffsethms, FOffsetdms), \
                QMessageBox.Yes | QMessageBox.Cancel)

        if reply == QMessageBox.Yes:
            result = wg.move_telescope(self.telsock, FOffsethms, FOffsetdms)
            self.GuidingText.append(result)
        else:
            return

    def _handleAstrometryCalc(self, solve):
        solvecenter, guideroffsets, plotting = solve
        x,y,k,xproj,yproj,image,head,coord = plotting

        self._handleAstrometricPlotting(plotting)

        #Grabbing the Object RA and DEC
        RAText = self.RAObj.text()
        DECText = self.DECObj.text()

        #RA and DEC of Guider center in deg
        ra_guide = solvecenter.ra.deg
        dec_guide = solvecenter.dec.deg
        GUIDERCoordhms = self.guider.returnhmsdmsstr(solvecenter.ra.hms)
        GUIDERCoorddms = self.guider.returnhmsdmsstr(solvecenter.dec.dms)

        #Performing the calculation to get the RA and DEC of the WIFIS field using the guider offsets
        #Note this assumes the offsets are true
        ra_wifis = ra_guide + (guideroffsets[0]/3600. / np.cos(dec_guide * np.pi / 180.))
        dec_wifis = dec_guide + guideroffsets[1]/3600.
        
        #Coord object for WIFIS Center
        WIFISCoord = SkyCoord(ra_wifis, dec_wifis, unit='deg')

        #Getting nice formatted strings for printout
        WIFISCoordhms = self.guider.returnhmsdmsstr(WIFISCoord.ra.hms)
        WIFISCoorddms = self.guider.returnhmsdmsstr(WIFISCoord.dec.dms)

        coordvalues = [GUIDERCoordhms, GUIDERCoorddms, WIFISCoordhms, WIFISCoorddms]

        self._handleGuidingTextUpdate("Real WIFIS Field Center is: \nRA %s\nDEC: %s" % (WIFISCoordhms, WIFISCoorddms))

        if (len(RAText) == 0) or (len(DECText) == 0):
            self._handleGuidingTextUpdate('RA or DEC Obj Text Empty!')
            self.writeOffsetInfo(plotting,WIFISCoord,'NotSet','NotSet', coordvalues, worked, guideroffsets)
            return

        #Checking if the entered target RA and DEC values are okay.
        RA, DEC = parseRADECText(RAText, DECText)
        if RA == False:
            self._handleGuidingTextUpdate(DEC)
            self._handleGuidingTextUpdate('RA or DEC Obj IMPROPER INPUT LIKELY')
            self.writeOffsetInfo(plotting,WIFISCoord,'NotSet','NotSet', coordvalues, worked, guideroffsets)
            return

        TargetCoord = SkyCoord(RA, DEC, unit=(u.hourangle, u.deg))
        fieldoffset = WIFISCoord.spherical_offsets_to(TargetCoord)
        #FOffsethms = fieldoffset[0].to(u.arcsec).to_string()
        #FOffsetdms = fieldoffset[1].to(u.arcsec).to_string()
        FOffsethms = fieldoffset[0].arcsec
        FOffsetdms = fieldoffset[1].arcsec

        GOffsetCoord = solvecenter.spherical_offsets_to(TargetCoord)
        #GOffsethms = GOffsetCoord[0].to(u.arcsec).to_string()
        #GOffsetdms = GOffsetCoord[1].to(u.arcsec).to_string()
        GOffsethms = GOffsetCoord[0].arcsec
        GOffsetdms = GOffsetCoord[1].arcsec
            
        self.writeOffsetInfo(plotting,WIFISCoord,RA,DEC, coordvalues, worked, guideroffsets)

        # De-rotating offsets for an IIS = 90.
        rotoffsetra, rotoffsetdec = wa.get_rotation_solution_offset(float(head['IIS']),\
                [GOffsethms,Goffsetdms], None, reverse=True)

        self._handleGuidingTextUpdate("IF RA/DEC IS CENTERED\nGuider Offsets Are:\nRA:\t%.2f\nDEC:\t%.2f\n" % \
                (rotoffsetra,rotoffsetdec))
        self._handleGuidingTextUpdate('WIFIS Offset (") to Target is:\nRA:\t%.2f\nDEC:\t%.2f\n' % \
                        (FOffsethms, FOffsetdms))

    def writeOffsetInfo(self, plotting, WIFISCoord, RA, DEC, coordvalues, worked, guideroffsets):
        x,y,k,xproj,yproj,image,head,coord = plotting

        fieldoffset = coord.spherical_offsets_to(WIFISCoord)
        FOffsethms = fieldoffset[0].to(u.arcsec).to_string()
        FOffsetdms = fieldoffset[1].to(u.arcsec).to_string()

        objtext = self.ObjText.text()
        todaydate = time.strftime("%Y%m%d")

        hdr = fits.Header()
        hdr['DATE'] = todaydate 
        hdr['SCOPE'] = 'Bok Telescope, Steward Observatory'
        hdr['ObsTime'] = time.strftime('%H:%M"%S')
        hdr['ExpTime'] = (self.GuiderExpTime.text(), '//Guider Exposure Time')
        hdr['RA'] = (head['RA'], '//Telescope RA')
        hdr['DEC'] = (head['DEC'], '//Telescope DEC')
        hdr['IIS'] = (head['IIS'], '//Rotator Angle')
        hdr['EL'] = head['EL']
        hdr['AZ'] = head['AZ']
        hdr['AM'] = (head['SECZ'], '//Airmass')
        hdr['Filter'] = self.guider.getFilterType()
        hdr['FocPos'] = self.guider.foc.get_stepper_position()
        hdr['OBJ'] = objtext
        hdr['OBJRA'] = (RA, '//Entered Object RA')
        hdr['OBJDEC'] = (DEC, '//Entered Object DEC')
        hdr['WRA'] = (coordvalues[2], '//Calculated WIFIS Field RA')
        hdr['WDEC'] = (coordvalues[3], '//Calculated WIFIS Field DEC')
        hdr['GRA'] = (coordvalues[0], '//Calculated Guider Field RA')
        hdr['GDEC'] = (coordvalues[1], '//Calculated Guider Field DEC')
        hdr['FOffRA'] = (FOffsethms, '//Arcsec from Telescope to WIFIS')
        hdr['FOffDEC'] = (FOffsetdms, '//Arcsec from Telescope to WIFIS')
        hdr['GRAOff'] = (str(guideroffsets[0]), '//Guider RA Offset')
        hdr['GDECOff'] = (str(guideroffsets[1]), '//Guider DEC Offset')
        fits.writeto('/Data/WIFISGuider/astrometry/'+todaydate+'T'+\
                        time.strftime('%H%M%S')+'.fits', image, hdr, clobber=True)

    def _handleAstrometricPlotting(self, plotting):
        try:
            x,y,k,xproj,yproj,image,head,coord = plotting
            #norm = ImageNormalize(image, interval=PercentileInterval(98.5),stretch=LinearStretch())

            self.plotwindow.guidefigure.clear()

            ax = self.plotwindow.guidefigure.add_subplot(1,1,1)
            #im = ax.imshow(image, origin='lower', norm=norm, interpolation='none', cmap='gray')
            pl2 = ax.plot(xproj[k], yproj[k], 'ro', label='Catalog Stars')
            pl1 = ax.plot(x,y,'b.', label='Image Stars')
            ax.legend()
            #im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
            #ax.format_coord = Formatter(im)
            ax.set_title('ASTROMETRIC FIELD')
            #self.guideplotwindow.figure.colorbar(im)
            self.plotwindow.guidefigure.tight_layout()

            self.plotwindow.guidecanvas.draw()

        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")
            
    def closeEvent(self, event):
        
        reply = QMessageBox.question(self, "Message", "Are you sure you want to quit?", QMessageBox.Close | QMessageBox.Cancel)

        if reply == QMessageBox.Close:
            event.accept()
            self.plotwindow.fullclose = True
            #self.guideplotwindow.fullclose = True

            self.plotwindow.close()
            #self.guideplotwindow.close()
        else:
            event.ignore()

class NoddingExposure(QThread):

    started = pyqtSignal()
    updateText = pyqtSignal(str)
    startGuiding = pyqtSignal(str)
    stopGuiding = pyqtSignal()
    progBar = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, scidet, guider, NodSelection, NNods, NodsPerCal, nramps, nreads,\
            objname, nodra, noddec, skipcalib, offsetArcsec, offsetRADEC, targetRA, targetDEC):

        QThread.__init__(self)

        self.scidet = scidet
        self.guider = guider
        self.NodSelection = NodSelection
        self.NNods = NNods
        self.NodsPerCal = NodsPerCal
        self.nramps = 1
        self.nreads = nreads
        self.objname = objname
        self.nodra = nodra
        self.noddec = noddec
        self.skipcalib = skipcalib
        self.offsetNod = offsetArcsec
        self.RADECNod = offsetRADEC
        self.RAObj = targetRA
        self.DECObj = targetDEC
        self.nreadssec = int(self.nreads.text())

        self.stopthread = False

    def __del__(self):
        self.wait()

    def stop(self):
        if self.stopthread == True:
            self.updateText.emit("### Still waiting for exposure to finish then stopping!")
            return
        self.updateText.emit("### STOPPING NODDING WHEN CURRENT EXPOSURE FINISHES")
        self.stopthread = True

    def run(self):
        if self.scidet.connected == False:
            self.updateText.emit("Please connect the detector and initialze if not done already")
            return

        self.NodSelectionVal = self.NodSelection.currentText()
        self.objnameval = self.objname.text()

        if self.RADECNod.isChecked():
            raoff, decoff = self.calcOffset()
            if raoff == False:
                self.updateText.emit("SOMETHING WRONG WITH RA/DEC INPUTS\nSEE BELOW")
                self.updateText.emit(decoff)
                return
            else:
                self.updateText.emit("CALCULATED OFFSETS\nRA:\t%f\nDEC:\t%f\n" % (raoff, decoff))
                self.nodraval = raoff
                self.noddecval = decoff
                if self.nodraval > 1500:
                    self.updateText.emit("NOD OFFSETS > 1500 arcsec -- QUITTING")
                    return
                if self.noddecval > 1500:
                    self.updateText.emit("NOD OFFSETS > 1500 arcsec -- QUITTING")
                    return
        else:
            try:
                self.nodraval = float(self.nodra.text())
                self.noddecval = float(self.noddec.text())
                if self.nodraval > 1500:
                    self.updateText.emit("NOD OFFSETS > 1500 arcsec -- QUITTING")
                    return
                if self.noddecval > 1500:
                    self.updateText.emit("NOD OFFSETS > 1500 arcsec -- QUITTING")
                    return
            except:
                self.updateText.emit("NOD OFFSETS NOT FLOATS -- QUITTING")
                return

        try:
            self.nrampsval = 1
            self.nreadsval = int(round(self.nreadssec/1.5))

            if self.nreadsval < 2:
                self.updateText.emit('Exposure time must be at least 3 seconds -- QUITTING')
                return

            self.NodsPerCalVal = int(self.NodsPerCal.text())
            self.NNodsVal = int(self.NNods.text())
        except Exception as e:
            self.updateText.emit("NOTE!\nN_RAMPS/N_READS/N_NODS/N_CALS NOT INTS -- QUITTING")
            return

        if self.stopthread:
            self.stopthread = False

        self.updateText.emit("### STARTING NODDING SEQUENCE")
        self.started.emit()

        if (not self.skipcalib.isChecked()) and (self.NodsPerCalVal != 0):
            self.updateText.emit("### DOING INITIAL CALIBS")
            self.progBar.emit(42, self.nrampsval)
            self.scidet.takecalibrations(self.objnameval)
        else:
            self.updateText.emit("### SKIPPING INITIAL CALIBS")

        if self.stopthread:
            self.updateText.emit("### STOPPED NODDING SEQUENCE")
            return

        for i in range(self.NNodsVal):
            for obstype in self.NodSelectionVal:
                if self.stopthread:
                    break

                if obstype == 'A':
                    self.startGuiding.emit('Obj')
                    self.sleep(5)
                    if self.stopthread:
                        break

                    self.progBar.emit(self.nreadssec, self.nrampsval)
                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval)

                    self.stopGuiding.emit()
                    self.sleep(5)
                elif obstype == 'B':
                    self.guider.moveTelescopeNod(self.nodraval, self.noddecval)
                    self.sleep(5)
                    self.startGuiding.emit('Sky')
                    self.sleep(5)
                    if self.stopthread:
                        break

                    self.progBar.emit(self.nreadssec, self.nrampsval)
                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval+'Sky')
                    
                    self.stopGuiding.emit()
                    self.sleep(5)
                    self.guider.moveTelescopeNod(-1.*self.nodraval, -1.*self.noddecval)
                    self.sleep(5)

                if self.stopthread:
                    break

            if self.stopthread:
                self.updateText.emit("### STOPPED NODDING SEQUENCE")
                break
            if self.NodsPerCalVal == 0:
                continue
            elif (i + 1) % self.NodsPerCalVal == 0:
                self.scidet.takecalibrations(self.objnameval)

        if not self.stopthread:
            self.updateText.emit("### FINISHED NODDING SEQUENCE")

        self.finished.emit()
    
    def calcOffset(self):
        RAObjP, DECObjP = parseRADECText(self.RAObj.text(), self.DECObj.text())
        RAOffP, DECOffP = parseRADECText(self.nodra.text(), self.noddec.text())

        if RAObjP == False:
            return False, DECObjP
        if RAOffP == False:
            return False, DECOffP

        startcoord = SkyCoord(RAObjP, DECObjP, unit = (u.hourangle, u.deg))
        targetcoord = SkyCoord(RAOffP, DECOffP, unit = (u.hourangle, u.deg))

        offset = startcoord.spherical_offsets_to(targetcoord)

        return float(offset[0].to(u.arcsec).to_string()[:-6]), \
                float(offset[1].to(u.arcsec).to_string()[:-6])
        
class UpdateLabels(QThread):

    updateText = pyqtSignal(list)

    def __init__(self, guider, guideron, updatevals, EnableForceIIS,\
            ForceIISEntry, textlabels):
        QThread.__init__(self)

        self.guider = guider
        self.guideron = guideron
        self.RAObj, self.DECObj = updatevals
        self.stopthread = False
        self.isrunning = False
        self.EnableForceIIS = EnableForceIIS
        self.ForceIISEntry = ForceIISEntry
        self.textlabels = textlabels

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopthread = True
        self.isrunning = False

    def run(self):

        while not self.stopthread:
            
            self.isrunning = True
            try:
                telemDict = wg.get_telemetry(self.guider.telSock, verbose=False)
                if self.EnableForceIIS.isChecked():
                    if self.ForceIISEntry.text() != '':
                        try:
                            float(self.ForceIISEntry.text())
                            telemDict['IIS'] = self.ForceIISEntry.text()
                        except:
                            self._handleOutputTextUpdate('### FORCED IIS NOT A FLOAT')

                telemDict['RAObj'] = self.RAObj.text()
                telemDict['DECObj'] = self.DECObj.text()

                wg.write_telemetry(telemDict)

                if self.guideron:
                    steppos = str(self.guider.foc.get_stepper_position())
                    ccdTemp = str(self.guider.cam.get_temperature())
                else:
                    steppos = "N/A"
                    ccdTemp = "N/A"
                
                self.updateText.emit([telemDict,steppos,ccdTemp])

                self.printLabels()

                self.sleep(5)

            except Exception as e:
                print "############################"
                print "ERROR IN LABEL UPDATE THREAD"
                print traceback.print_exc()
                print e
                print "############################"
        self.isrunning = False

    def printLabels(self):
        f = open('/home/utopea/WIFIS-Team/wifiscontrol/textlabels.txt','w')
        #self.textlabels = [self.ObjText, self.RAObj, self.DECObj, self.NodRAText, self.NodDECText]
        textlabelnames = ['Target','RAObj','DECObj','RANod','DECNod']
        for i in range(len(textlabelnames)):
            f.write('%s:\t%s\n' % (textlabelnames[i], self.textlabels[i].text()))

def parseRADECText(RAText, DECText):

    badformatstr = 'RA or DEC Obj IMPROPER INPUT\nPLEASE USE '+\
            'RA = HHMMSS.S and\nDEC = +/-DDMMSS.S, no spaces\n'

    try:
        float(RAText)
        float(DECText)
    except:
        return False, \
            

    if (len(RAText) == 0) or (len(DECText) == 0):
        return False, 'RA or DEC Text Empty!'

    try:
        if (RAText[0] == '+') or (RAText[0] == '-'):
            RAspl = RAText[1:].split('.')
            if len(RAspl[0]) != 6: 
                return False, badformatstr
        else:
            RAspl = RAText.split('.')
            if len(RAspl[0]) != 6: 
                return False, badformatstr
        if (DECText[0] == '+') or (DECText[0] == '-'):
            DECspl = DECText[1:].split('.')
            if len(DECspl[0]) != 6: 
                return False, badformatstr 
        else:
            DECspl = DECText.split('.')
            if len(DECspl) != 6: 
                return False, badformatstr 
    except Exception as e:
        print e
        return False, 'RA or DEC Obj IMPROPER INPUT LIKELY'

    if (RAText[0] == '+') or (RAText[0] == '-'):
        RA = RAText[1:3] + ' ' + RAText[3:5] + ' ' + RAText[5:]
    else:
        RA = RAText[0:2] + ' ' + RAText[2:4] + ' ' + RAText[4:]
    DEC = DECText[0:3] + ' ' + DECText[3:5] + ' ' + DECText[5:]

    return RA, DEC

def main():

    try:
        app = QApplication(sys.argv)  # A new instance of QApplication
        wifis = WIFISUI()                 # We set the form to be our ExampleApp (design)
        wifis.show()                         # Show the form
        app.exec_()                         # and execute the app
    except Exception as e:
        print e
        print traceback.print_exc()

if __name__ == '__main__':
    main()
