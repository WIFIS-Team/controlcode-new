from PyQt5.QtWidgets import QApplication, QMainWindow
import sys
from wifis import Ui_MainWindow
import wifis_guiding as wg
import WIFISdetector as wd
import power_control as pc
from PyQt5.QtCore import QThread, QCoreApplication
import guiding_functions as gf
import matplotlib.pyplot as mpl
import WIFISpower as pc

class WIFISUI(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super(WIFISUI, self).__init__()

        self.setupUi(self)
      
        #Defining GUI Variables to feed into the guider functions
        guidevariables = [self.RAMoveBox, self.DECMoveBox, self.FocStep, self.ExpType, self.ExpTime,\
                self.ObjText, self.SetTempValue, self.FilterVal]
        power_widgets = [self.Power11, self.Power12, self.Power13, self.Power14, self.Power15,\
                        self.Power16, self.Power17, self.Power18, self.Power21, self.Power22,\
                        self.Power23, self.Power24, self.Power25, self.Power26, self.Power27,\
                        self.Power28]
        #Defining various control/serial variables

        try:
            #Power Control
            self.powercontrol = pc.PowerControl(power_widgets)
            self.switch1 = self.powercontrol.switch1
            self.switch2 = self.powercontrol.switch2
            
            #Detector Control and Threads
            self.scidet = wd.h2rg(self.DetectorStatusLabel, self.switch1, self.switch2)
            self.scidetexpose = wd.h2rgExposeThread(self.scidet, self.ExpTypeSelect,self.ExpProgressBar,\
                    nreads=self.NReadsText,nramps=self.NRampsText,sourceName=self.ObjText)
            self.calibexpose = wd.h2rgExposeThread(self.scidet,"Calibrations",self.ExpProgressBar,\
                    nreads=self.NReadsText,nramps=self.NRampsText,sourceName=self.ObjText)

            #Guider Control and Threads
            self.guider = gf.WIFISGuider(guidevariables)
            self.guideThread = gf.RunGuiding(self.guider.telSock, self.guider.cam, self.ObjText)

            #Nodding
            self.noddingexposure=NoddingExposure(self.scidet, self.guider, self.NodSelection, \
                    self.NNods,self.NodsPerCal,\
                    self.guideThread, self.NRampsText, self.NReadsText, \
                    self.ObjText, self.NodRAText, self.NodDecText)

        except Exception as e:
            print e
            print "Something isn't connecting properly"
            return
            
        self.ExpProgressBar.setValue(0)
        #Starting function to update labels. Still need to add guider info.
        self.labelsThread = UpdateLabels(self.guider, self.powercontrol, self.RALabel, self.DECLabel,\
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

class NoddingExposure(QThread):

    def __init__(self, scidet, guider, NodSelection, NNods, NodsPerCal, guideThread, nramps, nreads,\
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

        self.guideThread = guideThread

        self.stopthread = False

    def __del__(self):
        self.wait()

    def stop(self):
        print "####### STOPPING NODDING WHEN CURRENT EXPOSURE FINISHES #######"
        self.stopthread = True

    def run(self):
        if self.scidet.connected == False:
            print "Please connect the detector and initialze if not done already"
            return

        self.NodSelectionVal = self.NodSelection.currentText()
        self.NNodsVal = int(self.NNods.toPlainText())
        self.NodsPerCalVal = int(self.NodsPerCal.toPlainText())
        self.nrampsval = int(self.nramps.toPlainText())
        self.nreadsval = int(self.nreads.toPlainText())
        self.objnameval = self.objname.toPlainText()
        self.nodraval = float(self.nodra.toPlainText())
        self.noddecval = float(self.noddec.toPlainText())
        if self.stopthread:
            self.stopthread = False

        print "####### STARTING NODDING SEQUENCE #######"
        print "# Doing initial calibrations"
        self.scidet.takecalibrations(self.objnameval)

        for i in range(self.NNodsVal):
            for obstype in self.NodSelectionVal:
                if obstype == 'A':
                    #self.guideThread.setObj()
                    #self.guideThread.start()
                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval)
                elif obstype == 'B':
                    #self.guideThread.setSky()
                    #self.guider.moveTelescopeNod(self.nodraval, self.noddecval)
                    #self.guideThread.start()
                    self.scidet.exposeRamp(self.nreadsval, self.nrampsval, 'Ramp', self.objnameval+'Sky')
                    #self.guideThread.setObj()
                    #self.guider.moveTelescopeNod(-1.*self.nodraval, -1.*self.noddecval)
                if self.stopthread:
                    break
                #self.guideThread.stop()
            if self.stopthread:
                break
            if (i + 1) % self.NodsPerCalVal == 0:
                self.scidet.takecalibrations(self.objnameval)
        print "####### FINISHED NODDING SEQUENCE #######"
        

class UpdateLabels(QThread):

    def __init__(self, guider, powercontrol, RALabel, DECLabel, AZLabel, ELLabel, IISLabel, \
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
        self.powercontrol = powercontrol

    def __del__(self):
        self.wait()

    def run(self):

        while True:
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
            self.powercontrol.checkOn()
            self.sleep(2)


def main():

    app = QApplication(sys.argv)  # A new instance of QApplication
    wifis = WIFISUI()                 # We set the form to be our ExampleApp (design)
    wifis.show()                         # Show the form
    app.exec_()                         # and execute the app

if __name__ == '__main__':
    main()
