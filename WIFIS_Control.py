from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QThread, QCoreApplication, QTimer, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import QDialog, QApplication, QPushButton, QVBoxLayout, QMessageBox

from wifis import Ui_MainWindow
import wifisguidingfunctions as wg
import WIFISdetector as wd
import guiding_functions as gf
import sys
from calibration_functions import CalibrationControl

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as mpl
from astropy.visualization import (PercentileInterval, LinearStretch,
                                    ImageNormalize, ZScaleInterval)
from pymodbus.client.sync import ModbusSerialClient as ModbusClient  

import WIFISpower as pc
import WIFISmotor as wm
import traceback
import numpy as np
from get_src_pos import get_src_pos
import time

motors = False

def read_defaults():

    f = open('/home/utopea/WIFIS-Team/wifiscontrol/defaultvalues.txt','r')
    valuesdict = {}
    for line in f:
        spl = line.split()
        valuesdict[spl[0]] = spl[1]
    f.close()

    return valuesdict

class Formatter(object):
    def __init__(self, im):
        self.im = im
    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
	return 'x={:.01f}, y={:.01f}, z={:.01f}'.format(x, y, z)

class PlotWindow(QDialog):

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
            reply = QMessageBox.question(self, "Message", "Close the main window to exit the GUI.\nClosing this window will break plotting.", QMessageBox.Cancel)

            event.ignore()

        else:
            event.accept()

