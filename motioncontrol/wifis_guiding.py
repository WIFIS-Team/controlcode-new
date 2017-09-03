import matplotlib.pyplot as mpl
import time
import socket
import numpy as np
#import fli_controller as flic
import urllib as url
try:
    import FLI
except:
    pass    
import WIFISastrometry as WA
from glob import glob
from astropy.io import fits
from sys import exit

plate_scale = 0.29125
guideroffsets = np.array([-4.15,365.88])

#June 2017 -4.0,414.1
#May 2017 -6.0, 424.1

# !!IMPORTANT!!: Before guiding can work we need to characterize the offset of the 
#                guiding field from the primary field.

###########################
### SIMPLE GUIDING PLAN ###
# SETUP
# NEED: 
#   1)  Offset from the guiding field to the primary field
#   2)  Rotation angle from the star
#   3)  Rough estimate of the plate scale of the guide camera
#
# PLAN:
#   1)  To get the offset we need to point the telescope at a star field
#           and then determine the location of stars in the guide field.
#           Both of these need the ability to download UNSO data.
#   2)  Rotation angle can be pulled from the telemetry
#   3)  Estimate of the plate scale take two images and then calculate the distance
#           travelled as a function of RA and DEC
################

# Use the command RADECGUIDE X.XX X.XX to move the telescope. X.XX in arcsec

try:
    f = open('/home/utopea/elliot/ipguiding.txt','r')
    lines = f.readlines()

    IPADDR = lines[0][:-1]
    PORT = int(lines[1][:-1])
except:
    pass

TELID = "BOK"
REF_NUM = 123
REQUEST = "ALL"

keyList = ["ID"            ,
        "SYS"           ,
        "REF_NUM"       ,
        "MOT"           ,
        "RA"            ,
        "DEC"           ,
        "HA"            ,
        "ST"            ,
        "EL"            ,
        "AZ"            ,
        "SECZ"          ,
        "EQ"            ,
        "JD"            ,
        "WOBBLE"        ,
        "DOME"          ,
        "UT"            ,
        "IIS"]

def connect_to_telescope():
    #instantiate the socket class
    telSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    telSock.settimeout(0.5)

    #IPADDR = telSock.gethostbyname(HOST)
    telSock.connect((IPADDR,PORT)) #Open the socket

    return telSock

def query_telescope(telSock, reqString, verbose=True, telem=False):
    """Sends a query or a command to the telescope and returns the telescope 
    response"""

    if verbose:
        print("QUERYING: %s" % (reqString))
    
    telSock.send(reqString)
    resp = ""
    test = True

    #Grab 100 bytes at a time from the socket and check for timeouts.
    while test:
        try:
            inStuff = telSock.recv(100)
        except socket.timeout:
            if resp and verbose:
                print("###\tDONE RECEIVING TELEMETRY\t###")
            test = False
            break

        if inStuff:
            resp += inStuff
        else:
            test = False
    
    #Turn string into list, separated by whitespace
    #for i,j in enumerate(resp):
        #print i,j 
    if telem:
        resp1 = resp[:74]
        resp2 = resp[87:]
        respf = resp1 + resp2
        respf = respf.split(' ')
    else:
        respf = resp.split(' ')
    cleanResp = []

    #Remove empty elements and newlines
    for char in respf:
        if char != '' and not char.endswith("\n"):
            cleanResp.append(char)
        elif char.endswith("\n"):
            cleanResp.append(char[:-1])

    return cleanResp
    
def get_telemetry(telSock, verbose=True):
    """Inititates connection to telescope and gets all telemetry data"""

    if verbose:
        reqString = "%s TCS %i REQUEST ALL" % (TELID, REF_NUM)

    cleanResp = query_telescope(telSock, reqString, telem=True)
    #gather the telemetry into a dict
    telemDict = {}
    II = 0
    for key in keyList:
        telemDict[key] = cleanResp[II]
        II += 1

    return telemDict

def check_moving(telSock):

    reqString = "%s TCS %i REQUEST MOT" % (TELID, REF_NUM)
    
    resp = query_telescope(telSock, reqString)
    mov = resp[-1]
    sleep(1)
    
    return mov

def clean_telem(telemDict):

    #print telemetry data in a clean way
    print "\n"
    print "|\t  BOK TELEMETRY             |"
    for (key, value) in telemDict.iteritems():
        print "|%s\t|\t%s|" % (key.ljust(10), value.ljust(12))

def write_telemetry(telemDict):

    f = open('/home/utopea/WIFIS-Team/controlcode/BokTelemetry.txt', 'w')
    f.write('Timestamp: %s\n' % (time.ctime(time.time())))
    for (key,value) in telemDict.iteritems():
        f.write("%s:\t\t%s\n" % (key, value))
    
    f.close()

