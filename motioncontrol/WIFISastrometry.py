import matplotlib.pyplot as mpl
import numpy as np
import urllib as url
from astropy.io import fits
from scipy.optimize import curve_fit

class Formatter(object):
    def __init__(self, im):
        self.im = im
    def __call__(self, x, y):
        z = self.im.get_array()[int(y), int(x)]
        return 'x={:.01f}, y={:.01f}, z={:.01f}'.format(x, y, z)

def grabUNSOfield(ra, dec):
    """Takes an ra and dec as grabbed from the telemetry and returns a field
    from UNSO for use in solving the guider field"""
    
    ra_offset = '000000.00' 
    dec_offset = '000000.00' 
    ra_deg = ra_conv(ra)
    dec_deg = dec_conv(dec)

    fov_am =5.1
    name, rad, ded, rmag = unso(ra_deg,dec_deg, fov_am)
    
    return [name, rad, ded, rmag]

def centroid_finder(img, plot = False, verbose=False):

    imgsize = img.shape

    #find bright pixels
    imgmean = np.mean(img)
    imgstd = np.std(img)
    nstd = 4.

    if verbose:
        print "IMG MEAN: %f\nIMGSTD: %f\nCUTOFF: %f" % (imgmean, imgstd,imgmean+nstd*imgstd)

    brightpix = np.where(img >= imgmean + nstd*imgstd)
    new_img = np.zeros(imgsize)

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
            if I == 65536:
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

            width.append(np.mean([gausx[0][1],gausy[0][1]]))
        except:
            width.append(0)

    if plot:
        fig = mpl.figure()
        ax = fig.add_subplot(1,1,1)
        im = ax.imshow(img, cmap = 'gray', interpolation='none', origin='lower')
        circ = ax.plot(centroidy, centroidx, 'ro', markeredgecolor = 'r', markerfacecolor='none',\
            markersize = 5)
        #ax.format_coord = Formatter(im)
        #fig.colorbar(im)
        mpl.show()
        mpl.close()

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
    bright_stars = np.argsort(Iarr)[::-1]

    starexists = 0
    for star in bright_stars:
       if Iarr[star] > 3000:
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


def unso(radeg,decdeg,fovam): # RA/Dec in decimal degrees/J2000.0 FOV in arc min. import urllib as url
    
    str1 = 'http://webviz.u-strasbg.fr/viz-bin/asu-tsv/?-source=USNO-B1'
    str2 = '&-c.ra={:4.6f}&-c.dec={:4.6f}&-c.bm={:4.7f}/{:4.7f}&-out.max=unlimited'.format(radeg,decdeg,fovam,fovam)

    # Make sure str2 does not have any spaces or carriage returns/line feeds when you # cut and paste into your code
    URLstr = str1+str2
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


if __name__ == '__main__':
    import glob
    fls = glob.glob('/Data/WIFISGuider/20170511/platescale*.fits')

    for fl in fls:
        f = fits.open(fl)
        img = f[0].data
        print fl
        print centroid_finder(img) 
        print "\n"
