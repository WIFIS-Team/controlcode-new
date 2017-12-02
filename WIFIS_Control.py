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
                                    ImageNormalize)

import WIFISpower as pc
import WIFISmotor as wm
import traceback
from get_src_pos import do_get_src_pos

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
            reply = QMessageBox.question(self, "Message", "Close the main window to exit the GUI.\nPlotting will break if you close this window. Are you sure?", QMessageBox.Close | QMessageBox.Cancel)

            if reply == QMessageBox.Close:
                event.accept()
            else:
                event.ignore()

        else:
            event.accept()


class WIFISUI(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super(WIFISUI, self).__init__()

        self.setupUi(self)

        self.plotwindow = PlotWindow('WIFIS Plot Window')
        self.plotwindow.show()
        self.guideplotwindow = PlotWindow('Guider Plot Window')
        self.guideplotwindow.show()

        self.telsock = wg.connect_to_telescope()
        telemDict = wg.get_telemetry(self.telsock, verbose=False)
        self.IISLabel.setText(telemDict['IIS'])

        #Defining GUI Variables to feed into the guider functions
        guide_widgets = [self.RAMoveBox, self.DECMoveBox, self.FocStep, self.ExpType, self.ExpTime,\
                self.ObjText, self.SetTempValue, self.FilterVal, self.XPos, self.YPos,self.IISLabel]
        power_widgets = [self.Power11, self.Power12, self.Power13, self.Power14, self.Power15,\
                        self.Power16, self.Power17, self.Power18, self.Power21, self.Power22,\
                        self.Power23, self.Power24, self.Power25, self.Power26, self.Power27,\
                        self.Power28]
        
        caliblabels = [self.CalibModeButton,self.ObsModeButton,self.ArclampModeButton,self.ISphereModeButton]

        #self.updatetimer = QTimer(self)
        #self.updatetimer.setInterval(5000)
        #self.updatetimer.timeout.connect(self.updateLabels)
        #self.updatetimer.start()

        #Defining various control/serial variables
        try:
            #Power Control
            self.powercontrol = pc.PowerControl(power_widgets)
            self.switch1 = self.powercontrol.switch1
            self.switch2 = self.powercontrol.switch2
            
            self.calibrationcontrol = CalibrationControl(self.switch1, self.switch2, caliblabels)

            #Motor Control
            self.motorcontrol = wm.MotorControl() 
            self.motorcontrol.updateText.connect(self._handleMotorText)

            #Detector Control and Threads
            self.scidet = wd.h2rg(self.DetectorStatusLabel, self.switch1, self.switch2,\
                    self.calibrationcontrol)
            self.scidet.updateText.connect(self._handleOutputTextUpdate)
            self.scidet.plotSignal.connect(self._handlePlotting)

            #Guider Control and Threads
            self.guider = gf.WIFISGuider(guide_widgets)
            self.guider.updateText.connect(self._handleGuidingTextUpdate)
            self.guider.plotSignal.connect(self._handleGuidePlotting)

        except Exception as e:
            print e
            print traceback.print_exc()
            print "Something isn't connecting properly"
            return
        
        self.ExpProgressBar.setMinimum(0)
        self.ExpProgressBar.setMaximum(100)
        self.ExpProgressBar.setValue(0)
        
        #Starting function to update labels. Still need to add guider info.
        #self.labelsThread = UpdateLabels(self.guider, self.motorcontrol, self.RALabel, self.DECLabel,\
        #        self.AZLabel, self.ELLabel, self.IISLabel, self.HALabel, self.CCDTemp,self.FocPosition)
        self.labelsThread = UpdateLabelsNew(self.guider, self.motorcontrol)
        self.labelsThread.updateText.connect(self._handleUpdateLabels)
        self.labelsThread.start()
        
        #self.motorcontrol.get_position()
        #self.motorcontrol.update_status()

        #Defining actions for Exposure Control
        if self.scidet.connected == False:
            self.DetectorStatusLabel.setStyleSheet('color: red')
            
        self.actionConnect.triggered.connect(self.scidet.connect)
        self.actionInitialize.triggered.connect(self.scidet.initialize)
        self.actionDisconnect.triggered.connect(self.scidet.disconnect)
        #self.ExposureButton.clicked.connect(self.scidetexpose.start)
        #self.TakeCalibButton.clicked.connect(self.calibexpose.start)
        self.ExposureButton.clicked.connect(self.initExposure)
        self.TakeCalibButton.clicked.connect(self.initCalibExposure)
        self.NodBeginButton.clicked.connect(self.startNodding)
        self.CenteringCheck.clicked.connect(do_get_src_pos)

        #Defining actions for Telescope Control
        self.GuiderMoveButton.clicked.connect(self.guider.offsetToGuider)
        self.WIFISMoveButton.clicked.connect(self.guider.offsetToWIFIS)
        self.moveTelescopeButton.clicked.connect(self.guider.moveTelescope)
        self.MoveBackButton.clicked.connect(self.guider.moveTelescopeBack)
        self.CalOffsetButton.clicked.connect(self.guider.calcOffset)

        #Defining actions for Guider Control
        self.BKWButton.clicked.connect(self.guider.stepBackward)
        self.FWDButton.clicked.connect(self.guider.stepForward)
        self.SaveImageButton.clicked.connect(self.initGuideExposureSave)
        self.TakeImageButton.clicked.connect(self.initGuideExposure)
        self.FocusCameraButton.clicked.connect(self.focusCamera) 
        self.StartGuidingButton.clicked.connect(self.startGuiding)
        self.CentroidButton.clicked.connect(self.guider.checkCentroids)
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

        #CalibrationControl Buttons in Other Tab
        self.CalibModeButton.clicked.connect(self.calibrationcontrol.flip2pos2)
        self.ObsModeButton.clicked.connect(self.calibrationcontrol.flip2pos1)
        self.ArclampModeButton.clicked.connect(self.calibrationcontrol.flip1pos2)
        self.ISphereModeButton.clicked.connect(self.calibrationcontrol.flip1pos1)

        #Others
        self.SkyCheckBox.stateChanged.connect(self.skybuttonchanged)
        self.actionQuit.triggered.connect(self.close)

    def initGuideExposure(self):
        self.guideexp = gf.ExposeGuider(self.guider, False)
        self.guideexp.start()

    def initGuideExposureSave(self):
        self.guideexp = gf.ExposeGuider(self.guider, True)
        self.guideexp.start()

    def startGuiding(self):
        self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel)
        self.guideThread.updateText.connect(self._handleGuidingTextUpdate)
        self.guideThread.plotSignal.connect(self._handleGuidePlotting)
        self.guideThread.setSkySignal.connect(self._handleGuidingSky)
        self.StopGuidingButton.clicked.connect(self.guideThread.stop)

    def focusCamera(self):
        self.fcthread = gf.FocusCamera(self.guider.cam, self.guider.foc)
        self.fcthread.plotSignal.connect(self._handleGuidePlotting)
        self.fcthread.updateText.connect(self._handleGuidingTextUpdate)

    def skybuttonchanged(self):
        objtxt = self.ObjText.text()
        if self.SkyCheckBox.isChecked():
            self.ObjText.setText(objtxt+'Sky')
        else:
            if objtxt[-3:] == 'Sky':
                self.ObjText.setText(objtxt[:-3])

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
        self.progbar.start()

    def initCalibExposure(self):
        self.calibexpose = wd.h2rgExposeThread(self.scidet, "Calibrations",\
                nreads=int(self.NReadsText.text()),nramps=int(self.NRampsText.text()),\
                sourceName=self.ObjText.text())
        self.calibexpose.updateText.connect(self._handleOutputTextUpdate)
        self.calibexpose.start()

    def startNodding(self):
        self.noddingexposure = NoddingExposure(self.scidet, self.guider, self.NodSelection, \
                self.NNods, self.NodsPerCal, self.NRampsText, self.NReadsText, \
                self.ObjText, self.NodRAText, self.NodDecText)
        self.noddingexposure.updateText.connect(self._handleGuidingTextUpdate)
        self.noddingexposure.startGuiding.connect(self._handleNoddingGuide)
        self.noddingexposure.stopGuiding.connect(self._handleNoddingGuideStop)
        self.StopExpButton.clicked.connect(self.noddingexposure.stop)

    def _handleNoddingGuide(self, s):
        if s == 'Sky':
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel, sky=True)
        else:
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText, self.IISLabel, sky=False)
        self.guideThread.updateText.connect(self._handleOutputTextUpdate)
        self.guideThread.plotSignal.connect(self._handleGuidePlotting)
        self.guideThread.setSkySignal.connect(self._handleGuidingSky)
        self.StopGuidingButton.clicked.connect(self.guideThread.stop)

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
        self.FocPosition.setText(str(self.guider.foc.get_stepper_position()))
        self.CCDTemp.setText(str(self.guider.cam.get_temperature()))

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
            elif motnum == 1:
                self.motorcontrol.stepping_operation(self.FilterStep.text(), unit=0x02)
            elif motnum == 2:
                self.motorcontrol.stepping_operation(self.GratingStep.text(), unit=0x03)

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

    def __init__(self, scidet, guider, NodSelection, NNods, NodsPerCal, nramps, nreads,\
            objname, nodra, noddec):

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
        self.NNodsVal = int(self.NNods.text())
        self.NodsPerCalVal = int(self.NodsPerCal.text())
        self.nrampsval = int(self.nramps.text())
        self.nreadsval = int(self.nreads.text())
        self.objnameval = self.objname.text()
        self.nodraval = float(self.nodra.text())
        self.noddecval = float(self.noddec.text())
        if self.stopthread:
            self.stopthread = False

        self.updateText.emit("####### STARTING NODDING SEQUENCE #######")
        self.updateText.emit("# Doing initial calibrations")

        self.scidet.takecalibrations(self.objnameval)

        for i in range(self.NNodsVal):
            for obstype in self.NodSelectionVal:
                if obstype == 'A':
                    self.startGuiding.emit('Obj')
                    self.sleep(3)
                     
                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval)

                    self.stopGuiding.emit()
                    self.sleep(3)
                elif obstype == 'B':
                    self.guider.moveTelescopeNod(self.nodraval, self.noddecval)
                    self.sleep(3)
                    self.startGuiding.emit('Sky')
                    self.sleep(3)

                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval+'Sky')
                    
                    self.stopGuiding.emit()
                    self.sleep(3)
                    self.guider.moveTelescopeNod(-1.*self.nodraval, -1.*self.noddecval)
                    self.sleep(3)
                if self.stopthread:
                    break

            if self.stopthread:
                self.updateText.emit("####### STOPPED NODDING SEQUENCE #######")
                break
            if (i + 1) % self.NodsPerCalVal == 0:
                self.scidet.takecalibrations(self.objnameval)

        self.updateText.emit("####### FINISHED NODDING SEQUENCE #######")
        

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
                self.sleep(5)

            except Exception as e:
                print "############################"
                print "ERROR IN LABEL UPDATE THREAD"
                print traceback.print_exc()
                print e
                print "############################"

class UpdateLabelsNew(QThread):

    updateText = pyqtSignal(list)

    def __init__(self, guider, motorcontrol):
        QThread.__init__(self)

        self.guider = guider
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

                steppos = str(self.guider.foc.get_stepper_position())
                ccdTemp = str(self.guider.cam.get_temperature())
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
