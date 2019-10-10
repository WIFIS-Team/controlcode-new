import matplotlib.pyplot as mpl
import numpy as np
import urllib as url
from astropy.io import fits
from scipy.optimize import curve_fit
from astropy import units as u
from astropy.coordinates import SkyCoord
import WIFIStelescope as WG
from sys import exit
from scipy.stats import mode
from numpy.linalg import inv
import traceback
import time

from PyQt5.QtCore import QThread, QCoreApplication, QTimer, pyqtSlot, pyqtSignal

plate_scale = 0.29125
#flength = 9206.678
flength = 9207.218

class Formatter(object):
    def __init__(self, im):
        self.im = im
    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
        return 'x={:.01f}, y={:.01f}, z={:.01f}'.format(x, y, z)

def read_defaults():

    f = open('/home/utopea/WIFIS-Team/wifiscontrol/defaultvalues.txt','r')
    #f = open('/Users/relliotmeyer/WIFIS-Team/wifiscontrol/defaultvalues.txt','r')
    valuesdict = {}
    for line in f:
        spl = line.split()
        valuesdict[spl[0]] = spl[1]
    f.close()

    return valuesdict

def getAstrometricSoln(fl, telSock, rotangleget, verbose = False, catalog = 'sdss'):
    """Takes an ra and dec as grabbed from the telemetry and returns a field
    from UNSO for use in solving the guider field"""

    data, head, RA, DEC, centroids = load_img(fl, telSock)
    if type(fl) != str:
        head['IIS'] = rotangleget
    print "Number of stars in image: "+str(len(centroids[0]))

    xorig = np.array(centroids[0])
    yorig = np.array(centroids[1])
    Iarr = np.array(centroids[2])

    yorigflip = -1*(yorig - 1024)
    rotangle = float(head['IIS'])

    valuesdict = read_defaults()
    guider_offsets = [float(valuesdict['GuideRA']), float(valuesdict['GuideDEC'])]
    
    coord = SkyCoord(RA, DEC, unit=(u.hourangle, u.deg))
    ra_deg = coord.ra.deg
    dec_deg = coord.dec.deg

    offsets = get_rotation_solution_offset(rotangle, guider_offsets, dec_deg)

    name, rad, ded, rmag, ra_deg, dec_deg, fov_am ,coord, newcoord, newcatalog = grabUNSOfield(RA, DEC, offsets=offsets, catalog = catalog)
    catalog = newcatalog

    cxrot, cyrot, cxrotneg, cyrotneg = rotate_points(rotangle,xorig,yorig)

    cyrotneg_flip = -1*(np.array(cyrotneg) - 1024)
    x = np.array(cxrotneg)
    y = np.array(cyrotneg_flip)
    #y = np.array(cyrotneg)

    xproj, yproj,X,Y = projected_coords(rad, ded, ra_deg, dec_deg)

    xproj = np.array(xproj)
    yproj = np.array(yproj)


    if len(rmag[np.isnan(rmag)]) > len(rmag)/2.: 
        k = rmag != 0
        print 'lots of nan'
    elif catalog == 'unso':
        magval = 17.5
        k = rmag < magval
    elif catalog == 'sdss':
        magval = 20
        k = rmag < magval

    #compareresults = compareFieldsNew(x, y, xproj, yproj, rad, ded, k)
    compareresults = compareFields3(x, y, xproj, yproj, rad, ded, k, Iarr)

    if compareresults == None:
        return [False]
    else:
        xmatch, ymatch, xprojmatch, yprojmatch, ramatch, decmatch, xdist, ydist,disti, posi = compareresults

    disti = np.array(disti)

    Xmatch = []
    Ymatch = []
    for i in disti:
        Xmatch.append(X[k][i])
        Ymatch.append(Y[k][i])
    Xmatch = np.array(Xmatch)
    Ymatch = np.array(Ymatch)

    xorigmatch = []
    yorigmatch = []
    for i in posi:
        xorigmatch.append(xorig[i])
        yorigmatch.append(yorigflip[i])
    xorigmatch = np.array(xorigmatch)
    yorigmatch = np.array(yorigmatch) 
    
    platesolve = solvePlate(xorigmatch,yorigmatch,Xmatch,Ymatch)

    if not platesolve:
        print "NO SOLVE"
        return [False]
    elif platesolve == 'Offsets':
        print "TOO FEW STARS"
        print xorig
        print yorig
        return [xdist, ydist]
    else:
        print "Solved"
        xsolve = platesolve[0]
        ysolve = platesolve[1]

        #print xmatch, ymatch
        print xsolve
        print ysolve
        #print rotangle - 90. - 0.26
        #print np.arccos(xsolve[0] * flength / 0.013) * 180. / np.pi
        #print 0.013 / np.sqrt(np.abs(xsolve[0]*ysolve[1] - xsolve[1]*ysolve[0]))
        #print

        Xnew = (flength * (xsolve[0]*xmatch + xsolve[1]*ymatch + xsolve[2]) / 0.013) + 512
        Ynew = (flength * (ysolve[0]*xmatch + ysolve[1]*ymatch + ysolve[2]) / 0.013) + 512

        decdegrad = dec_deg*np.pi/180.
        Xcen, Ycen = returnXY(platesolve, 512, 512)

        ra_cen = ra_deg + np.arctan(-Xcen/(np.cos(decdegrad) - (Ycen*np.sin(decdegrad))))*180/np.pi
        dec_cen = np.arcsin((np.sin(decdegrad) + Ycen*np.cos(decdegrad))/ \
                (np.sqrt(1 + Xcen**2. + Ycen**2)))*180/np.pi

        #print ra_cen, dec_cen
        #print newcoord.ra, newcoord.dec
        solvecenter = SkyCoord(ra_cen, dec_cen, unit='deg')
        #print "Guessed: ", newcoord.ra.hms, newcoord.dec.dms
        #print "Solved: ", solvecenter.ra.hms, solvecenter.dec.dms

        fieldoffset = solvecenter.spherical_offsets_to(newcoord)
        realcenter = [ra_cen, dec_cen]

        name, rad, ded, rmag, ra_deg, dec_deg, fov_am ,ncoord, nnewcoord, newcatalog = grabUNSOfield(ra_cen, dec_cen, offsets=False\
              ,deg=True, catalog= catalog)
        xproj, yproj,X,Y = projected_coords(rad, ded, ra_cen, dec_cen)

        xproj = np.array(xproj)
        yproj = np.array(yproj)

        #mpl.plot(x,y, 'r*')
        k = rmag < magval
        #mpl.plot(xproj[k], yproj[k],'b.')
        #mpl.show()
        
        if verbose:
            return [platesolve, fieldoffset, realcenter, solvecenter, offsets,[x,y,k,xproj,yproj,data,head,coord],[xorig, yorig, cxrot, cyrot, cxrotneg, cyrotneg, Iarr]]
        else:
            return [platesolve, fieldoffset, realcenter, solvecenter, offsets,[x,y,k,xproj,yproj,data,head,coord]]

