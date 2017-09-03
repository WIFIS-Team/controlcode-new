from PyQt5.QtWidgets import QApplication, QMainWindow
import sys
from design import Ui_MainWindow
import wifis_guiding as wg

class WIFISUI(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super(WIFISUI, self).__init__()

        self.setupUi(self)
        
        self.telSock = wg.connect_to_telescope()

    def updateTelem(self):
        telemDict = wg.get_telemetry(self.telSock)
        self.RALabel = 




def main():

    app = QApplication(sys.argv)  # A new instance of QApplication
    wifis = WIFISUI()                 # We set the form to be our ExampleApp (design)
    wifis.show()                         # Show the form
    app.exec_()                         # and execute the app

if __name__ == '__main__':
    main()
