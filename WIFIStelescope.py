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
from PyQt5.QtCore import QThread

plate_scale = 0.29125

#guideroffsets = np.array([-9.,361.86])

# Early March guideroffsets = np.array([-9.,366.73])

# Dec 2017 guideroffsets = np.array([-0.7,362.68])

#JAN/FEB 2018 guideroffsets = np.array([-4.6,363.73])

#Aug/Sept guideroffsets = np.array([-5.54,361.37])
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
   
    for i in range(10): 
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
        respspl = resp.split()
        #print 'respspl ', respspl
        if telem and (len(respspl) < 4):
            continue
        if not telem:
            break
        elif telem and respspl[3] != 'OK':
            break

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

    reqString = "%s TCS %i REQUEST ALL" % (TELID, REF_NUM)

    cleanResp = query_telescope(telSock, reqString, telem=True, verbose=verbose)
    #gather the telemetry into a dict
    telemDict = {}
    II = 0
    for key in keyList:
        telemDict[key] = cleanResp[II]
        II += 1
    #telemDict['IIS'] = '90.0'

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
   
    if ra_adj > 2500:
        result = "Too large a move in RA. NOT MOVING"
        return result
    if dec_adj > 2500:
        result = "Too large a move in DEC. NOT MOVING"
        return result

    reqString = "%s TCS %i RADECGUIDE %.2f %.2f" % (TELID, REF_NUM, ra_adj, dec_adj)
    
    resp = query_telescope(telSock, reqString, verbose=verbose)

    result = "MOVED TELESCOPE RA: %s, DEC: %s" % (str(ra_adj), str(dec_adj))
    return result 

def move_next(telSock, verbose=True):

    reqString = "%s TCS %i MOVNEXT" % (TELID, REF_NUM)
    resp = query_telescope(telSock, reqString, verbose=verbose)
    time.sleep(1)

    result = "### Moved to NEXT"
    return result 

def set_next_radec(telSock,ra, dec, verbose=True):
   
    reqString = "%s TCS %i MANUAL" % (TELID, REF_NUM)
    
    resp = query_telescope(telSock, reqString, verbose=verbose)
    time.sleep(1)

    if dec[0] != '-':
        pm_DEC = '+'
    else:
        pm_DEC = '-'
    if ra[0] != '-':
        pm_RA = '+'
    else:
        pm_RA = '-'

    pm_RA = '+'

    if (ra[0] == '+') or (ra[0] == '-'):
        ra = ra[1:]
    if (dec[0] == '+') or (dec[0] == '-'):
        dec = dec[1:]

    reqString = "%s TCS %i NEXTDEC %s" % (TELID, REF_NUM, pm_DEC + dec)
    
    resp = query_telescope(telSock, reqString, verbose=verbose)
    time.sleep(1)

    reqString = "%s TCS %i NEXTRA %s" % (TELID, REF_NUM, pm_RA+ra)
    
    resp = query_telescope(telSock, reqString, verbose=verbose)

    result = "### SET NEXT RA: %s, DEC: %s" % (str(ra), str(dec))
    return result 
        
def plotguiderimage(img):

    mpl.imshow(np.log10(img), cmap='gray',interpolation='none',origin='lower')
    mpl.show()

def get_rotation_solution(rotangle, guideroffsets,forcerot=90):

    x_sol = np.array([0.0, plate_scale])
    y_sol = np.array([plate_scale, 0.0])

    forcerot = False
    if forcerot == True:
        rotangle = 90

    rotangle = rotangle - 90 - 0.26
    rotangle_rad = rotangle*np.pi/180.0
    rotation_matrix = np.array([[np.cos(rotangle_rad),1*np.sin(rotangle_rad)],\
        [-1*np.sin(rotangle_rad), np.cos(rotangle_rad)]])
    rotation_matrix_offsets = np.array([[np.cos(rotangle_rad),-1*np.sin(rotangle_rad)],\
        [1*np.sin(rotangle_rad), np.cos(rotangle_rad)]])

    #if (rotangle < 90) & (rotangle > 0):
    #    rotation_matrix = rotation_matrix_offsets
    #    print "CHANGING MATRIX"

    offsets = np.dot(rotation_matrix_offsets, guideroffsets[:2])
    x_rot = np.dot(rotation_matrix, x_sol)
    y_rot = np.dot(rotation_matrix, y_sol)

    offsets[0] = offsets[0] * np.cos(guideroffsets[2] * np.pi / 180.)

    return offsets, x_rot, y_rot