def returnXY(platesolve, x, y):

    xsolve = platesolve[0]
    ysolve = platesolve[1]

    Xnew = xsolve[0]*x + xsolve[1]*y + xsolve[2]
    Ynew = ysolve[0]*x + ysolve[1]*y + ysolve[2]

    return Xnew, Ynew

def returnRADEC(X,Y,radeg, decdeg):

    decdegrad = decdeg * np.pi / 180.

    ra_solve = radeg + np.arctan(-X/(np.cos(decdegrad) - (Y*np.sin(decdegrad))))*180/np.pi
    dec_solve = np.arcsin((np.sin(decdegrad) + Y*np.cos(decdegrad))/(np.sqrt(1 + X**2. + Y**2)))*180/np.pi

    return ra_solve, dec_solve

def compareFields(x, y, xp, yp,rad, ded, k):

    distsi = []
    dists = []
    xdists = []
    ydists = []
    
    for i in range(len(x)):
        Xdist = xp[k] - x[i]
        Ydist = yp[k] - y[i]

        dist = np.sqrt(Xdist**2 + Ydist**2)

        distsi.append(np.argmin(dist))
        dists.append(dist[distsi[i]])
        xdists.append(Xdist[distsi[i]])
        ydists.append(Ydist[distsi[i]])

    if len(dists) < 3:
        med = np.min(dists)
    elif (len(dists) % 2) == 0:
        mediumind = len(dists) / 2
        med = np.sort(dists)[mediumind]
    else:
        med = np.median(dists)

    w = np.where(dists == med)[0]

    xdist = np.array(xdists)[w]
    ydist = np.array(ydists)[w]

    xnew = x + xdist
    ynew = y + ydist

    xmatch = []
    ymatch = []
    Xmatch = []
    Ymatch = []
    ramatch = []
    decmatch = []
    distsi = []
    distsimatch = []
    posi = []

    for i in range(len(xnew)):
        Xdist = xp[k] - xnew[i]
        Ydist = yp[k] - ynew[i]

        dist = np.sqrt(Xdist**2 + Ydist**2)
        mini = np.argmin(dist)

        distsi.append(mini)

        if dist[mini] < 5:
            distsimatch.append(mini)
            posi.append(i)
            xmatch.append(x[i])
            ymatch.append(y[i])
            Xmatch.append(xp[k][mini])
            Ymatch.append(yp[k][mini])
            ramatch.append(rad[k][mini])
            decmatch.append(ded[k][mini])

    return np.array(xmatch), np.array(ymatch), np.array(Xmatch), np.array(Ymatch), \
            np.array(ramatch), np.array(decmatch), xdist, ydist, distsimatch, posi

