from PyQt5.QtWidgets import QApplication, QMainWindow
import sys
from design import Ui_MainWindow
import wifis_guiding as wg
from PyQt5.QtCore import QThread, QTimer


class WIFISUI(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super(WIFISUI, self).__init__()

        self.setupUi(self)
        
        self.telsock = wg.connect_to_telescope()
        
        self.telemThread = TelemetryUpdate(self.telsock, self.RALabel, self.DECLabel, \
                self.AZLabel, self.ELLabel, self.IISLabel, self.HALabel)
        self.telemThread.start()

    #def updateTelem(self):
    #    td = wg.get_telemetry(self.telSock)
    #    self.RALabel.setText(td['RA'])
    #    self.DECLabel.setText(td['DEC'])
    #    self.AZLabel.setText(td['AZ'])
    #    self.ELLabel.setText(td['EL'])
    #    self.IISLabel.setText(td['IIS'])
    #    self.HALabel.setText(td['HA'])


class TelemetryUpdate(QThread):

    def __init__(self, telsock, RALabel, DECLabel, AZLabel, ELLabel, IISLabel, HALabel):
        QThread.__init__(self)
        self.telsock = telsock
        self.RALabel = RALabel
        self.DECLabel = DECLabel
        self.AZLabel = AZLabel
        self.ELLabel = ELLabel
        self.IISLabel = IISLabel
        self.HALabel = HALabel

    def __del__(self):
        self.wait()

    def updatetelem(self):

        td = wg.get_telemetry(self.telsock, verbose=False)

        self.RALabel.setText(td['RA'])
        self.DECLabel.setText(td['DEC'])
        self.AZLabel.setText(td['AZ'])
        self.ELLabel.setText(td['EL'])
        self.IISLabel.setText(td['IIS'])
        self.HALabel.setText(td['HA'])

    def run(self):
        while True:
            self.updatetelem()
            self.sleep(1)

def main():

    app = QApplication(sys.argv)  # A new instance of QApplication
    wifis = WIFISUI()                 # We set the form to be our ExampleApp (design)
    wifis.show()                         # Show the form
    app.exec_()                         # and execute the app

if __name__ == '__main__':
    main()