def wifis_simple_guiding_setup(telSock, cam, exptime, gfls, rotangle, goffsets):

    #Some constants that need defining
    #exptime = 1500

    #Gets the rotation solution so that we can guide at any instrument rotation angle
    guideroffsets = [float(goffsets[0].text()), float(goffsets[1].text())]
            
    offsets, x_rot, y_rot = get_rotation_solution(telSock, rotangle, guideroffsets)

    #Take image with guider (with shutter open)
    cam.set_exposure(exptime, frametype="normal")
    cam.end_exposure()

    #Takes initial image
    img1 = cam.take_photo()
    img1size = img1.shape
    boxsize = 30

    result = None
    result2 = None
   
    #Checks to see if there exists a guiding star for this target
    if gfls[1] and (gfls[0] != ''):
        #Sets the larger boxsize for guiding setup
        boxsize_f = 25
        
        #Get the original guidestar coordinates.
        f = open(gfls[0], 'r')
        lines = f.readlines()

        spl = lines[0].split()
        starx1old, stary1old = int(spl[0]), int(spl[1])

        centroidxold, centroidyold = [], []
        diffxold, diffyold = [], []
        if len(lines) > 1:
            for l in range(1, len(lines)):
                spl = l.split()
                centroidxold.append(int(spl[0]))
                centroidyold.append(int(spl[1]))
                diffxold.append(int(spl[0]) - starx1old)
                diffyold.append(int(spl[1]) - stary1old)

        if len(lines) > 1:
            inbox = numstarsinbox(centroidxold, centroidyold, starx1old, stary1old, boxsize_f)

        if len(inbox) > 0:
            #Create box around star and check if star is in box. If star, correct it. If no star, reinitialize guiding
            imgbox = img1[stary1old-boxsize_f:stary1old+boxsize_f, starx1old-boxsize_f:starx1old+boxsize_f]
            worked, result2 = checkstarinbox(imgbox, boxsize_f, telSock, rotangle, guideroffsets,\
                    multistar = [diffxold, diffyold, inbox])
        else:
            #Create box around star and check if star is in box. If star, correct it. If no star, reinitialize guiding
            imgbox = img1[stary1old-boxsize_f:stary1old+boxsize_f, starx1old-boxsize_f:starx1old+boxsize_f]
            worked, result2 = checkstarinbox(imgbox, boxsize_f, telSock, rotangle, guideroffsets, multistar = False)
        
        if worked:
            #If we could put a star at the right coordinates, set the guiding coords to the old coords
            starx1 = starx1old
            stary1 = stary1old
            result = "FOUND OLD GUIDE STAR...CORRECTING"
            fieldinfo = None
        else:
            #If we could not move a star to the right coordinates, then restart guiding for this object
            result = "COULD NOT FIND OLD GUIDESTAR IN IMAGE...SELECTING NEW GUIDESTAR"
            starx1, stary1, centroidx,centroidy,Iarr,Isat,width, gs = findguidestar(img1, gfls)
            fieldinfo = [centroidx,centroidy,Iarr,Isat, width]
    else:
        #restart guiding by selecting a new guide star in the image 
        starx1, stary1, centroidx,centroidy,Iarr,Isat,width,gs = findguidestar(img1,gfls)
        fieldinfo = [centroidx,centroidy,Iarr,Isat, width]
    
    #Make sure were guiding on an actual star. If not maybe change the exptime for guiding.
    print starx1, stary1
    #Record this initial setup in the file
    if (gfls[0] != '') and (starx1 not in [None, False, "NoStar"]):
        f = open(gfls[0], 'w')
        f.write('%i\t%i\t%i\t%i\n' % (starx1, stary1, exptime, Iarr[gs]))
        for j in range(len(centroidx)):
            if j == gs:
                continue
            f.write('%i\t%i\t%i\t%i\n' % (centroidy[j], centroidx[j], exptime, Iarr[j]))
        f.close()
    

    return [offsets, x_rot, y_rot, stary1, starx1, boxsize, img1, result, result2, fieldinfo]