def compareFieldsNew(x, y, xp, yp,rad, ded, k):

    distsi = []
    dists = []
    xdists = []
    ydists = []
    
    for i in range(len(x)):
        Xdist = xp[k] - x[i]
        Ydist = yp[k] - y[i]

        dist = np.sqrt(Xdist**2 + Ydist**2)
        amdist = np.argmin(dist)

        distsi.append(amdist)
        dists.append(dist[amdist])
        xdists.append(Xdist[amdist])
        ydists.append(Ydist[amdist])

    nsmalls = []
    for j in range(len(xdists)):
        xnew = x + xdists[j]
        ynew = y + ydists[j]

        sumdist = 0
        nsmall = 0
        mindists = []
        for i in range(len(xnew)):
            Xdist = np.abs(xp[k] - xnew[i])
            Ydist = np.abs(yp[k] - ynew[i])
            dist = np.sqrt(Xdist**2. + Ydist**2.)
            mini = np.argmin(dist)

            if (Xdist[mini] < 15) and (Ydist[mini] < 15):
                nsmall += 1
            sumdist += dist[mini]
            mindists.append(dist[mini])
        nsmalls.append(nsmall)
    if len(nsmalls) == 0:
        return None

    amnsmall = np.argmax(nsmalls)

    xdist = xdists[amnsmall]
    ydist = ydists[amnsmall]

    xnew = x + xdist
    ynew = y + ydist

    xmatch = []
    ymatch = []
    Xmatch = []
    Ymatch = []
    ramatch = []
    decmatch = []
    distsi = []
    distsimatch = []
    posi = []

    for i in range(len(xnew)):
        Xdist = np.abs(xp[k] - xnew[i])
        Ydist = np.abs(yp[k] - ynew[i])

        dist = np.sqrt(Xdist**2 + Ydist**2)
        mini = np.argmin(dist)

        distsi.append(mini)

        if (Xdist[mini] < 15) and (Ydist[mini] < 15):
            distsimatch.append(mini)
            posi.append(i)
            xmatch.append(x[i])
            ymatch.append(y[i])
            Xmatch.append(xp[k][mini])
            Ymatch.append(yp[k][mini])
            ramatch.append(rad[k][mini])
            decmatch.append(ded[k][mini])

    return np.array(xmatch), np.array(ymatch), np.array(Xmatch), np.array(Ymatch), \
            np.array(ramatch), np.array(decmatch), xdist, ydist, distsimatch, posi
            
def compareFields3(x, y, xp, yp,rad, ded, k, Iarr):

    brighti = np.argsort(Iarr)[::-1]
    if len(brighti) > 5:
        xb = x[brighti[:5]]
        yb = y[brighti[:5]]
    else:
        xb = x
        yb = y

    distsi = []
    dists = []
    xdists = []
    ydists = []
    
    nsmalls_total = []
    nsmalls_max = []
    nsmalls_imax = []
    #Loop over brightest stars
    for i in range(len(xb)):
        #Calculate distance to each catalog star
        Xdist = xp[k] - xb[i]
        Ydist = yp[k] - yb[i]

        dist = np.sqrt(Xdist**2 + Ydist**2)
        amdist = np.argsort(dist)

        distsi.append(amdist)
        dists.append(dist[amdist])
        xdists.append(Xdist[amdist])
        ydists.append(Ydist[amdist])

        nsmalls = []
        #Loops through each catalog star distance
        for l in range(len(Xdist[amdist])):
            xnew = x + Xdist[amdist][l]
            ynew = y + Ydist[amdist][l]

            nsmall = 0
            for j in range(len(xp[k])):
                Xdistnew = np.abs(xp[k][j] - xnew)
                Ydistnew = np.abs(yp[k][j] - ynew)
                dist = np.sqrt(Xdistnew**2. + Ydistnew**2.)
                mini = np.argmin(dist)

                if (Xdistnew[mini] < 15) and (Ydistnew[mini] < 15):
                    nsmall += 1
            nsmalls.append(nsmall)

        nsmalls_max.append(np.max(nsmalls))
        nsmalls_imax.append(np.argmax(nsmalls))

        nsmalls_total.append(nsmalls)

    supermax = np.argmax(nsmalls_max)
    superimax = nsmalls_imax[supermax]
    xdist = xdists[supermax][superimax]
    ydist = ydists[supermax][superimax]

    xnew = x + xdist
    ynew = y + ydist

    xmatch = []
    ymatch = []
    Xmatch = []
    Ymatch = []
    ramatch = []
    decmatch = []
    distsi = []
    distsimatch = []
    posi = []

    for i in range(len(xnew)):
        Xdist = np.abs(xp[k] - xnew[i])
        Ydist = np.abs(yp[k] - ynew[i])

        dist = np.sqrt(Xdist**2 + Ydist**2)
        mini = np.argmin(dist)

        distsi.append(mini)

        if (Xdist[mini] < 15) and (Ydist[mini] < 15):
            distsimatch.append(mini)
            posi.append(i)
            xmatch.append(x[i])
            ymatch.append(y[i])
            Xmatch.append(xp[k][mini])
            Ymatch.append(yp[k][mini])
            ramatch.append(rad[k][mini])
            decmatch.append(ded[k][mini])

    return np.array(xmatch), np.array(ymatch), np.array(Xmatch), np.array(Ymatch), \
            np.array(ramatch), np.array(decmatch), xdist, ydist, distsimatch, posi

def solvePlate(x,y, X, Y):

    #Get number of matches/degrees of freedom
    #If one star is a match just take the calculated offsets with a warning.
    #If less than 6 stars then maybe just solve for the offsets with a warning
    #If more than 6 stars then do the full plate solution.

    ndf = len(x)

    if ndf >= 3:
        print "THERE ARE ", ndf, "STARS"
        ones = np.ones(ndf)
        A_t = np.array([x,y,ones])
        A = np.transpose(A_t)
        
        A_tA = np.dot(A_t, A)
        A_tA_inv = inv(A_tA)

        f1 = np.dot(A_tA_inv, A_t)
        finalX = np.dot(f1,np.transpose(X))
        finalY = np.dot(f1,np.transpose(Y))

        return finalX, finalY
        
    elif ndf > 0:
        return "Offsets"
    else:
        return False

