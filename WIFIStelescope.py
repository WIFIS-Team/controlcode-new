import matplotlib.pyplot as mpl
import time, os
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

homedir = os.path.dirname(os.path.realpath(__file__))

#plate_scale = 0.29125
plate_scale = 0.2979146

#IP IS HARDCODED IN A FILE ON THE WIFIS CONTROL COMPUTER FOR SECURITY
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
                    print("### DONE RECEIVING TELEMETRY")
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

    f = open(homedir+'/data/BokTelemetry.txt', 'w')
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
        
def get_rotation_solution(rotangle, guideroffsets,forcerot=90):

    print guideroffsets, rotangle

    x_sol = np.array([0.0, plate_scale])
    y_sol = np.array([plate_scale, 0.0])

    forcerot = False
    if forcerot == True:
        rotangle = 90

    rotangle = rotangle - 90. - 0.21#0.26
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

    #offsets[0] = offsets[0] * np.cos(guideroffsets[2] * np.pi / 180.)

    return offsets, x_rot, y_rot

