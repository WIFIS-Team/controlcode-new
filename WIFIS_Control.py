from PyQt5.QtWidgets import QApplication, QMainWindow
import sys
from wifis import Ui_MainWindow
import wifis_guiding as wg
import WIFISdetector as wd
import power_control as pc
from PyQt5.QtCore import QThread
import guiding_functions as gf

class WIFISUI(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super(WIFISUI, self).__init__()

        self.setupUi(self)
       
        #Defining various control/serial variables
        try:
            self.telSock = wg.connect_to_telescope()
            self.switch1, self.switch2 = pc.connect_to_power()
            self.scidet = wd.h2rg()
            self.cam, self.foc, self.flt = gf.load_FLIDevices()
        except:
            print "Something isn't connecting properly"
            return False 

        self.guidedirec, self.todaydate = gf.initGuideFolder()

        #Starting function to update labels. Still need to add guider info.
        self.labelsThread = UpdateLabels(self.telSock, self.RALabel, self.DECLabel,\
                self.AZLabel, self.ELLabel, self.IISLabel, self.HALabel, self.cam, \
                self.foc, self.CCDTemp,self.FocPosition)
        self.labelsThread.start()

        #Defining actions for Exposure Control
        self.actionConnect.triggered.connect(self.scidet.connect)
        self.actionInitialize.triggered.connect(self.scidet.initialize)
        self.actionDisconnect.triggered.connect(self.scidet.disconnect)
        
        #Defining actions for Guider Control
        self.GuiderMoveButton.triggered.connect(gf.offsetToGuider(self.telSock))
        self.WIFISMoveButton.triggered.connect(gf.offsetToWIFIS(self.telSock))
        self.moveTelescopeButton.triggered.connect(gf.moveTelescope(self.telSock,\
                self.RAMoveBot.toPlainText(), self.DECMoveBox.toPlainText()))
        self.BKWButton.triggred.connect(gf.stepBackward(self.foc, self.focStep))
        self.FWDButton.triggered.connect(gf.stepForward(self.foc, self.focStep))
        

class UpdateLabels(QThread):

    def __init__(self, telsock, RALabel, DECLabel, AZLabel, ELLabel, IISLabel, \
            HALabel, cam, foc, ccdTemp, focpos):
        QThread.__init__(self)

        self.telsock = telsock
        self.RALabel = RALabel
        self.DECLabel = DECLabel
        self.AZLabel = AZLabel
        self.ELLabel = ELLabel
        self.IISLabel = IISLabel
        self.HALabel = HALabel
        self.cam = cam
        self.foc = foc
        self.ccdTemp = ccdTemp
        self.focpos = focpos

    def __del__(self):
        self.wait()

    def run(self):

        while True:
            telemDict = wg.get_telemetry(self.telsock, verbose=False)

            self.RALabel.setText(telemDict['RA'])
            self.DECLabel.setText(telemDict['DEC'])
            self.AZLabel.setText(telemDict['AZ'])
            self.ELLabel.setText(telemDict['EL'])
            self.IISLabel.setText(telemDict['IIS'])
            self.HALabel.setText(telemDict['HA'])
            gf.getCCDTemp(self.cam, self.ccdTemp)            
            gf.writeStepNum(self.foc, self.focpos)

            self.sleep(3)


def main():

    app = QApplication(sys.argv)  # A new instance of QApplication
    wifis = WIFISUI()                 # We set the form to be our ExampleApp (design)
    wifis.show()                         # Show the form
    app.exec_()                         # and execute the app

if __name__ == '__main__':
    main()