def grabUNSOfield(RA, DEC, offsets=False, deg = False, catalog = 'unso'):
    """Takes an ra and dec as grabbed from the telemetry and returns a field
    from UNSO for use in solving the guider field"""
    
    if deg:
        coord = SkyCoord(RA, DEC, unit='deg')
    else:
        coord = SkyCoord(RA, DEC, unit=(u.hourangle, u.deg))

    ra_deg = coord.ra.deg
    dec_deg = coord.dec.deg

    if type(offsets) != bool:
        ra_deg -= (offsets[0]/3600. / np.cos(dec_deg * np.pi / 180.))
        dec_deg -= offsets[1]/3600.

    newcoord = SkyCoord(ra_deg, dec_deg, unit='deg')

    fov_am = 5
    if catalog == 'unso':
        name, rad, ded, rmag = unso(ra_deg,dec_deg, fov_am)
    else:
        name, rad, ded, rmag = sdss(ra_deg,dec_deg, fov_am)
        if len(rad) == 0:
            print "NO STARS IN SDSS, TRYING UNSO"
            name, rad, ded, rmag = unso(ra_deg,dec_deg, fov_am)
            catalog = 'unso'


    return [name, rad, ded, rmag, ra_deg, dec_deg, fov_am, coord, newcoord, catalog]

def unso(radeg,decdeg,fovam): # RA/Dec in decimal degrees/J2000.0 FOV in arc min. import urllib as url
    
    #str1 = 'http://webviz.u-strasbg.fr/viz-bin/asu-tsv/?-source=USNO-B1'
    str1 = 'http://vizier.hia.nrc.ca/viz-bin/asu-tsv/?-source=USNO-B1'
    str2 = '&-c.ra={:4.6f}&-c.dec={:4.6f}&-c.bm={:4.7f}/{:4.7f}&-out.max=unlimited'.format(\
            radeg,decdeg,fovam,fovam)

    # Make sure str2 does not have any spaces or carriage returns/line 
    #feeds when you # cut and paste into your code
    URLstr = str1+str2
    #print URLstr

    f = url.urlopen(URLstr)
    # Read from the object, storing the page's contents in 's'.
    s = f.read()
    f.close()
   
    sl = s.splitlines()
    sl = sl[45:-1]
    name = np.array([])
    rad = np.array([])
    ded = np.array([])
    rmag = np.array([])
    for k in sl:
        kw = k.split('\t')
        name = np.append(name,kw[0])
        rad = np.append(rad,float(kw[1]))
        ded = np.append(ded,float(kw[2]))
        if kw[12] != '     ': # deal with case where no mag is reported
            rmag = np.append(rmag,float(kw[12]))
        else:
            rmag = np.append(rmag,np.nan) 
        
    return name,rad,ded,rmag

def sdss(radeg,decdeg,fovam): # RA/Dec in decimal degrees/J2000.0 FOV in arc min. import urllib as url
    
    #str1 = 'http://vizier.hia.nrc.ca/viz-bin/asu-tsv/?-source=SDSS-DR12'
    str1 = 'http://vizier.hia.nrc.ca/viz-bin/asu-tsv/?-source=V/147'
    str2 = '&-c.ra={:4.6f}&-c.dec={:4.6f}&-c.bm={:4.7f}/{:4.7f}&-out.max=unlimited'.format(\
            radeg,decdeg,fovam,fovam)

    # Make sure str2 does not have any spaces or carriage returns/line feeds when you # cut 
    #and paste into your code
    URLstr = str1+str2
    print URLstr

    f = url.urlopen(URLstr)
    # Read from the object, storing the page's contents in 's'.
    s = f.read()
    f.close()
   
    sl = s.splitlines()
    sl = sl[54:-1]
    name = np.array([])
    rad = np.array([])
    ded = np.array([])
    zmag = np.array([])
    for k in sl:
        kw = k.split('\t')
        name = np.append(name,kw[5])
        rad = np.append(rad,float(kw[0]))
        ded = np.append(ded,float(kw[1]))
        if kw[12] != '     ': # deal with case where no mag is reported
            zmag = np.append(zmag,float(kw[17]))
        else:
            zmag = np.append(zmag,np.nan) 
        
    return name,rad,ded,zmag

def load_img(fl,telSock):
    biasff = fits.open('/home/utopea/elliot/20190418T073052_Bias.fits')
    bias = biasff[0].data
    bias = bias.astype('float')

    if type(fl) == str:
        f = fits.open(fl)
        data = f[0].data
        data = data.astype('float') - bias
        head = f[0].header
        RA = head['RA']
        DEC = head['DEC']
        RA = RA[0:2] + ' ' + RA[2:4] + ' ' + RA[4:]
        DEC = DEC[0:3] + ' ' + DEC[3:5] + ' ' + DEC[5:]

        cresult = centroid_finder(data)
    else:
        data = fl.astype('float') - bias
        telem = WG.get_telemetry(telSock)
        RA = telem['RA']
        DEC = telem['DEC']
        RA = RA[0:2] + ' ' + RA[2:4] + ' ' + RA[4:]
        DEC = DEC[0:3] + ' ' + DEC[3:5] + ' ' + DEC[5:]
        head = telem

        cresult = centroid_finder(data)

    return data, head, RA, DEC, cresult