class WIFISUI(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super(WIFISUI, self).__init__()

        self.setupUi(self)

        #Create the plotting windows
        self.plotwindow = PlotWindow('WIFIS Plot Window')
        self.plotwindow.show()
        self.guideplotwindow = PlotWindow('Guider Plot Window')
        self.guideplotwindow.show()

        guidevals = read_defaults()
        self.GuideRA.setText(guidevals['GuideRA'])
        self.GuideDEC.setText(guidevals['GuideDEC'])
        self.SetGuideOffset.clicked.connect(self.setGuideOffset)

        self.guideroffsets = [self.GuideRA, self.GuideDEC]

        #Defining GUI Variables to feed into different control classes
        #Important that the classes only read the variables and never try to adjust them.
        self.guide_widgets = [self.RAMoveBox, self.DECMoveBox, self.FocStep, self.ExpType, self.ExpTime,\
                self.ObjText, self.SetTempValue, self.FilterVal, self.XPos, self.YPos,self.IISLabel, self.guideroffsets]
        self.power_widgets = [self.Power11, self.Power12, self.Power13, self.Power14, self.Power15,\
                        self.Power16, self.Power17, self.Power18, self.Power21, self.Power22,\
                        self.Power23, self.Power24, self.Power25, self.Power26, self.Power27,\
                        self.Power28]
        self.caliblabels = [self.CalibModeButton,self.ObsModeButton,self.ArclampModeButton,self.ISphereModeButton]

        self.updateon = False

        self.connectTelescopeAction()
        self.connectPowerAction()
        self.connectCalibAction()
        self.connectGuiderAction()
        self.connectH2RGAction()

        #Defining various control/serial variables

        #self.calibon = False
        #self.calibrationcontrol = False

        #Connecting to Motor Control /// Currently disabled due to unknown crashes caused by Motor
        #Serial connection
        if motors:
            try:
                self.motorclient = ModbusClient(method="rtu", port="/dev/motor", stopbits=1, \
                bytesize=8, parity='E', baudrate=9600, timeout=0.1)
                print "Connecting to motors..."
                self.motorclient.connect()

                self.motorcontrol = wm.MotorControl(self.motorclient) 
                self.motorcontrol.updateText.connect(self._handleMotorText)
                self.motorson = True
            except:
                self.motorson = False
        else:
            self.motorcontrol = None
            self.motorson = False

        self.m1running = 0
        self.m2running = 0
        self.m3running = 0

        #Turn on label thread
        if self.telescope:
            updatevals = [self.RAObj, self.DECObj]
            if not self.updateon:
                self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.guideron,updatevals)
                self.labelsThread.updateText.connect(self._handleUpdateLabels)
                self.labelsThread.start()
                self.updateon = True
            else:
                if self.labelsThread.isrunning:
                    self.labelsThread.stop()
                    self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.guideron, updatevals)
                    self.labelsThread.updateText.connect(self._handleUpdateLabels)
                    self.labelsThread.start()
                else:
                    self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.guideron, updatevals)
                    self.labelsThread.updateText.connect(self._handleUpdateLabels)
                    self.labelsThread.start()
        
        #Defining settings from progress bar
        self.ExpProgressBar.setMinimum(0)
        self.ExpProgressBar.setMaximum(100)
        self.ExpProgressBar.setValue(0)
        
        #Starting function to update labels and telescope controls
        #self.telescopeSwitch(True)

        #Defining actions for Exposure Control
        #self.scidetSwitch()
        if self.scideton and not self.scidet.connected:
            self.DetectorStatusLabel.setStyleSheet('color: red')
        #Detector control functions that don't reference the detector
        self.ExposureButton.clicked.connect(self.initExposure)
        self.TakeCalibButton.clicked.connect(self.initCalibExposure)
        self.NodBeginButton.clicked.connect(self.checkStartNodding)
        self.CenteringCheck.clicked.connect(self.checkcentering)

        #Defining actions for Guider Control
        #self.guiderSwitch()
        #Guider Control functions that don't reference the guider
        self.SaveImageButton.clicked.connect(self.initGuideExposureSave)
        self.TakeImageButton.clicked.connect(self.initGuideExposure)
        self.FocusCameraButton.clicked.connect(self.focusCamera) 
        self.StartGuidingButton.clicked.connect(self.startGuiding)

        #Defining Actions for Power Control
        #self.powerSwitch()

        #CalibrationControl Buttons in Other Tab
        #self.calibSwitch()

        #Defining actions for Motor Control CURRENTLY DISABLED
        if motors:
            self.motorcontrol.update_status()
            self.motorcontrol.get_position() 

            self.FocusGoTo.clicked.connect(self.motorcontrol.m1_step)
            self.FilterGoTo.clicked.connect(self.motorcontrol.m2_step)
            self.GratingGoTo.clicked.connect(self.motorcontrol.m3_step)
            self.FocusHome.clicked.connect(self.motorcontrol.m1_home)
            self.FilterHome.clicked.connect(self.motorcontrol.m2_home)
            self.GratingHome.clicked.connect(self.motorcontrol.m3_home)
            self.FocusStop.clicked.connect(self.motorcontrol.m1_stop)
            self.FilterStop.clicked.connect(self.motorcontrol.m2_stop)
            self.GratingStop.clicked.connect(self.motorcontrol.m3_stop)
            self.TBButton.clicked.connect(self.motorcontrol.gotoTB)
            self.HButton.clicked.connect(self.motorcontrol.gotoH)
            self.BlankButton.clicked.connect(self.motorcontrol.gotoBlank)

        #Others
        self.SkyCheckBox.stateChanged.connect(self.skybuttonchanged)
        self.actionQuit.triggered.connect(self.close)
        
        self.FocusTestButton.setStyleSheet('background-color: red')
        self.FocusTestStop.setStyleSheet('background-color: red')
        self.FocusTestButton.setEnabled(False)
        self.FocusTestStop.setEnabled(False)
        #self.FocusTestButton.clicked.connect(self.runFocusTest)
        #self.FocusTestStop.clicked.connect(self.stopFocusTest)

        self.ConnectGuider.triggered.connect(self.connectGuiderAction)
        self.ConnectCalib.triggered.connect(self.connectCalibAction)
        self.ConnectPower.triggered.connect(self.connectPowerAction)
        self.ConnectH2RG.triggered.connect(self.connectH2RGAction)
        self.ConnectTelescope.triggered.connect(self.connectTelescopeAction)
        self.ConnectAll.triggered.connect(self.connectAllAction)
        
        self.SetNextButton.clicked.connect(self.setNextRADEC)

    def setGuideOffset(self):
        self._handleOutputTextUpdate('SETTING NEW GUIDE OFFSETS...')
        guidevals['GuideRA'] = self.GuideRA.text()
        guidevals['GuideDEC'] = self.GuideDEC.text()
        fl = open('/home/utopea/WIFIS-Team/wifiscontrol/defaultvalues.txt','w')
        for key, val in guidevals.iteritems():
            fl.write('%s\t\t%s\n' % (key, val))
        fl.close()
        self._handleOutputTextUpdate('NEW GUIDE OFFSETS SET')
        

    def calibSwitch(self):
        '''Connects all the calibration buttons to the proper functions'''
        if self.calibon:
            self.CalibModeButton.clicked.connect(self.calibrationcontrol.flip2pos2)
            self.ObsModeButton.clicked.connect(self.calibrationcontrol.flip2pos1)
            self.ArclampModeButton.clicked.connect(self.calibrationcontrol.flip1pos2)
            self.ISphereModeButton.clicked.connect(self.calibrationcontrol.flip1pos1)

    def powerSwitch(self):
        '''Connects all the Power buttons to the proper functions'''
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

    def guiderSwitch(self):
        '''Connects all the guider buttons to the proper functions'''
        if self.guideron:
            self.BKWButton.clicked.connect(self.guider.stepBackward)
            self.FWDButton.clicked.connect(self.guider.stepForward)
            self.CentroidButton.clicked.connect(self.guider.checkCentroids)
            self.SetTempButton.clicked.connect(self.guider.setTemperature)
            self.FilterVal.currentIndexChanged.connect(self.guider.goToFilter)

        if self.telescope:
            self.GuiderMoveButton.clicked.connect(self.guider.offsetToGuider)
            self.WIFISMoveButton.clicked.connect(self.guider.offsetToWIFIS)
            self.moveTelescopeButton.clicked.connect(self.guider.moveTelescope)
            self.MoveBackButton.clicked.connect(self.guider.moveTelescopeBack)
            self.CalOffsetButton.clicked.connect(self.guider.calcOffset)

    def scidetSwitch(self):
        '''Connects all the scidet buttons to the proper functions'''
        if self.scideton:
            self.actionConnect.triggered.connect(self.scidet.connect)
            self.actionInitialize.triggered.connect(self.scidet.initialize)
            self.actionDisconnect.triggered.connect(self.scidet.disconnect)
            self.scidet.connect()

    def telescopeSwitch(self):
        if self.telescope:
            updatevals = [self.RAObj, self.DECObj]
            if not self.updateon:
                self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.guideron, updatevals)
                self.labelsThread.updateText.connect(self._handleUpdateLabels)
                self.labelsThread.start()
                self.updateon = True
            else:
                if self.labelsThread.isrunning:
                    self.labelsThread.stop()
                    self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.guideron, updatevals)
                    self.labelsThread.updateText.connect(self._handleUpdateLabels)
                    self.labelsThread.start()
                else:
                    self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.guideron, updatevals)
                    self.labelsThread.updateText.connect(self._handleUpdateLabels)
                    self.labelsThread.start()


    def connectGuiderAction(self):
        #Connecting to Guider
        try:
            #Guider Control and Threads
            self.guider = gf.WIFISGuider(self.guide_widgets)
            self.guider.updateText.connect(self._handleGuidingTextUpdate)
            self.guider.plotSignal.connect(self._handleGuidePlotting)
            self.guideron = True
        except:
            print "##### Can't Connect to Guider ##### -- Something Failed"
            self.guideron = False

        if not self.guider.guiderready:
            print "##### Can't connect to one or all of the guider components"
            print "FOC: ",self.guider.foc
            print "CAM: ",self.guider.cam
            print "FLT: ",self.guider.flt
            self.guideron = False
            self.guiderToggle(False)
        else:
            self.guiderToggle(True)
            self.guiderSwitch()
            print "Connected to Guider #####"

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
                print "Connected to Calibration Unit #####"

            except Exception as e:
                print "##### Can't connect to Calibraiton Unit -- Something Failed"
                print e
                self.calibon = False
                self.calibrationcontrol = None
                self.calibToggle(False)
                
        else:
            print "##### Can't connect to Calibraiton Unit -- No Power Connection"
            self.calibon = False
            self.calibrationcontrol = None

            self.calibToggle(False)
            
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
            print "Connected to Power Controllers #####"

        except Exception as e:
            print "##### Can't connect to Power Controllers -- Something Failed"
            print e
            print traceback.print_exc()
            self.poweron = False
            self.ConnectPower.setText('Power - X')
            self.powerToggle(False, False, False)

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
            self.IISLabel.setText(telemDict['IIS']) #Set IIS early because certain functions rely on this value
            self.telescope = True

            self.telescopeToggle(True)

            #self.telescopeSwitch()
            print "Connected to Telescope #####"

        except Exception as e:
            print "##### Can't connect to telescope -- Something Failed"
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

        self.GuiderMoveButton.setEnabled(val)
        self.WIFISMoveButton.setEnabled(val)
        self.moveTelescopeButton.setEnabled(val)
        self.MoveBackButton.setEnabled(val)
        self.CalOffsetButton.setEnabled(val)
        self.SetNextButton.setEnabled(val)

    def connectH2RGAction(self):
        #Connecting to Detector
        if self.poweron:
            try:
                #Detector Control and Threads
                self.scidet = wd.h2rg(self.DetectorStatusLabel, self.switch1, self.switch2,\
                        self.calibrationcontrol)
                self.scidet.updateText.connect(self._handleOutputTextUpdate)
                self.scidet.plotSignal.connect(self._handlePlotting)
                self.scideton = True

                self.H2RGToggle(True)

                self.scidetSwitch()
                print "Connected to Science Array #####"
            except Exception as e:
                self.scideton = False
                print "##### Can't Connect to Science Array -- Something Failed"
                print e
                print traceback.print_exc()
                self.H2RGToggle(False)
        else:
            print "##### Can't Connect to Science Array -- No Power Connection"
            self.scideton = False
            self.H2RGToggle(False)

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
                self.GuiderExpTime.text(), self.OverGuideStar, self.guideroffsets)
        self.guideThread.updateText.connect(self._handleGuidingTextUpdate)
        self.guideThread.plotSignal.connect(self._handleGuidePlotting)
        self.guideThread.setSkySignal.connect(self._handleGuidingSky)
        self.StopGuidingButton.clicked.connect(self.guideThread.stop)
        self.guideThread.start()

    def focusCamera(self):
        self.fcthread = gf.FocusCamera(self.guider.cam, self.guider.foc, self.ExpTime)
        self.fcthread.plotSignal.connect(self._handleGuidePlotting)
        self.fcthread.updateText.connect(self._handleGuidingTextUpdate)
        self.fcthread.start()

    def skybuttonchanged(self):
        objtxt = self.ObjText.text()
        if self.SkyCheckBox.isChecked():
            self.ObjText.setText(objtxt+'Sky')
        else:
            if objtxt[-3:] == 'Sky':
                self.ObjText.setText(objtxt[:-3])

    def setNextRADEC(self):

        RAText = self.RAObj.text()
        DECText = self.DECObj.text()

        try:
            float(RAText)
            float(DECText)
        except:
            self._handleOutputTextUpdate('RA or DEC Obj IMPROPER INPUT')
            self._handleOutputTextUpdate('PLEASE USE RA = +/-HHMMSS.S  and')
            self._handleOutputTextUpdate('DEC = +/-DDMMSS.S, no spaces')
            return

        if (len(RAText) == 0) or (len(DECText) == 0):
            self._handleOutputTextUpdate('RA or DEC Obj Text Empty!')
            return

        if (RAText[0] == '+') or (RAText[0] == '-'):
            RAspl = RAText[1:].split('.')
            if len(RAspl[0]) != 6: 
                self._handleOutputTextUpdate('RA or DEC Obj IMPROPER INPUT')
                self._handleOutputTextUpdate('PLEASE USE RA = +/-HHMMSS.S  and')
                self._handleOutputTextUpdate('DEC = +/-DDMMSS.S, no spaces')
                return
        else:
            RAspl = RAText.split('.')
            if len(RAspl[0]) != 6: 
                self._handleOutputTextUpdate('RA or DEC Obj IMPROPER INPUT')
                self._handleOutputTextUpdate('PLEASE USE RA = +/-HHMMSS.S  and')
                self._handleOutputTextUpdate('DEC = +/-DDMMSS.S, no spaces')
                return

        if (DECText[0] == '+') or (DECText[0] == '-'):
            DECspl = DECText[1:].split('.')
            if len(DECspl[0]) != 6: 
                self._handleOutputTextUpdate('RA or DEC Obj IMPROPER INPUT')
                self._handleOutputTextUpdate('PLEASE USE RA = +/-HHMMSS.S  and')
                self._handleOutputTextUpdate('DEC = +/-DDMMSS.S, no spaces')
                return
        else:
            DECspl = DECText.split('.')
            if len(DECspl) != 6: 
                self._handleOutputTextUpdate('RA or DEC Obj IMPROPER INPUT')
                self._handleOutputTextUpdate('PLEASE USE RA = +/-HHMMSS.S  and')
                self._handleOutputTextUpdate('DEC = +/-DDMMSS.S, no spaces')
                return

        RAText = float(RAText)
        DECText = float(DECText)
        RAText = '%.1f' % (RAText)
        DECText = '%.1f' % (DECText)
     
        return1 = wg.set_next_radec(self.telsock,RAText,DECText)
        self._handleOutputTextUpdate(return1)
            

    def initExposure(self):
        self.scidetexpose = wd.h2rgExposeThread(self.scidet, self.ExpTypeSelect.currentText(),\
                nreads=int(self.NReadsText.text()),nramps=int(self.NRampsText.text()),\
                sourceName=self.ObjText.text())
        self.scidetexpose.updateText.connect(self._handleOutputTextUpdate)
        self.scidetexpose.finished.connect(self._handleExpFinished)
        self.scidetexpose.start()
        self.progbar = wd.h2rgProgressThread(self.ExpTypeSelect.currentText(),\
                nreads=int(self.NReadsText.text()),nramps=int(self.NRampsText.text()))
        self.progbar.updateBar.connect(self._handleProgressBar)
        self.progbar.finished.connect(self._handleExpFinished)
        self.progbar.start()

    def initCalibExposure(self):
        self.calibexpose = wd.h2rgExposeThread(self.scidet, "Calibrations",\
                nreads=int(self.NReadsText.text()),nramps=int(self.NRampsText.text()),\
                sourceName=self.ObjText.text())
        self.calibexpose.updateText.connect(self._handleOutputTextUpdate)
        self._handleNoddingProgBar(20,1)
        self.calibexpose.start()

    def checkStartNoding(self):
        choice = QtGui.QMessageBox.question(self, 'Nodding Sequence?',
                                            "Start Nodding Sequence?",
                                            QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        if choice == QtGui.QMessageBox.Yes:
            self.startNodding()
        else:
            pass

    def startNodding(self):
        self.noddingexposure = NoddingExposure(self.scidet, self.guider, self.NodSelection, \
                self.NNods, self.NodsPerCal, self.NRampsText, self.NReadsText, \
                self.ObjText, self.NodRAText, self.NodDecText, self.SkipCalib)
        self.noddingexposure.updateText.connect(self._handleOutputTextUpdate)
        self.noddingexposure.startGuiding.connect(self._handleNoddingGuide)
        self.noddingexposure.stopGuiding.connect(self._handleNoddingGuideStop)
        self.StopExpButton.clicked.connect(self.noddingexposure.stop)
        self.noddingexposure.progBar.connect(self._handleNoddingProgBar)

        self.noddingexposure.start()

    def _handleNoddingProgBar(self, nreads, nramps):

        self.progbar = wd.h2rgProgressThread('Ramp',nreads=nreads,nramps=nramps)
        self.progbar.updateBar.connect(self._handleProgressBar)
        self.progbar.finished.connect(self._handleExpFinished)
        self.progbar.start()

    def _handleNoddingGuide(self, s):
        if s == 'Sky':
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel, \
                    self.GuiderExpTime.text(), self.OverGuideStar, self.guideroffsets, sky=True)
        else:
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel, \
                    self.GuiderExpTime.text(), self.OverGuideStar, self.guideroffsets, sky=False)
        self.guideThread.updateText.connect(self._handleGuidingTextUpdate)
        self.guideThread.plotSignal.connect(self._handleGuidePlotting)
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

    def _handleExpFinished(self):
        self.ExpProgressBar.setValue(0)

    def _handleUpdateLabels(self, labelupdates):
        telemDict,steppos,ccdtemp = labelupdates

        DECText = telemDict['DEC']
        RAText = telemDict['RA']

        self.RALabel.setText(RAText[0:2]+':'+RAText[2:4]+':'+RAText[4:])
        self.DECLabel.setText(DECText[0:3]+':'+DECText[3:5]+':'+DECText[5:])
        self.AZLabel.setText(telemDict['AZ'])
        self.ELLabel.setText(telemDict['EL'])
        self.IISLabel.setText(telemDict['IIS'])
        self.HALabel.setText(telemDict['HA'])
        self.FocPosition.setText(steppos)
        self.CCDTemp.setText(ccdtemp)

    def checkcentering(self):
        fieldrecObj = get_src_pos('/home/utopea/WIFIS-Team/wifiscontrol/wave.lst','/home/utopea/WIFIS-Team/wifiscontrol/flat.lst',\
                '/home/utopea/WIFIS-Team/wifiscontrol/obs.lst')
        fieldrecObj.plotField.connect(self._handleFRPlotting)
        fieldrecObj.doFieldRec()


        #Old implementation without classes
        #do_get_src_pos('/home/utopea/WIFIS-Team/wifiscontrol/wave.lst','/home/utopea/WIFIS-Team/wifiscontrol/flat.lst',\
        #        '/home/utopea/WIFIS-Team/wifiscontrol/obs.lst')

    def _handlePlotting(self, image, flname):

        try:
            norm = ImageNormalize(image, interval=PercentileInterval(99.5),stretch=LinearStretch())

            self.plotwindow.figure.clear()

            ax = self.plotwindow.figure.add_subplot(1,1,1)
            im = ax.imshow(image, origin='lower', norm=norm, interpolation='none')
            ax.format_coord = Formatter(im)
            ax.set_title(flname)
            self.plotwindow.figure.colorbar(im)

            self.plotwindow.canvas.draw()
        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")

    def _handleGuidePlotting(self, image, flname):
        print "IMAGE IS...", image

        try:
            norm = ImageNormalize(image, interval=PercentileInterval(99.5),stretch=LinearStretch())

            self.guideplotwindow.figure.clear()

            ax = self.guideplotwindow.figure.add_subplot(1,1,1)
            im = ax.imshow(image, origin='lower', norm=norm, interpolation='none', cmap='gray')
            ax.format_coord = Formatter(im)
            ax.set_title(flname)
            self.guideplotwindow.figure.colorbar(im)

            self.guideplotwindow.canvas.draw()

        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")

    def _handleFRPlotting(self, returns):

        try:
            dataImg, WCS, hdr, gFit, xScale, yScale = returns
            
            #Things that are needed for plotting the data
            #WCS, dataImg, hdr

            print('Plotting FIELD REC data')
            self.plotwindow.figure.clear()
            ax = self.plotwindow.figure.add_subplot(111, projection=WCS)

            scaling = 'normal'
            if scaling=='zscale':
                interval=ZScaleInterval()
                lims=interval.get_limits(dataImg)
            else:
                lims=[dataImg.min(),dataImg.max()]
            im = ax.imshow(dataImg, origin='lower', cmap='jet', clim=lims)

            #if colorbar:
            #    plt.colorbar()
            self.plotwindow.figure.colorbar(im)
                
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

            self.plotwindow.canvas.draw()
        except Exception as e:
            print e
            print traceback.print_exc()
            self.OutputText.append("SOMETHING WENT WRONG WITH THE PLOTTING")

    def _handleMotorText(self, s, labeltype, motnum):
        
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

        if labeltype == 'Step':
            if motnum == 0:
                self.motorcontrol.stepping_operation(self.FocusStep.text(), unit=0x01)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, self.FocusStep.text())
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()
            elif motnum == 1:
                self.motorcontrol.stepping_operation(self.FilterStep.text(), unit=0x02)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, self.FilterStep.text())
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()
            elif motnum == 2:
                self.motorcontrol.stepping_operation(self.GratingStep.text(), unit=0x03)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, self.GratingStep.text())
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()

        if (labeltype == 'Step') and (len(s) != 0):
            if motnum == 0:
                self.motorcontrol.stepping_operation(s, unit=0x01)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, s)
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()
            elif motnum == 1:
                self.motorcontrol.stepping_operation(s, unit=0x02)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, s)
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()
            elif motnum == 2:
                self.motorcontrol.stepping_operation(s, unit=0x03)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, s)
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()

        if labeltype == 'Home':
            if motnum == 0:
                self.motorcontrol.homing_operation(0x01)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, 0)
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()
            elif motnum == 1:
                self.motorcontrol.homing_operation(0x02)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, 0)
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()
            elif motnum == 2:
                self.motorcontrol.homing_operation(0x03)
                #self.motormove = wm.MotorThread(self.motorcontrol, motnum, 0)
                #self.motormove.updateText.connect(self._handleMotorText)
                #self.motormove.start()

                
    def runFocusTest(self):
        self.focustest = FocusTest(self.motorcontrol, self.scidet, self.FocusStatus, self.calibrationcontrol,\
                self.FocusPosition)
        self.focustest.updateText.connect(self._handleOutputTextUpdate)
        self.focustest.moveMotor.connect(self._handleMoveMotor)
        self.focustest.start()

    def stopFocusTest(self):
        self.focustest.stop()

    def _handleMoveMotor(self, s1, s2, mot):
        self.motorcontrol.stepping_operation(s1, unit=0x01)
        #self.motormove = wm.MotorThread(self.motorcontrol, mot, s1)
        #self.motormove.updateText.connect(self._handleMotorText)
        #self.motormove.start()


    def closeEvent(self, event):
        
        reply = QMessageBox.question(self, "Message", "Are you sure you want to quit?", QMessageBox.Close | QMessageBox.Cancel)

        if reply == QMessageBox.Close:
            event.accept()
            self.plotwindow.fullclose = True
            self.guideplotwindow.fullclose = True

            self.plotwindow.close()
            self.guideplotwindow.close()
        else:
            event.ignore()

