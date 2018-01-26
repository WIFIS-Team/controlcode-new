import wifisIO
import numpy as np
import os
from DoFieldRec import procScienceDataGUI
from PyQt5.QtCore import QObject, pyqtSignal
from astropy import wcs
import astropy.io as aio

os.environ['PYOPENCL_CTX'] = '0' # Used to specify which OpenCL device to target. Should be uncommented and pointed to correct device to avoid future interactive requests

#****************************************************************************************
#REQUIRED INPUT FILES
waveLstFile = 'wave.lst'
flatLstFile = 'flat.lst'
obsLstFile = 'obs.lst'

hband = False
colorbarLims = [0,10]
varFile = '/home/utopea/WIFIS-Team/wifiscontrol/wifisConfig.inp'
#****************************************************************************************

class get_src_pos(QObject):

    plotField = pyqtSignal(list)
    #plotField = pyqtSignal(np.ndarray, wcs.wcs.WCS, aio.fits.header.Header)

    def __init__(self, waveLstFile, flatLstFile, obsLstFile):
        super(get_src_pos, self).__init__()
        
        self.waveLstFile = waveLstFile
        self.flatLstFile = flatLstFile
        self.obsLstFile = obsLstFile

    def doFieldRec(self):
        waveLst = wifisIO.readAsciiList(self.waveLstFile)
        if waveLst.ndim==0:
            waveLst = np.asarray([waveLst])

        flatLst = wifisIO.readAsciiList(self.flatLstFile)    
        if flatLst.ndim == 0:
            flatLst = np.asarray([flatLst])

        obsLst = wifisIO.readAsciiList(self.obsLstFile)
        if obsLst.ndim == 0:
            obsLst = np.asarray([obsLst])

        #quickReduction.initPaths()
        for fle in range(len(obsLst)):
            dataImg, WCS, hdr, gFit, xScale, yScale = procScienceDataGUI(obsLst[fle], flatLst[fle], varFile = varFile, scaling='')

        returns = [dataImg, WCS, hdr, gFit, xScale, yScale]
        self.plotField.emit(returns)


if __name__ == '__main__':
    do_get_src_pos('/home/utopea/WIFIS-Team/wifiscontrol/wave.lst','/home/utopea/WIFIS-Team/wifiscontrol/flat.lst','/home/utopea/WIFIS-Team/wifiscontrol/obs.lst')