def centroid_finder(img, plot=False):

    imgsize = img.shape

    #find bright pixels
    imgmedian = np.median(img)
    #print "MEDIAN: %f, MEAN: %f" % (imgmedian, np.mean(img))
    imgstd = np.std(img[img < (imgmedian + 50)])
    nstd = 3.0
    #print "IMG MED: %f\nIMGSTD: %f\nCUTOFF: %f" % (imgmedian, imgstd,imgmedian+nstd*imgstd)

    brightpix = np.where(img >= imgmedian + nstd*imgstd)
    new_img = np.zeros(imgsize)

    if len(brightpix) == 0:
        return False

    for i in range(len(brightpix[0])):
        new_img[brightpix[0][i],brightpix[1][i]] = 1.0

    stars = []
    for x in range(imgsize[0]):
        for y in range(imgsize[1]):
            if new_img[x,y] == 1:
                new_star, new_img = explore_region(x,y,new_img)
                if len(new_star[0]) >=3: #Check that the star is not just a hot pixel
                    stars.append(new_star)
    
    centroidx, centroidy, Iarr, Isat, width = [],[],[],[],[]
    for star in stars:
        xsum, ysum, Isum = 0.,0.,0.
        sat = False
        for i in range(len(star[0])):
            x = star[0][i]
            y = star[1][i]
            I = img[x,y]
            xsum += x*I
            ysum += y*I
            Isum += I
            if I >= 63000: #65536
                sat = True
        
        if sat == True:
            Isat.append(1)
        else:
            Isat.append(0)

        centroidx.append(xsum/Isum)
        centroidy.append(ysum/Isum)
        Iarr.append(Isum)

        gx0 = centroidx[-1] - 10
        gx1 = centroidx[-1] + 10
        gy0 = centroidy[-1] - 10
        gy1 = centroidy[-1] + 10

        if centroidx[-1] < 10:
            gx0 = 0
        if centroidx[-1] > imgsize[0]-11:
            gx1 = imgsize[0]-1
        
        if centroidy[-1] < 10:
            gy0 = 0
        if centroidy[-1] > imgsize[1]-11:
            gy1 = imgsize[1]-1
        
        gx = img[int(gx0):int(gx1),int(centroidy[-1])]
        gy = img[int(centroidx[-1]), int(gy0):int(gy1)]
        xs = range(len(gx))
        ys = range(len(gy))

        try:
            gausx = gaussian_fit(xs, gx, [5000.0,3.0,10.0])
            gausy = gaussian_fit(ys, gy, [5000.0,3.0,10.0])

            width.append(np.mean([gausx[0][1],gausy[0][1]]) * 2.355)
        except:
            width.append(0)

    return [centroidx,centroidy,Iarr, Isat, width]

def explore_region(x,y, img):
 
    xreg = [x]
    yreg = [y]
    img[x,y] = 0
    imgcopy = np.array(img)

    for k,x in enumerate(xreg):
        y = yreg[k]
        for i in range(-1,2):
            for j in range(-1,2):
                if (x+i > 0 and x+i < img.shape[0]) and (y+j > 0 and y+j < img.shape[1])\
                    and (img[x+i,y+j] == 1):
                    xreg.append(x+i)
                    yreg.append(y+j)
                    img[x+i,y+j] = 0

    region = np.array([np.array(xreg), np.array(yreg)])
    
    return region, img

def bright_star(centroids, imshape, mindist = 25):

    Iarr = centroids[2]
    Isat = centroids[3]
    bright_stars = np.argsort(Iarr)[::-1]

    starexists = 0
    for star in bright_stars:
       if (Iarr[star] > 3000) and (Isat[star] != 1):
           starexists = 1
           break

    if starexists == 0:
        return None

    for star in bright_stars:
        if (centroids[3][star] != 1) and (centroids[0][star] > mindist) and \
            (centroids[0][star] < imshape[0]-mindist) and \
            (centroids[1][star] > mindist) and (centroids[1][star] < imshape[1]-mindist):
            return star

    return None

def gaus(xs, a, sigma, x0):
    '''Returns a gaussian function with parameters p0
    p0 [A, sigma, mean]'''

    return a * np.exp((-1.0/2.0) * ((xs - x0)/sigma)**2.0)

def gaussian(xs, p0):
    first = ((xs - p0[2])/p0[1])**2.0

    return p0[0] * np.exp((-1.0/2.0) * second)

def gaussian_fit(xdata, ydata, p0, gaussian=gaus):

    popt, pcov = curve_fit(gaus, xdata, ydata, p0=p0)
    return [popt, pcov]

def ra_conv(ra, degrees=True):

    if degrees:
        h = float(ra[0:2])
        m = float(ra[2:4])
        s = float(ra[4:9])

        deg = (h/24 + m/24/60 + s/24/60/60)*360

        return deg

    if not degrees:
        ra = float(ra)
        h = int(np.floor(ra / 360 * 24))
        m = int(np.floor((ra - h/24*360)/360 * 24 * 60))
        s = round(float((ra*24*60/360 - h*60 - m) * 60),2)

        hms_out = str(h) + str(m) + str(s)

        return hms_out