class NoddingExposure(QThread):

    updateText = pyqtSignal(str)
    startGuiding = pyqtSignal(str)
    stopGuiding = pyqtSignal()
    progBar = pyqtSignal(int, int)

    def __init__(self, scidet, guider, NodSelection, NNods, NodsPerCal, nramps, nreads,\
            objname, nodra, noddec, skipcalib):

        QThread.__init__(self)

        self.scidet = scidet
        self.guider = guider
        self.NodSelection = NodSelection
        self.NNods = NNods
        self.NodsPerCal = NodsPerCal
        self.nramps = nramps
        self.nreads = nreads
        self.objname = objname
        self.nodra = nodra
        self.noddec = noddec
        self.skipcalib = skipcalib

        self.stopthread = False

    def __del__(self):
        self.wait()

    def stop(self):
        if self.stopthread == True:
            self.updateText.emit("Waiting for exposure to finish then stopping!")
        self.updateText.emit("####### STOPPING NODDING WHEN CURRENT EXPOSURE FINISHES #######")
        self.stopthread = True

    def run(self):
        if self.scidet.connected == False:
            self.updateText.emit("Please connect the detector and initialze if not done already")
            return

        self.NodSelectionVal = self.NodSelection.currentText()
        try:
            self.nrampsval = int(self.nramps.text())
            self.nreadsval = int(self.nreads.text())
            self.NodsPerCalVal = int(self.NodsPerCal.text())
            self.NNodsVal = int(self.NNods.text())
        except:
            self.updateText.emit("N_RAMPS/N_READS/N_NODS/N_CALS NOT INTS -- QUITTING")
            return

        self.objnameval = self.objname.text()
        try:
            self.nodraval = float(self.nodra.text())
            self.noddecval = float(self.noddec.text())
        except:
            self.updateText.emit("NOD VALUES NOT FLOATS -- QUITTING")
            return

        if self.stopthread:
            self.stopthread = False

        self.updateText.emit("####### STARTING NODDING SEQUENCE #######")
        self.updateText.emit("# Doing initial calibrations")

        if not self.skipcalib.isChecked():
            self.progBar.emit(20, self.nrampsval)
            self.scidet.takecalibrations(self.objnameval)

        if self.stopthread:
            self.updateText.emit("####### STOPPED NODDING SEQUENCE #######")
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

                    self.progBar.emit(self.nreadsval, self.nrampsval)
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

                    self.progBar.emit(self.nreadsval, self.nrampsval)
                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval+'Sky')
                    
                    self.stopGuiding.emit()
                    self.sleep(5)
                    self.guider.moveTelescopeNod(-1.*self.nodraval, -1.*self.noddecval)
                    self.sleep(5)

                if self.stopthread:
                    break

            if self.stopthread:
                self.updateText.emit("####### STOPPED NODDING SEQUENCE #######")
                break
            if (i + 1) % self.NodsPerCalVal == 0:
                self.scidet.takecalibrations(self.objnameval)

        self.updateText.emit("####### FINISHED NODDING SEQUENCE #######")
        