def numstarsinbox(centroidx, centroidy, starx1, stary1, boxsize):
    
    inbox = []
    for i in range(len(centroidx)):
        if (centroidx[i]  > starx1 - boxsize) and (centroidx[i] < starx1 + boxsize) \
                and (centroidy[i] > stary1 - boxsize) and (centroidy[i] < stary1 + boxsize):
            inbox.append(i)
    
    return inbox

def findguidestar(img1, gfls):
    #check positions of stars    
    CFReturns = WA.centroid_finder(img1, plot=False)

    if CFReturns == False:
        return None, None, False, False, False, False, False

    centroidx, centroidy, Iarr, Isat, width = CFReturns 

    #for i in CFReturns:
    #    print i

    bright_stars = np.argsort(Iarr)[::-1]

    #Choose the brightest non-saturated star for guiding
    try:
        guiding_star = bright_stars[0]
    except:
        return None,None,centroidx,centroidy,Iarr,Isat,width

    #Checking to see if the star is in the "center" of the field and isn't saturated
    for star in bright_stars:
        if (centroidx[star] > 50) and (centroidx[star] < 950) and \
            (centroidy[star] > 50) and (centroidy[star] < 950):
            if Isat[star] != 1:
                guiding_star = star
                break 
    
    stary1 = centroidx[guiding_star]
    starx1 = centroidy[guiding_star] 

    if Iarr[guiding_star] < 9000:
        return None,None,centroidx,centroidy,Iarr,Isat,width

    if Isat[guiding_star] == 1:
        return False, False, centroidx, centroidy, Iarr, Isat, width

    if (centroidx[guiding_star] < 50) or (centroidx[guiding_star] > 950) or \
            (centroidy[guiding_star] > 50 and centroidy[guiding_star] > 950):
        return 'NoStar', 'NoStar', centroidx, centroidy, Iarr, Isat, width

    return starx1, stary1, centroidx,centroidy,Iarr,Isat,width,guiding_star

def checkstarinbox(imgbox, boxsize, telSock, rotangle, guideroffsets, multistar = False):

    #platescale = 0.29125 #"/pixel
    result = []

    offsets, x_rot, y_rot = get_rotation_solution(telSock, rotangle, guideroffsets)
    
    #Try centroiding
    CFReturns = WA.centroid_finder(imgbox, plot=False)

    if CFReturns == False:
        return [False, None]

    centroidx, centroidy, Iarr, Isat, width = CFReturns

    if not multistar:
        try:
            #If centroid worked, great
            new_loc = np.argmax(Iarr)
        except:
            #If centroid didn't work, exit and restart gudding
            return [False, None]

        newx = centroidx[new_loc]
        newy = centroidy[new_loc]

        #Figure out how to move based on the rotation solution
        dx = newx - boxsize 
        dy = newy - boxsize
        d_ra = dx * x_rot
        d_dec = dy * y_rot
        radec = d_ra + d_dec

        result.append("INITIAL MOVEMENT TO GET SOURCE BACK IN CENTER")
        result.append("X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f\n" \
           % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale))

        #Move the telescope if the required movement is greater than 0.5" 
        lim = 0.5
        r = -1
        d = -1

        if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
            result.append("NOT MOVING, TOO SMALL SHIFT")
        elif abs(radec[1]) < lim:
            result.append("MOVING DEC ONLY")
            move_telescope(telSock, 0.0, d*radec[0], verbose=False)
        elif abs(radec[0]) < lim:
            result.append("MOVING RA ONLY")
            move_telescope(telSock, r*radec[1], 0.0, verbose=False)
        else:
            move_telescope(telSock,r*radec[1],d*radec[0], verbose=False)
        
        time.sleep(2)

        return [True, result]
    else:
        diffxold, diffyold, inbox = multistar
        inbox_xold, inboxy_old = [], []
        for i in inbox:
            inbox_xold.append(diffxold[i])
            inboy_xold.append(diffyold[i])

        try:
            #If centroid worked, great
            new_loc = np.argmax(Iarr)
        except:
            #If centroid didn't work, exit and restart gudding
            return [False, None]

        newx = centroidx[new_loc]
        newy = centroidy[new_loc]
        
        #Figure out how to move based on the rotation solution
        dx = newx - boxsize 
        dy = newy - boxsize
        d_ra = dx * x_rot
        d_dec = dy * y_rot
        radec = d_ra + d_dec

        result.append("INITIAL MOVEMENT TO GET SOURCE BACK IN CENTER")
        result.append("X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t\t%f\n" \
           % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale))

        #Move the telescope if the required movement is greater than 0.5" 
        lim = 0.5
        r = -1
        d = -1

        if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
            result.append("NOT MOVING, TOO SMALL SHIFT")
        elif abs(radec[1]) < lim:
            result.append("MOVING DEC ONLY")
            move_telescope(telSock, 0.0, d*radec[0], verbose=False)
        elif abs(radec[0]) < lim:
            result.append("MOVING RA ONLY")
            move_telescope(telSock, r*radec[1], 0.0, verbose=False)
        else:
            move_telescope(telSock,r*radec[1],d*radec[0], verbose=False)

        #result.append("Checking if right guide star")