def dec_conv(dec, degrees=True):

    if degrees:
        sign = np.sign(float(dec[0:3]))
        deg = float(dec[0:3]) + sign*float(dec[3:5])/60. + sign*float(dec[5:])/3600.
        return deg

def ra_adjust(ra, d_ra, action = 'add'):
    '''Adjusts RA by the specified amount and returns a single string.
    Inputs are hhmmss.ss. Can add or sub. Default is add.'''
    
    h = float(ra[0:2])
    m = float(ra[2:4])
    s = float(ra[4:9])

    ra_l = np.array([h,m,s])

    dh = float(d_ra[0:2])
    dm = float(d_ra[2:4])
    ds = float(d_ra[4:9])

    dra_l = np.array([dh,dm,ds])

    if action == 'add':
        new_ra = ra_l + dra_l
        
        if new_ra[2] >= 60.0:
            new_ra[1] += 1.0
            new_ra[2] -= 60.0
            if new_ra[1] >= 60.0:
                new_ra[0] += 1.0
                new_ra[1] -= 60.0
                if new_ra[0] >= 24.0:
                    new_ra[0] -= 24.0

    if action == 'sub':
        new_ra = ra_l - dra_l

        if new_ra[2] < 0.0:
            new_ra[1] -= 1.0
            new_ra[2] += 60.0
            if new_ra[1] < 0.0:
                new_ra[0] -= 1.0
                new_ra[1] += 60.0
                if new_ra[0] <= 0.0:
                    new_ra[0] += 24.0

    
    return str(new_ra[0]) + str(new_ra[1]) + str(round(new_ra[2],2))

