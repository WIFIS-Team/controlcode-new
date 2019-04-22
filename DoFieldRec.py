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

def procArcDataGUI(waveFolder, flatFolder, hband=False, colorbarLims = None, varFile='', noPlot=False):
    """
    Routine to quickly process the raw data from an arc lamp/wavelength correction ramp and plot the resulting FWHM map across each slice
    Usage: procArcData(waveFolder, flatFolder, hband=False, colorbarLims = None, varFile='')
    waveFolder is the ramp folder to be processed
    flatFolder is the flat field ramp folder associated with waveFolder
    hband is a boolean keyword to specify if the ramp used the h-band filter (and thus does not span the entire detector)
    colorbarLims is a keyword that allows one to specify the limits to use when plotting the FWHM map. If set to None, the default method uses z-scaling
    varFile is the name of the input configuration file.
    """

    #initialize variables using configuration file
    varInp = wifisIO.readInputVariables(varFile)
    for var in varInp:
        globals()[var[0]]=var[1]    

    #execute pyOpenCL section here
    os.environ['PYOPENCL_COMPILER_OUTPUT'] = pyCLCompOut

    if len(pyCLCTX)>0:
        os.environ['PYOPENCL_CTX'] = pyCLCTX 

    wifisIO.createDir('quick_reduction')

    #read in previous results and template
    template = wifisIO.readImgsFromFile(waveTempFile)[0]
    prevResults = wifisIO.readPickle(waveTempResultsFile)
    prevSol = prevResults[5]

    if os.path.exists(distMapFile) and os.path.exists(spatGridPropsFile):
        distMap = wifisIO.readImgsFromFile(distMapFile)[0]
        spatGridProps = wifisIO.readTable(spatGridPropsFile)
    else:
        distMap = None
        spatGridProps = None
        
    if os.path.exists(satFile):
        satCounts = wifisIO.readImgsFromFile(satFile)[0]
    else:
        satCounts = None
    if os.path.exists(bpmFile):
        bpm = wifisIO.readImgsFromFile(bpmFile)[0]
    else:
        bpm = None
        
    if (os.path.exists('quick_reduction/'+waveFolder+'_wave_fwhm_map.png') and os.path.exists('quick_reduction/'+waveFolder+'_wave_fwhm_map.fits') and os.path.exists('quick_reduction/'+waveFolder+'_wave_wavelength_map.fits')):
        print('*** ' + waveFolder + ' arc/wave data already processed, skipping ***')
    else:
        wave, hdr,obsinfo = wifisqr.procRamp(waveFolder, satCounts=satCounts, bpm=bpm, saveName='quick_reduction/'+waveFolder+'_wave.fits',varFile=varFile)
    
        if (os.path.exists('quick_reduction/'+flatFolder+'_flat_limits.fits') and os.path.exists('quick_reduction/'+flatFolder+'_flat_slices.fits')):
            limits, limitsHdr = wifisIO.readImgsFromFile('quick_reduction/'+flatFolder+'_flat_limits.fits')
            flatSlices,flatHdr = wifisIO.readImgsFromFile('quick_reduction/'+flatFolder+'_flat_slices.fits')
            shft = limitsHdr['LIMSHIFT']
        else:
            print('Processing flat file')
            flat, flatHdr, obsinfo = wifisqr.procRamp(flatFolder, satCounts=satCounts, bpm=bpm, saveName='quick_reduction/'+flatFolder+'_flat.fits',varFile=varFile)

            print('Finding flat limits')
            limits = slices.findLimits(flat, dispAxis=0, winRng=51, imgSmth=5, limSmth=20,rmRef=True, centGuess=centGuess)
            if os.path.exists(distMapLimitsFile):
                distMapLimits = wifisIO.readImgsFromFile(distMapLimitsFile)[0]
                shft = int(np.nanmedian(limits[1:-1,:] - distMapLimits[1:-1,:]))
                limits = distMapLimits
            else:
                print(colorama.Fore.RED+'*** WARNING: NO LIMITS FILE ASSOCIATED WITH THE DISTORTION MAP PROVIDED, USING LIMITS DETERMINED FROM FLATS ONLY ***'+colorama.Style.RESET_ALL)
                shft = 0

            flatSlices = slices.extSlices(flat[4:-4, 4:-4], limits, shft=shft)
            flatHdr.set('LIMSHIFT',shft, 'Limits shift relative to Ronchi slices')
            wifisIO.writeFits(limits,'quick_reduction/'+flatFolder+'_flat_limits.fits',hdr=flatHdr, ask=False)
            wifisIO.writeFits(flatSlices,'quick_reduction/'+flatFolder+'_flat_slices.fits', ask=False)
                
        print('Extracting wave slices')
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", "RuntimeWarning")
            waveSlices = slices.extSlices(wave[4:-4,4:-4], limits, dispAxis=0, shft=shft)

        print('Getting normalized wave slices')
        if hband:
            flatNorm = slices.getResponseAll(flatSlices, 0, 0.6)
        else:
            flatNorm = slices.getResponseAll(flatSlices, 0, 0.1)

        if distMap is None:
            print(colorama.Fore.RED+'*** WARNING: NO DISTORTION MAP PROVIDED, ESTIMATING FROM FLAT FIELD SLICES ***'+colorama.Style.RESET_ALL)

            flatSlices = wifisIO.readImgsFromFile('quick_reduction/'+flatFolder+'_flat_slices.fits')[0]
            distMap, spatGridProps = wifisqr.makeFakeDistMap(flatSlices)

        print ('Getting distortion corrected slices')
        waveCor = createCube.distCorAll_CL(waveSlices, distMap, spatGridProps=spatGridProps)

        #save data
        wifisIO.writeFits(waveCor, 'quick_reduction/'+waveFolder+'_wave_slices_distCor.fits', ask=False)
        print('Getting dispersion solution')

        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            
            result = waveSol.getWaveSol(waveCor, template, atlasFile,mxOrder, prevSol, winRng=waveWinRng, mxCcor=waveMxCcor, weights=False, buildSol=False, sigmaClip=sigmaClip, allowLower=False, lngthConstraint=False, MP=True, adjustFitWin=True, sigmaLimit=sigmaLimit, allowSearch=False, sigmaClipRounds=sigmaClipRounds)        
       
        print('Extracting solution results')
        dispSolLst = result[0]
        fwhmLst = result[1]
        pixCentLst = result[2]
        waveCentLst = result[3]
        rmsLst = result[4]
        pixSolLst = result[5]

        print('Building maps of results')
        npts = waveSlices[0].shape[1]
        waveMapLst = waveSol.buildWaveMap(dispSolLst,npts)

        for fwhm in fwhmLst:
            for i in range(len(fwhm)):
                fwhm[i] = np.abs(fwhm[i])
        
        fwhmMapLst = waveSol.buildFWHMMap(pixCentLst, fwhmLst, npts)
        #get max and min starting wavelength based on median of central slice (slice 8)

        if hband:
            trimSlc = waveSol.trimWaveSlice([waveMapLst[8], flatSlices[8], 0.5])
            waveMin = np.nanmin(trimSlc)
            waveMax = np.nanmax(trimSlc)
        else:
            trimSlc = waveMapLst[8]
            waveMax = np.nanmedian(trimSlc[:,0])
            waveMin = np.nanmedian(trimSlc[:,-1])
 
        print('*******************************************************')
        print('*** Minimum median wavelength for slice 8 is ' + str(waveMin)+ ' ***')
        print('*** Maximum median wavelength for slice 8 is ' + str(waveMax)+ ' ***')
        print('*******************************************************')

        
        #determine length along spatial direction
        ntot = 0
        for j in range(len(rmsLst)):
            ntot += len(rmsLst[j])

        #get median FWHM
        fwhmAll = []
        for f in fwhmLst:
            for i in range(len(f)):
                for j in range(len(f[i])):
                    fwhmAll.append(f[i][j])
            
        fwhmMed = np.nanmedian(fwhmAll)
        print('**************************************')
        print('*** MEDIAN FWHM IS '+ str(fwhmMed) + ' ***')
        print('**************************************')

        #build "detector" map images
        #wavelength solution
        waveMap = np.empty((npts,ntot),dtype='float32')
        strt=0
        for m in waveMapLst:
            waveMap[:,strt:strt+m.shape[0]] = m.T
            strt += m.shape[0]

        #fwhm map
        fwhmMap = np.empty((npts,ntot),dtype='float32')
        strt=0
        for f in fwhmMapLst:
            fwhmMap[:,strt:strt+f.shape[0]] = f.T
            strt += f.shape[0]

        #save results
        hdr.set('QC_WMIN',waveMin,'Minimum median wavelength for middle slice')
        hdr.set('QC_WMAX',waveMax,'Maximum median wavelength for middle slice')
        hdr.set('QC_WFWHM', fwhmMed, 'Median FWHM of all slices')

        wifisIO.writeFits(waveMap, 'quick_reduction/'+waveFolder+'_wave_wavelength_map.fits', ask=False,hdr=hdr)
        wifisIO.writeFits(fwhmMap, 'quick_reduction/'+waveFolder+'_wave_fwhm_map.fits', ask=False,hdr=hdr)

    return [fwhmMap, fwhmMed, waveMin, waveMax]

        #print('plotting results')
        #fig = plt.figure()

        #if colorbarLims is None:
        #    interval=ZScaleInterval()
        #    lims=interval.get_limits(fwhmMap)
        #else:
        #    lims = colorbarLims



        #plt.imshow(fwhmMap, aspect='auto', cmap='jet', clim=lims, origin='lower')
        #plt.colorbar()
        #plt.title('Median FWHM is '+'{:3.1f}'.format(fwhmMed) +', min wave is '+'{:6.1f}'.format(waveMin)+', max wave is '+'{:6.1f}'.format(waveMax))
        #plt.tight_layout()
        #plt.savefig('quick_reduction/'+waveFolder+'_wave_fwhm_map.png', dpi=300)
        #if not noPlot:
        #    plt.show()
        #plt.close()