def move_telescope(telSock,ra_adj, dec_adj, verbose=True):
   
    if ra_adj > 1000:
        print "Too large a move in RA. NOT MOVING"
        return
    if dec_adj > 1000:
        print "Too large a move in DEC. NOT MOVING"
        return

    reqString = "%s TCS %i RADECGUIDE %.2f %.2f" % (TELID, REF_NUM, ra_adj, dec_adj)
    
    resp = query_telescope(telSock, reqString, verbose=verbose)
        
def plotguiderimage(img):

    mpl.imshow(np.log10(img), cmap='gray',interpolation='none',origin='lower')
    mpl.show()

def get_rotation_solution(telSock, forcerot=90):

    x_sol = np.array([0.0, plate_scale])
    y_sol = np.array([plate_scale, 0.0])

    forcerot = False
    if forcerot == True:
        rotangle = 90
    else:
        rotangle = float(query_telescope(telSock, 'BOK TCS 123 REQUEST IIS')[-1]) - 90 - 0.26

    rotangle_rad = rotangle*np.pi/180.0
    rotation_matrix = np.array([[np.cos(rotangle_rad),1*np.sin(rotangle_rad)],\
        [-1*np.sin(rotangle_rad), np.cos(rotangle_rad)]])
    rotation_matrix_offsets = np.array([[np.cos(rotangle_rad),-1*np.sin(rotangle_rad)],\
        [1*np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    #if (rotangle < 90) & (rotangle > 0):
    #    rotation_matrix = rotation_matrix_offsets
    #    print "CHANGING MATRIX"

    offsets = np.dot(rotation_matrix_offsets, guideroffsets)
    x_rot = np.dot(rotation_matrix, x_sol)
    y_rot = np.dot(rotation_matrix, y_sol)

    return offsets, x_rot, y_rot

def wifis_simple_guiding(telSock):

    #Some constants that need defining
    exptime = 1500

    offsets, x_rot, y_rot = get_rotation_solution(telSock)

    camSN = "ML0240613"
    cam = FLI.USBCamera.locate_device(camSN)

    #Take image with guider (with shutter open)
    cam.set_exposure(exptime, frametype="normal")
    cam.end_exposure()
    img1 = cam.take_photo()
    img1size = img1.shape
   
    #check positions of stars    
    centroidx, centroidy, Iarr, Isat, width = WA.centroid_finder(img1, plot=False)
    bright_stars = np.argsort(Iarr)[::-1]

    #Choose the star to track
    guiding_star = bright_stars[0]
    for star in bright_stars:
        if (centroidx[star] > 50 and centroidx[star] < 950) and \
            (centroidy[star] > 50 and centroidy[star] < 950):
            if Isat[star] != 1:
                guiding_star = star
                break 
    
    stary1 = centroidx[guiding_star]
    starx1 = centroidy[guiding_star] 
    boxsize = 30
    
    check_guidestar = False
    if check_guidestar:
        mpl.imshow(img1, cmap = 'gray',interpolation='none', origin='lower')
        mpl.plot(starx1, stary1, 'ro', markeredgecolor = 'r', markerfacecolor='none', markersize = 5)
        mpl.show()

    guideplot=True
    if guideplot:
        mpl.ion()
        fig, ax = mpl.subplots(1,1)
        imgbox = img1[stary1-boxsize:stary1+boxsize, starx1-boxsize:starx1+boxsize]
        imgplot = ax.imshow(imgbox, interpolation='none', origin='lower')
        fig.canvas.draw()

    try:
        while True:
            img = cam.take_photo(shutter='open')
            imgbox = img[stary1-boxsize:stary1+boxsize, starx1-boxsize:starx1+boxsize]
          
            if guideplot:
                ax.clear()
                imgplot = ax.imshow(imgbox, interpolation='none', origin='lower')
                fig.canvas.draw()
            
            centroidx, centroidy, Iarr, Isat, width = WA.centroid_finder(imgbox, plot=False)
            try:
                new_loc = np.argmax(Iarr)
            except:
                continue

            newx = centroidx[new_loc]
            newy = centroidy[new_loc]

            dx = newx - boxsize 
            dy = newy - boxsize
            d_ra = dx * x_rot
            d_dec = dy * y_rot
            radec = d_ra + d_dec

            #fl = open('/home/utopea/elliot/guiding_data.txt','a')
            #fl.write("%f\t%f\n" % (dx, dy))
            #fl.close()
           
            print "X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f\n" \
               % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale)

            lim = 0.5
            r = -1
            d = -1
            #print d_ra, d_dec, width[0]
            guidingon=True
            if guidingon:
                if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
                    print "NOT MOVING, TOO SMALL SHIFT"
                    pass
                elif abs(radec[1]) < lim:
                    print "MOVING DEC ONLY"
                    move_telescope(telSock, 0.0, d*radec[0], verbose=False)
                elif abs(radec[0]) < lim:
                    print "MOVING RA ONLY"
                    move_telescope(telSock, r*radec[1], 0.0, verbose=False)
                else:
                    move_telescope(telSock,r*radec[1],d*radec[0], verbose=False)
                    pass
           
            time.sleep(1)

    except KeyboardInterrupt:
        cam.end_exposure()

    cam.end_exposure()

    return starx1, stary1

def wifis_simple_guiding_setup(telSock, cam, exptime, gfls):

    #Some constants that need defining
    #exptime = 1500

    #Gets the rotation solution so that we can guide at any instrument rotation angle
    offsets, x_rot, y_rot = get_rotation_solution(telSock)

    #Take image with guider (with shutter open)
    cam.set_exposure(exptime, frametype="normal")
    cam.end_exposure()

    #Takes initial image
    img1 = cam.take_photo()
    img1size = img1.shape
    boxsize = 30
   
    #Checks to see if there exists a guiding star for this target
    if gfls[1] and (gfls[0] != ''):
        #Sets the larger boxsize for guiding setup
        boxsize_f = 50
        
        #Get the original guidestar coordinates.
        f = open(gfls[0], 'r')
        lines = f.readlines()
        spl = lines[0].split()
        starx1old, stary1old = int(spl[0]), int(spl[1])

        #Create box around star and check if star is in box. If star, correct it. If no star, reinitialize guiding
        imgbox = img1[stary1old-boxsize_f:stary1old+boxsize_f, starx1old-boxsize_f:starx1old+boxsize_f]
        worked = checkstarinbox(imgbox, boxsize_f, telSock)

        if worked:
            #If we could put a star at the right coordinates, set the guiding coords to the old coords
            starx1 = starx1old
            stary1 = stary1old
        else:
            #If we could not move a star to the right coordinates, then restart guiding for this object
            print "COULD NOT FIND OLD GUIDESTAR IN IMAGE...SELECTING NEW GUIDESTAR"
            starx1, stary1 = findguidestar(img1, gfls)
            
    else:
        #restart guiding by selecting a new guide star in the image 
        starx1, stary1 = findguidestar(img1,gfls)
    
    #Make sure were guiding on an actual star. If not maybe change the exptime for guiding.
    check_guidestar = True
    if check_guidestar:
        img2 = cam.take_photo()
        mpl.ion()
        starybox = int(stary1)
        starxbox = int(starx1)
        imgbox = img2[starybox-boxsize:starybox+boxsize, starxbox-boxsize:starxbox+boxsize]
        mpl.imshow(imgbox, interpolation='none', origin='lower')
        mpl.plot([boxsize],[boxsize], 'rx', markersize=10)
        #mpl.plot(starx1, stary1, 'ro', markeredgecolor = 'r', markerfacecolor='none', markersize = 5)
        mpl.show()

    print stary1, starx1

    return [offsets, x_rot, y_rot, stary1, starx1, boxsize, img1]

def findguidestar(img1, gfls):
    #check positions of stars    
    centroidx, centroidy, Iarr, Isat, width = WA.centroid_finder(img1, plot=False)
    bright_stars = np.argsort(Iarr)[::-1]

    #Choose the brightest non-saturated star for guiding
    guiding_star = bright_stars[0]
    for star in bright_stars:
        if (centroidx[star] > 50 and centroidx[star] < 950) and \
            (centroidy[star] > 50 and centroidy[star] < 950):
            if Isat[star] != 1:
                guiding_star = star
                break 
    
    stary1 = centroidx[guiding_star]
    starx1 = centroidy[guiding_star] 

    #Record this initial setup in the file
    if gfls[0] != '':
        f = open(gfls[0], 'w')
        f.write('%i\t%i\n' % (starx1, stary1))
        f.close()
    
    return starx1, stary1

def checkstarinbox(imgbox, boxsize, telSock):

    platescale = 0.29125 #"/pixel

    offsets, x_rot, y_rot = get_rotation_solution(telSock)
    
    #Try centroiding
    centroidx, centroidy, Iarr, Isat, width = WA.centroid_finder(imgbox, plot=False)
    try:
        #If centroid worked, great
        new_loc = np.argmax(Iarr)
    except:
        #If centroid didn't work, exit and restart gudding
        return False

    newx = centroidx[new_loc]
    newy = centroidy[new_loc]

    #Figure out how to move based on the rotation solution
    dx = newx - boxsize 
    dy = newy - boxsize
    d_ra = dx * x_rot
    d_dec = dy * y_rot
    radec = d_ra + d_dec

    print "INITIAL MOVEMENT TO GET SOURCE BACK IN CENTER"
    print "X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f\n" \
       % (dx,dy,radec[1],radec[0],width[0], width[0]*platescale)

    #Move the telescope if the required movement is greater than 0.5" 
    lim = 0.5
    r = -1
    d = -1
    guidingon=True
    if guidingon:
        if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
            print "NOT MOVING, TOO SMALL SHIFT"
            pass
        elif abs(radec[1]) < lim:
            print "MOVING DEC ONLY"
            move_telescope(telSock, 0.0, d*radec[0], verbose=False)
        elif abs(radec[0]) < lim:
            print "MOVING RA ONLY"
            move_telescope(telSock, r*radec[1], 0.0, verbose=False)
        else:
            move_telescope(telSock,r*radec[1],d*radec[0], verbose=False)
            pass
    
    time.sleep(2)

    return True

def run_guiding(inputguiding, parent, cam, telSock):
   
    #Get all the parameters from the guiding input
    offsets, x_rot, y_rot, stary1, starx1, boxsize, img1  = inputguiding

    #Start an updating guideplot DOESN'T WORK RIGHT NOW BECAUSE OF THE GUI IMPLEMENTATION
    #guideplot=False
    #if guideplot:
    #    mpl.ion()
    #    fig, ax = mpl.subplots(1,1)
    #    imgbox = img1[stary1-boxsize:stary1+boxsize, starx1-boxsize:starx1+boxsize]
    #    imgplot = ax.imshow(imgbox, interpolation='none', origin='lower')
    #    fig.canvas.draw()

    #Take an image
    img = cam.take_photo(shutter='open')
    starx_box = int(starx1)
    stary_box = int(stary1)
    imgbox = img[stary_box-boxsize:stary_box+boxsize, starx_box-boxsize:starx_box+boxsize]

    #if guideplot:
    #    ax.clear()
    #    imgplot = ax.imshow(imgbox, interpolation='none', origin='lower')
    #    fig.canvas.draw()
   
    #FInd the star in the box
    centroidx, centroidy, Iarr, Isat, width = WA.centroid_finder(imgbox, plot=False)
    try:
        new_loc = np.argmax(Iarr)
    except:
        return

    newx = centroidx[new_loc]
    newy = centroidy[new_loc]

    #Determine rotation solution 
    dx = newx - boxsize 
    dy = newy - boxsize
    d_ra = dx * x_rot
    d_dec = dy * y_rot
    radec = d_ra + d_dec

    #Do the movement
    #print "X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f\nDELTRA:\t\t%f\nDELTDEC:\t%f" \
    #   % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale,deltRA, deltDEC)
    print "X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f" \
       % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale)

    ##### IMPORTANT GUIDING PARAMETERS #####
    lim = 0.35 #Changes the absolute limit at which point the guider moves the telescope
    d = -0.8 #Affects how much the guider corrects by. I was playing around with -0.8 but the default is -1. Keep this negative.
    #######################################

    deltRA = 0
    deltDEC = 0

    guidingon=True
    if guidingon:
        if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
            print "NOT MOVING, TOO SMALL SHIFT\n"
            pass
        elif abs(radec[1]) < lim:
            print "MOVING DEC ONLY\n"
            deltDEC = d*radec[0]
            move_telescope(telSock, 0.0, d*radec[0], verbose=False)
        elif abs(radec[0]) < lim:
            print "MOVING RA ONLY\n"
            deltRA = d*radec[1]
            move_telescope(telSock, d*radec[1], 0.0, verbose=False)
        else:
            deltRA = d*radec[1]
            deltDEC = d*radec[0]
            move_telescope(telSock,d*radec[1],d*radec[0], verbose=False)
            print "\n"

    #Record for guiding checking later
    f = open('/home/utopea/elliot/guidinglog/'+time.strftime('%Y%m%dT%H')+'.txt', 'a')
    f.write("%f\t%f\n" % (radec[1],radec[0]))
    f.close()

    return deltRA, deltDEC

if __name__ == '__main__':

    telSock = connect_to_telescope()
    x = get_telemetry(telSock)
    #reqString = "BOK TCS 123 REQUEST IIS"
    #offset, xrot, yrot = get_rotation_solution(telSock)
    
    wifis_simple_guiding(telSock) 
