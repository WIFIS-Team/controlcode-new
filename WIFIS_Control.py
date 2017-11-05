from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QThread, QCoreApplication
from PyQt5.QtWidgets import QDialog, QApplication, QPushButton, QVBoxLayout, QMessageBox

from wifis import Ui_MainWindow
import wifis_guiding as wg
import WIFISdetector as wd
import guiding_functions as gf
import sys

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as mpl

import WIFISpower as pc
import WIFISmotor as wm
import traceback


class PlotWindow(QDialog):
    def __init__(self, parent=None):
        super(PlotWindow, self).__init__(parent)
        
        self.figure = mpl.figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)

        # set the layout
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.canvas)
        self.setLayout(self.layout)

        #self.layout.btnExit.clicked.connect(self.close)
        #self.layout.actionExit.triggered.connect(self.close)

    def closeEvent(self, event):
        
        reply = QMessageBox.question(self, "Message", "You will no longer see plots if you close this window. Are you sure?", QMessageBox.Close | QMessageBox.Cancel)

        if reply == QMessageBox.Close:
            event.accept()
        else:
            event.ignore()


class WIFISUI(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super(WIFISUI, self).__init__()

        self.setupUi(self)

        self.plotwindow = PlotWindow()
        self.plotwindow.show()
      
        #Defining GUI Variables to feed into the guider functions
        guide_widgets = [self.RAMoveBox, self.DECMoveBox, self.FocStep, self.ExpType, self.ExpTime,\
                self.ObjText, self.SetTempValue, self.FilterVal, self.XPos, self.YPos,self.GuidingText]
        power_widgets = [self.Power11, self.Power12, self.Power13, self.Power14, self.Power15,\
                        self.Power16, self.Power17, self.Power18, self.Power21, self.Power22,\
                        self.Power23, self.Power24, self.Power25, self.Power26, self.Power27,\
                        self.Power28]
        motor_modules = self.FocusStatus, self.FilterStatus, self.GratingStatus, self.FocusPosition,\
                self.FilterPosition, self.GratingPosition, self.FocusStep,\
                self.FilterStep, self.GratingStep

        #Defining various control/serial variables

        try:
            #Power Control
            self.powercontrol = pc.PowerControl(power_widgets)
            self.switch1 = self.powercontrol.switch1
            self.switch2 = self.powercontrol.switch2
            
            #Motor Control
            self.motorcontrol = wm.MotorControl(motor_modules) 

            #Detector Control and Threads
            self.scidet = wd.h2rg(self.DetectorStatusLabel, self.switch1, self.switch2, self.plotwindow,\
                    self.OutputText)
            self.scidetexpose = wd.h2rgExposeThread(self.scidet, self.ExpTypeSelect,self.ExpProgressBar,\
                    self.OutputText, nreads=self.NReadsText,nramps=self.NRampsText,sourceName=self.ObjText)
            self.calibexpose = wd.h2rgExposeThread(self.scidet,"Calibrations",self.ExpProgressBar,\
                    self.OutputText, nreads=self.NReadsText,nramps=self.NRampsText,sourceName=self.ObjText)

            #Guider Control and Threads
            self.guider = gf.WIFISGuider(guide_widgets)
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText,\
                    self.GuidingText)

            #Nodding
            self.noddingexposure=NoddingExposure(self.scidet, self.guider, self.NodSelection, \
                    self.NNods,self.NodsPerCal,\
                    self.guideThread, self.NRampsText, self.NReadsText, \
                    self.ObjText, self.NodRAText, self.NodDecText, self.OutputText)

        except Exception as e:
            print e
            print traceback.print_exc()
            print "Something isn't connecting properly"
            return
            
        self.ExpProgressBar.setValue(0)
        #Starting function to update labels. Still need to add guider info.
        self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.RALabel, self.DECLabel,\
                self.AZLabel, self.ELLabel, self.IISLabel, self.HALabel, self.CCDTemp,self.FocPosition)
        self.labelsThread.start()

        #Defining actions for Exposure Control
        if self.scidet.connected == False:
            self.DetectorStatusLabel.setStyleSheet('color: red')
            
        self.actionConnect.triggered.connect(self.scidet.connect)
        self.actionInitialize.triggered.connect(self.scidet.initialize)
        self.actionDisconnect.triggered.connect(self.scidet.disconnect)
        self.ExposureButton.clicked.connect(self.scidetexpose.start)
        self.TakeCalibButton.clicked.connect(self.calibexpose.start)
        #self.ExposureButton.clicked.connect(self.h2rgProgressThread.start)
        self.NodBeginButton.clicked.connect(self.noddingexposure.start)
        self.StopExpButton.clicked.connect(self.noddingexposure.stop)

        #Defining actions for Telescope Control
        self.GuiderMoveButton.clicked.connect(self.guider.offsetToGuider)
        self.WIFISMoveButton.clicked.connect(self.guider.offsetToWIFIS)
        self.moveTelescopeButton.clicked.connect(self.guider.moveTelescope)
        self.MoveBackButton.clicked.connect(self.guider.moveTelescopeBack)
        self.CalOffsetButton.clicked.connect(self.guider.calcOffset)

        #Defining actions for Guider Control
        self.BKWButton.clicked.connect(self.guider.stepBackward)
        self.FWDButton.clicked.connect(self.guider.stepForward)
        self.SaveImageButton.clicked.connect(self.guider.saveImage) #Need to thread this
        self.TakeImageButton.clicked.connect(self.guider.takeImage) #Need to thread this
        self.FocusCameraButton.clicked.connect(self.guider.focusCamera) #Need to thread
        self.StartGuidingButton.clicked.connect(self.guideThread.start)
        self.CentroidButton.clicked.connect(self.guider.checkCentroids)
        self.StopGuidingButton.clicked.connect(self.guideThread.stop)
        self.SetTempButton.clicked.connect(self.guider.setTemperature)
        self.FilterVal.currentIndexChanged.connect(self.guider.goToFilter)

        #Defining Actions for Power Control
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

        #Defining actions for Motor Control
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

    def skybuttonchanged(self):
        objtxt = self.ObjText.text()
        if self.SkyCheckBox.isChecked():
            self.ObjText.setText(objtxt+'Sky')
        else:
            if objtxt[-3:] == 'Sky':
                self.ObjText.setText(objtxt[:-3])