def run_guiding(inputguiding,  cam, telSock, rotangle):
   
    #Get all the parameters from the guiding input
    offsets, x_rot, y_rot, stary1, starx1, boxsize, img1  = inputguiding

    #Take an image
    img = cam.take_photo(shutter='open')
    starx_box = int(starx1)
    stary_box = int(stary1)
    imgbox = img[stary_box-boxsize:stary_box+boxsize, starx_box-boxsize:starx_box+boxsize]

    #FInd the star in the box
    CFReturns = WA.centroid_finder(imgbox, plot=False)
    if CFReturns == False:
        return
    
    centroidx, centroidy, Iarr, Isat, width = CFReturns

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

    guideinfo = "X Offset:\t%f\nY Offset:\t%f\nRA ADJ:\t%f\nDEC ADJ:\t%f\nPix Width:\t%f\nSEEING:\t%f" \
       % (dx,dy,radec[1],radec[0],width[0], width[0]*plate_scale)

    ##### IMPORTANT GUIDING PARAMETERS #####
    lim = 0.6 #Changes the absolute limit at which point the guider moves the telescope
    d = -0.9 #Affects how much the guider corrects by. I was playing around with -0.8 but the default is -1. Keep this negative.
    #######################################

    deltRA = 0
    deltDEC = 0

    guidingon=True
    if guidingon:
        if (abs(radec[1]) < lim) and (abs(radec[0]) < lim):
            guideresult = "NOT MOVING, TOO SMALL SHIFT\n"
            pass
        elif abs(radec[1]) < lim:
            guideresult = "MOVING DEC ONLY\n"
            deltDEC = d*radec[0]
            move_telescope(telSock, 0.0, d*radec[0], verbose=False)
        elif abs(radec[0]) < lim:
            guideresult = "MOVING RA ONLY\n"
            deltRA = d*radec[1]
            move_telescope(telSock, d*radec[1], 0.0, verbose=False)
        else:
            deltRA = d*radec[1]
            deltDEC = d*radec[0]
            move_telescope(telSock,d*radec[1],d*radec[0], verbose=False)
            guideresult = "\n"

    #Record for guiding checking later
    f = open('/home/utopea/elliot/guidinglog/'+time.strftime('%Y%m%dT%H')+'.txt', 'a')
    f.write("%f\t%f\n" % (radec[1],radec[0]))
    f.close()

    return deltRA, deltDEC, guideinfo, guideresult, img