class UpdateLabels(QThread):

    updateText = pyqtSignal(list)

    def __init__(self, guider, motorcontrol, guideron,updatevals):
        QThread.__init__(self)

        self.guider = guider
        self.motorcontrol = motorcontrol
        self.guideron = guideron
        self.RAObj, self.DECObj = updatevals
        self.stopthread = False
        self.isrunning = False

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
                telemDict['RAObj'] = self.RAObj.text()
                telemDict['DECObj'] = self.DECObj.text()
                wg.write_telemetry(telemDict)

                if self.guideron:
                    steppos = str(self.guider.foc.get_stepper_position())
                    ccdTemp = str(self.guider.cam.get_temperature())
                else:
                    steppos = "N/A"
                    ccdTemp = "N/A"
                
                if motors:
                    self.motorcontrol.update_status()
                    self.motorcontrol.get_position()

                self.updateText.emit([telemDict,steppos,ccdTemp])

                self.sleep(4)

            except Exception as e:
                print "############################"
                print "ERROR IN LABEL UPDATE THREAD"
                print traceback.print_exc()
                print e
                print "############################"
        self.isrunning = False

class FocusTest(QThread):

    updateText = pyqtSignal(str)
    moveMotor = pyqtSignal(str,str,int)

    def __init__(self, motorcontrol, scidet, focusstatus, calibcontrol, focvalue):
        QThread.__init__(self)

        self.motorcontrol = motorcontrol
        self.scidet = scidet
        self.stopthread = False
        self.focarray = np.arange(-200,200,10)
        #self.focarray = np.arange(-20,20,10)
        self.focstatus = focusstatus
        self.calibcontrol = calibcontrol
        self.focvalue = focvalue

    def __del__(self):
        self.wait()

    def stop(self):
        self.updateText.emit("STOPPING FOCUS THREAD ASAP")
        self.stopthread = True

    def run(self):

        self.updateText.emit("### STARTING FOCUS TEST")
        nexp = len(self.focarray)
        i = 0
        while (not self.stopthread) and (i < nexp):
            try:                
                self.updateText.emit("### MOVING TO %i" % (self.focarray[i]))
                self.moveMotor.emit(str(self.focarray[i]),'Step',0)
                self.sleep(3)
                currentfocvalue = self.focvalue.text()
                t1 = time.time()
                while currentfocvalue != str(self.focarray[i]):
                    currentfocvalue = self.focvalue.text()
                    
                    if self.stopthread:
                        break
                    continue

                    t2 = time.time()
                    if ((t2 - t1) / 60) > 0.5:
                        self.stopthread = True
                        self.updateText.emit("Taking too long to move...")
                        break

                    self.sleep(1)

                self.sleep(2)

                currentfocvalue = self.focvalue.text()
                if currentfocvalue != str(self.focarray[i]):
                    self.updateText.emit("THE MOTOR ISNT MOVING PROPERLY, EXITING...")
                    break

                self.scidet.flatramp('FocusTest', notoggle=True)

                if self.stopthread:
                    self.updateText.emit("EXITING FOCUS THREAD")
                    break

                i += 1

            except Exception as e:
                print "############################"
                print "ERROR IN FOCUS TEST THREAD"
                print traceback.print_exc()
                print e
                print "############################"

        self.calibcontrol.sourcesetup()
        self.updateText.emit("FOCUS THREAD FINISHED")

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