class NoddingExposure(QThread):

    def __init__(self, scidet, guider, NodSelection, NNods, NodsPerCal, guideThread, nramps, nreads,\
            objname, nodra, noddec, OutputText):

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
        self.OutputText = OutputText

        self.guideThread = guideThread

        self.stopthread = False

    def __del__(self):
        self.wait()

    def stop(self):
        if self.stopthread == True:
            print "Waiting for exposure to finish then stopping!"
        print "####### STOPPING NODDING WHEN CURRENT EXPOSURE FINISHES #######"
        self.stopthread = True

    def run(self):
        if self.scidet.connected == False:
            print "Please connect the detector and initialze if not done already"
            return

        self.NodSelectionVal = self.NodSelection.currentText()
        self.NNodsVal = int(self.NNods.text())
        self.NodsPerCalVal = int(self.NodsPerCal.text())
        self.nrampsval = int(self.nramps.text())
        self.nreadsval = int(self.nreads.text())
        self.objnameval = self.objname.text()
        self.nodraval = float(self.nodra.text())
        self.noddecval = float(self.noddec.text())
        if self.stopthread:
            self.stopthread = False

        print "####### STARTING NODDING SEQUENCE #######"
        print "# Doing initial calibrations"
        self.scidet.takecalibrations(self.objnameval)

        for i in range(self.NNodsVal):
            for obstype in self.NodSelectionVal:
                if obstype == 'A':
                    self.guideThread.setObj()
                    self.guideThread.start()
                    self.sleep(2)
                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval)
                    self.guideThread.stop()
                    self.sleep(2)
                elif obstype == 'B':
                    self.guideThread.setSky()
                    self.guider.moveTelescopeNod(self.nodraval, self.noddecval)
                    self.sleep(2)
                    self.guideThread.start()
                    self.sleep(2)

                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval+'Sky')
                    
                    self.guideThread.stop()
                    self.sleep(2)
                    self.guideThread.setObj()
                    self.guider.moveTelescopeNod(-1.*self.nodraval, -1.*self.noddecval)
                    self.sleep(2)
                if self.stopthread:
                    break
                #self.guideThread.stop()
            if self.stopthread:
                print "####### STOPPED NODDING SEQUENCE #######"
                break
            if (i + 1) % self.NodsPerCalVal == 0:
                self.scidet.takecalibrations(self.objnameval)
        print "####### FINISHED NODDING SEQUENCE #######"
        

class UpdateLabels(QThread):

    def __init__(self, guider, motorcontrol, RALabel, DECLabel, AZLabel, ELLabel, IISLabel, \
            HALabel, ccdTemp, focpos):
        QThread.__init__(self)

        self.guider = guider
        self.RALabel = RALabel
        self.DECLabel = DECLabel
        self.AZLabel = AZLabel
        self.ELLabel = ELLabel
        self.IISLabel = IISLabel
        self.HALabel = HALabel
        self.ccdTemp = ccdTemp
        self.focpos = focpos
        self.motorcontrol = motorcontrol
        self.stopthread = False

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopthread = True

    def run(self):

        while not self.stopthread:
            try:
                telemDict = wg.get_telemetry(self.guider.telSock, verbose=False)
                
                DECText = telemDict['DEC']
                RAText = telemDict['RA']

                self.RALabel.setText(RAText[0:2]+':'+RAText[2:4]+':'+RAText[4:])
                self.DECLabel.setText(DECText[0:3]+':'+DECText[3:5]+':'+DECText[5:])
                self.AZLabel.setText(telemDict['AZ'])
                self.ELLabel.setText(telemDict['EL'])
                self.IISLabel.setText(telemDict['IIS'])
                self.HALabel.setText(telemDict['HA'])
                self.focpos.setText(str(self.guider.foc.get_stepper_position()))
                self.ccdTemp.setText(str(self.guider.cam.get_temperature()))
                #self.motorcontrol.update_status()
                #self.motorcontrol.get_position()
                #self.powercontrol.checkOn()
                self.sleep(3)

            except Exception as e:
                print "############################"
                print "ERROR IN LABEL UPDATE THREAD"
                print traceback.print_exc()
                print e
                print "############################"




def main():

    app = QApplication(sys.argv)  # A new instance of QApplication
    wifis = WIFISUI()                 # We set the form to be our ExampleApp (design)
    wifis.show()                         # Show the form
    app.exec_()                         # and execute the app

if __name__ == '__main__':
    main()