def rotate_points(rotangle, x_points, y_points, arraysize = 1024):

    normx = np.array(x_points) - (arraysize / 2.)
    normy = np.array(y_points) - (arraysize / 2.)
   
    rotangle = rotangle - 90 - 0.26
    rotangle_rad = rotangle*np.pi/180.0
    rotation_matrix = np.array([[np.cos(rotangle_rad),1*np.sin(rotangle_rad)],\
        [-1*np.sin(rotangle_rad), np.cos(rotangle_rad)]])
    rotation_matrix_neg = np.array([[np.cos(rotangle_rad),-1*np.sin(rotangle_rad)],\
        [1*np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    points = np.array([normx, normy])

    offsets = np.dot(rotation_matrix, points)
    offsets_neg = np.dot(rotation_matrix_neg, points)

    return offsets[0] + (arraysize / 2.), offsets[1] + (arraysize / 2.),\
            offsets_neg[0] + (arraysize / 2.), offsets_neg[1] + (arraysize / 2.)


def projected_coords(ra, dec, ra0, dec0):

    ra = ra * np.pi / 180
    dec = dec * np.pi / 180
    ra0 = ra0 * np.pi / 180
    dec0 = dec0 * np.pi /180

    X = -1*(np.cos(dec) * np.sin(ra - ra0)) / (np.cos(dec0)*np.cos(dec)*np.cos(ra - ra0) \
            + np.sin(dec)*np.sin(dec0))
    Y = -1*(np.sin(dec0)*np.cos(dec)*np.cos(ra - ra0) - np.cos(dec0)*np.sin(dec)) / \
            (np.cos(dec0)*np.cos(dec)*np.cos(ra - ra0) + np.sin(dec)*np.sin(dec0))

    x = (flength * X / 0.013) + 512
    y = (flength * Y / 0.013) + 512

    return x, y, X, Y

def get_rotation_solution(rotangle, guideroffsets, DEC):

    rotangle = rotangle - 90 - 0.26
    rotangle_rad = rotangle * np.pi / 180.0

    rotation_matrix = np.array([[np.cos(rotangle_rad),np.sin(rotangle_rad)],\
                              [-1.*np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    rotation_matrix_offsets = np.array([[np.cos(rotangle_rad),-1*np.sin(rotangle_rad)],\
                                [np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    offsets = np.dot(rotation_matrix_offsets, guideroffsets)
    #offsets[0] = offsets[0] * np.cos(float(DEC)*np.pi / 180.)

    return offsets

def get_rotation_solution_offset(rotangle, guideroffsets, DEC):

    rotangle = rotangle - 90
    rotangle_rad = rotangle * np.pi / 180.0

    rotation_matrix = np.array([[np.cos(rotangle_rad),np.sin(rotangle_rad)],\
                              [-1.*np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    rotation_matrix_offsets = np.array([[np.cos(rotangle_rad),-1*np.sin(rotangle_rad)],\
                                [np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    offsets = np.dot(rotation_matrix_offsets, guideroffsets)
    #offsets[0] = offsets[0] * np.cos(float(DEC)*np.pi / 180.)

    return offsets

def get_rotation_solution_astrom(rotangle, guideroffsets, DEC):

    rotangle = rotangle - 90 - 0.26
    rotangle_rad = rotangle * np.pi / 180.0

    rotation_matrix = np.array([[np.cos(rotangle_rad),np.sin(rotangle_rad)],\
                              [-1.*np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    rotation_matrix_offsets = np.array([[np.cos(rotangle_rad),-1*np.sin(rotangle_rad)],\
                                [np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    offsets = np.dot(rotation_matrix_offsets, guideroffsets)
    #offsets[0] = offsets[0] * np.cos(float(DEC)*np.pi / 180.)

    return offsets

class AstrometryThread(QThread):

    updateText = pyqtSignal(str)
    plotSignal = pyqtSignal(np.ndarray,str)
    astrometricPlotSignal = pyqtSignal(list,str)
    astrometryMove = pyqtSignal(float,float)

    def __init__(self, guider, RAObj, DECObj, ObjText, GuiderExpTime):

        QThread.__init__(self)

        self.guider = guider
        self.telSock = self.guider.telSock
        self.RAObj = RAObj
        self.DECObj = DECObj
        self.ObjText = ObjText
        self.GuiderExpTime = GuiderExpTime

    def __del__(self):
        self.wait()

    def run(self):

        if self.guider.cam:
            exptime = int(self.guider.expTime.text())
            self.updateText.emit("TAKING ASTROMETRIC IMAGE")
            img = self.guider.takeImage(dark=False)

            self.plotSignal.emit(img, 'Astrometry')
            self.updateText.emit("STARTING ASTROMETRIC DERIVATION")
            try:
                results = getAstrometricSoln(img, self.telSock, \
                        self.guider.rotangle.text())
                if len(results) < 3:
                    self.updateText.emit("NO ASTROMETRIC SOLUTION...NOT ENOUGH STARS? >=3")
                    self.updateText.emit("Try increasing exp time, or moving to a different field?")
                else:
                    platesolve, fieldoffset, realcenter, solvecenter, guideroffsets,plotting = results
                    self.updateText.emit("Real Guider Center is: \nRA:\t%s\n DEC:\t%s" % \
                            (self.returnhmsdmsstr(solvecenter.ra.hms), self.returnhmsdmsstr(solvecenter.dec.dms)))
                    #self.updateText.emit('Guider Offset (") is: \nRA: %s\n DEC: %s' % (fieldoffset[0].to(u.arcsec).to_string(),\
                    #        fieldoffset[1].to(u.arcsec).to_string()))
                    self.astrometry_calc(solvecenter, guideroffsets, plotting)

            except Exception as e:
                print e
                print traceback.print_exc()
                self.updateText.emit("SOMETHING WENT WRONG WITH ASTROMETRY....\nCHECK TERMINAL")

    def returnhmsdmsstr(self,angle):

        return str(int(angle[0])) + ' '+ str(int(angle[1])) + ' ' + str(float(angle[2]))

    def astrometry_calc(self, solvecenter, guideroffsets, plotting):
        self.astrometricPlotSignal.emit(plotting, "Astrometry Solution")

        #Grabbing the Object RA and DEC
        RAText = self.RAObj.text()
        DECText = self.DECObj.text()

        #RA and DEC of Guider center in deg
        ra_guide = solvecenter.ra.deg
        dec_guide = solvecenter.dec.deg
        GUIDERCoordhms = self.returnhmsdmsstr(solvecenter.ra.hms)
        GUIDERCoorddms = self.returnhmsdmsstr(solvecenter.dec.dms)

        #Performing the calculation to get the RA and DEC of the WIFIS field using the guider offsets
        #Note this assumes the offsets are true
        ra_wifis = ra_guide + (guideroffsets[0]/3600. / np.cos(dec_guide * np.pi / 180.))
        dec_wifis = dec_guide + guideroffsets[1]/3600.
        
        #Coord object for WIFIS Center
        WIFISCoord = SkyCoord(ra_wifis, dec_wifis, unit='deg')

        #Getting nice formatted strings for printout
        WIFISCoordhms = self.returnhmsdmsstr(WIFISCoord.ra.hms)
        WIFISCoorddms = self.returnhmsdmsstr(WIFISCoord.dec.dms)

        coordvalues = [GUIDERCoordhms, GUIDERCoorddms, WIFISCoordhms, WIFISCoorddms]

        self.updateText.emit("Real WIFIS Field Center is: \nRA %s\nDEC: %s" % (WIFISCoordhms, WIFISCoorddms))

        #Checking if the RA and DEC values are okay
        worked = True
        try:
            float(RAText)
            float(DECText)
        except:
            self.updateText.emit('RA or DEC Obj IMPROPER INPUT')
            self.updateText.emit('PLEASE USE RA = HHMMSS.S  and')
            self.updateText.emit('DEC = +/-DDMMSS.S, no spaces')
            worked = False

        if (len(RAText) == 0) or (len(DECText) == 0):
            self.updateText.emit('RA or DEC Obj Text Empty!')
            self.writeOffsetInfo(plotting,WIFISCoord,'NotSet','NotSet', coordvalues, worked, guideroffsets)
            return

        try:
            if (RAText[0] == '+') or (RAText[0] == '-'):
                RAspl = RAText[1:].split('.')
                if len(RAspl[0]) != 6: 
                    self.updateText.emit('RA or DEC Obj IMPROPER INPUT')
                    self.updateText.emit('PLEASE USE RA = HHMMSS.S  and')
                    self.updateText.emit('DEC = +/-DDMMSS.S, no spaces')
                    worked = False
            else:
                RAspl = RAText.split('.')
                if len(RAspl[0]) != 6: 
                    self.updateText.emit('RA or DEC Obj IMPROPER INPUT')
                    self.updateText.emit('PLEASE USE RA = HHMMSS.S  and')
                    self.updateText.emit('DEC = +/-DDMMSS.S, no spaces')
                    worked = False

            if (DECText[0] == '+') or (DECText[0] == '-'):
                DECspl = DECText[1:].split('.')
                if len(DECspl[0]) != 6: 
                    self.updateText.emit('RA or DEC Obj IMPROPER INPUT')
                    self.updateText.emit('PLEASE USE RA = HHMMSS.S  and')
                    self.updateText.emit('DEC = +/-DDMMSS.S, no spaces')
                    worked = False
            else:
                DECspl = DECText.split('.')
                if len(DECspl) != 6: 
                    self.updateText.emit('RA or DEC Obj IMPROPER INPUT')
                    self.updateText.emit('PLEASE USE RA = HHMMSS.S  and')
                    self.updateText.emit('DEC = +/-DDMMSS.S, no spaces')
                    worked = False
        except Exception as e:
            print e
            self.updateText.emit('RA or DEC Obj IMPROPER INPUT LIKELY')
            self.writeOffsetInfo(plotting,WIFISCoord,'NotSet','NotSet', coordvalues, worked, guideroffsets)
            return

        if worked == False:
            self.updateText.emit('NO Object RA and DEC...Cant compute offset')
            self.writeOffsetInfo(plotting,WIFISCoord,'NotSet','NotSet', coordvalues, worked, guideroffsets)
            return
        else:
            if (RAText[0] == '+') or (RAText[0] == '-'):
                RA = RAText[1:3] + ' ' + RAText[3:5] + ' ' + RAText[5:]
            else:
                RA = RAText[0:2] + ' ' + RAText[2:4] + ' ' + RAText[4:]
            DEC = DECText[0:3] + ' ' + DECText[3:5] + ' ' + DECText[5:]

        TargetCoord = SkyCoord(RA, DEC, unit=(u.hourangle, u.deg))
        fieldoffset = WIFISCoord.spherical_offsets_to(TargetCoord)
        FOffsethms = fieldoffset[0].to(u.arcsec).to_string()
        FOffsetdms = fieldoffset[1].to(u.arcsec).to_string()

        GOffsetCoord = solvecenter.spherical_offsets_to(TargetCoord)
        GOffsethms = GOffsetCoord[0].to(u.arcsec).to_string()
        GOffsetdms = GOffsetCoord[1].to(u.arcsec).to_string()
            
        self.writeOffsetInfo(plotting,WIFISCoord,RA,DEC, coordvalues, worked, guideroffsets)

        self.updateText.emit("IF RA/DEC IS CENTERED\nGuider Offsets Are:\nRA:\t%s\nDEC:\t%s\n" % \
                (GOffsethms,GOffsetdms))
        self.updateText.emit('WIFIS Offset (") to Target is:\nRA:\t%s\nDEC:\t%s\n' % \
                        (FOffsethms, FOffsetdms))

        self.astrometryMove.emit(fieldoffset[0].arcsec, fieldoffset[1].arcsec)

    def writeOffsetInfo(self, plotting, WIFISCoord, RA, DEC, coordvalues, worked, guideroffsets):
        x,y,k,xproj,yproj,image,head,coord = plotting

        fieldoffset = coord.spherical_offsets_to(WIFISCoord)
        FOffsethms = fieldoffset[0].to(u.arcsec).to_string()
        FOffsetdms = fieldoffset[1].to(u.arcsec).to_string()

        objtext = self.ObjText.text()
        todaydate = time.strftime("%Y%m%d")

        hdr = fits.Header()
        hdr['DATE'] = todaydate 
        hdr['SCOPE'] = 'Bok Telescope, Steward Observatory'
        hdr['ObsTime'] = time.strftime('%H:%M"%S')
        hdr['ExpTime'] = (self.GuiderExpTime, '//Guider Exposure Time')
        hdr['RA'] = (head['RA'], '//Telescope RA')
        hdr['DEC'] = (head['DEC'], '//Telescope DEC')
        hdr['IIS'] = (head['IIS'], '//Rotator Angle')
        hdr['EL'] = head['EL']
        hdr['AZ'] = head['AZ']
        hdr['AM'] = (head['SECZ'], '//Airmass')
        hdr['Filter'] = self.guider.getFilterType()
        hdr['FocPos'] = self.guider.foc.get_stepper_position()
        hdr['OBJ'] = objtext
        hdr['OBJRA'] = (RA, '//Entered Object RA')
        hdr['OBJDEC'] = (DEC, '//Entered Object DEC')
        hdr['WRA'] = (coordvalues[2], '//Calculated WIFIS Field RA')
        hdr['WDEC'] = (coordvalues[3], '//Calculated WIFIS Field DEC')
        hdr['GRA'] = (coordvalues[0], '//Calculated Guider Field RA')
        hdr['GDEC'] = (coordvalues[1], '//Calculated Guider Field DEC')
        hdr['FOffRA'] = (FOffsethms, '//Arcsec from Telescope to WIFIS')
        hdr['FOffDEC'] = (FOffsetdms, '//Arcsec from Telescope to WIFIS')
        hdr['GRAOff'] = (str(guideroffsets[0]), '//Guider RA Offset')
        hdr['GDECOff'] = (str(guideroffsets[1]), '//Guider DEC Offset')
        fits.writeto('/Data/WIFISGuider/astrometry/'+todaydate+'T'+\
                        time.strftime('%H%M%S')+'.fits', image, hdr, clobber=True)
