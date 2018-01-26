import wifisIO
import numpy as np
import wifisSlices as slices
import wifisCreateCube as createCube
import wifisHeaders as headers
from astropy import wcs 
import os
from astropy.modeling import models, fitting
import glob
import warnings
from wifisIO import sorted_nicely
import wifisWaveSol as waveSol
import wifisProcessRamp as processRamp
import wifisSpatialCor as spatialCor
from astropy.visualization import ZScaleInterval
from scipy.optimize import curve_fit
import wifisQuickReduction as wifisqr

import colorama


def procScienceDataGUI(rampFolder='', flatFolder='', noProc=False, skyFolder=None, pixRange=None, varFile='',scaling='zscale', colorbar=False):
    """
    Routine to quickly process the raw data from a science ramp and plot a 2D collapse of the final image cube
    Usage procScienceData(rampFolder='', flatFolder='', noProc=False, skyFolder=None, pixRange=None, varFile='',scaling='zscale')
    rampFolder is the folder name of the observation to process and plot
    flatFolder is the corresponding flat field observation associated with rampFolder
    noProc is a boolean keyword used to indicate if the ramp image should be computed using the pipeline (but skipping non-linearity and reference corrections) (False) or if the ramp image should be found in a simple manner using the first and last images (True). The latter option does not handle saturation well, which is handled with the usual pipeline method if False.
    skyFolder is an optional keyword to specify the name of an associated sky ramp folder
    pixRange is an optional list containing the first and last pixel in a range (along the dispersion axis) of pixels to use for creating the ramp image.
    varFile is the name of the configuration file
    scaling is a keyword that specifies the type of image scaling to use for plotting the final image. If set to "zscale", z-scaling is used. Anything else will set the scale to min-max scaling.
    """

    #initialize variables using configuration file
    varInp = wifisIO.readInputVariables(varFile)
    for var in varInp:
        globals()[var[0]]=var[1]    

    #execute pyOpenCL section here
    os.environ['PYOPENCL_COMPILER_OUTPUT'] = pyCLCompOut

    if len(pyCLCTX)>0:
        os.environ['PYOPENCL_CTX'] = pyCLCTX 

    if os.path.exists(satFile):
        satCounts = wifisIO.readImgsFromFile(satFile)[0]
    else:
        satCounts = None

    if os.path.exists(bpmFile):
        bpm = wifisIO.readImgsFromFile(bpmFile)[0]
    else:
        bpm = None
        
    wifisIO.createDir('quick_reduction')

    #process science data
    if noProc:
        print('Attempting to process science and sky (if exists) ramps without usual processing')

    fluxImg, hdr, obsinfoFile = wifisqr.procRamp(rampFolder, noProc=noProc, satCounts=satCounts, bpm=bpm, saveName='quick_reduction/'+rampFolder+'_obs.fits',varFile=varFile)

    #now process sky, if it exists
       
    if (skyFolder is not None):
        skyImg, hdrSky, skyobsinfo = wifisqr.procRamp(skyFolder,noProc=noProc, satCounts=satCounts, bpm=bpm, saveName='quick_reduction/'+skyFolder+'_sky.fits',varFile=varFile)
        
        #subtract
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            fluxImg -= skyImg

    fluxImg = fluxImg[4:-4, 4:-4]

    #first check if limits already exists
    if os.path.exists('quick_reduction/'+flatFolder+'_limits.fits'):
        limitsFile = 'quick_reduction/'+flatFolder+'_limits.fits'
        limits = wifisIO.readImgsFromFile(limitsFile)[0]
    else:
        flat, hdrFlat, hdrobsinfo = wifisqr.procRamp(flatFolder, noProc=False, satCounts=satCounts, bpm=bpm, saveName='quick_reduction/'+flatFolder+'_flat.fits',varFile=varFile)
        
        print('Getting slice limits')
        limits = slices.findLimits(flat, dispAxis=0, rmRef=True,centGuess=centGuess)
        wifisIO.writeFits(limits, 'quick_reduction/'+flatFolder+'_limits.fits', ask=False)

    if os.path.exists(distMapLimitsFile):
        #get ronchi slice limits
        distLimits = wifisIO.readImgsFromFile(distMapLimitsFile)[0]

        #determine shift
        shft = np.median(limits[1:-1, :] - distLimits[1:-1,:])
    else:
        print(colorama.Fore.RED+'*** WARNING: NO DISTORTION MAP LIMITS PROVIDED. LIMITS ARE DETERMINED ENTIRELY FROM THE FLAT FIELD DATA ***'+colorama.Style.RESET_ALL)
        shft = 0
        distLimits = limits
        
    print('Extracting slices')
    dataSlices = slices.extSlices(fluxImg, distLimits, dispAxis=0, shft=shft)

    #place on uniform spatial grid
    print('Distortion correcting')
    if not os.path.exists(distMapLimitsFile) or not os.path.exists(distMapFile) or not os.path.exists(spatGridPropsFile):
        print(colorama.Fore.RED+'*** WARNING: NO DISTORTION MAP PROVIDED, ESTIMATING DISTORTION MAP FROM SLICE SHAPE ***'+colorama.Style.RESET_ALL)
        #read flat image from file and extract slices
        flat,flatHdr = wifisIO.readImgsFromFile('quick_reduction/'+flatFolder+'_flat.fits')
        flatSlices = slices.extSlices(flat[4:-4,4:-4], limits)
        #get fake distMap and grid properties
        distMap, spatGridProps = wifisqr.makeFakeDistMap(flatSlices)
    else:
        distMap = wifisIO.readImgsFromFile(distMapFile)[0]
        spatGridProps = wifisIO.readTable(spatGridPropsFile)

    dataGrid = createCube.distCorAll(dataSlices, distMap, spatGridProps=spatGridProps)

    #create cube
    print('Creating image')
    dataCube = createCube.mkCube(dataGrid, ndiv=1, missing_left=missing_left_slice, missing_right=missing_right_slice)

    #create output image
    if pixRange is not None:
        dataImg = np.nansum(dataCube[:,:,pixRange[0]:pixRange[1]],axis=2)
    else:
        dataImg = createCube.collapseCube(dataCube)

    print('Computing FWHM')
    #fit 2D Gaussian to image to determine FWHM of star's image
    y,x = np.mgrid[:dataImg.shape[0],:dataImg.shape[1]]
    cent = np.unravel_index(np.nanargmax(dataImg),dataImg.shape)
    gInit = models.Gaussian2D(np.nanmax(dataImg), cent[1],cent[0])
    fitG = fitting.LevMarLSQFitter()
    gFit = fitG(gInit, x,y,dataImg)

    if noProc:
        #fill in header info
        headers.addTelInfo(hdr, obsinfoFile, obsCoords=obsCoords)

    #save distortion corrected slices
    wifisIO.writeFits(dataGrid, 'quick_reduction/'+rampFolder+'_quickRed_slices_grid.fits', hdr=hdr, ask=False)

    headers.getWCSImg(dataImg, hdr, xScale, yScale)
    
    #save image
    wifisIO.writeFits(dataImg, 'quick_reduction/'+rampFolder+'_quickRedImg.fits', hdr=hdr, ask=False)

    #plot the data
    WCS = wcs.WCS(hdr)

    return dataImg, WCS, hdr, gFit, xScale, yScale



