#gui that controls all of the calibration unit componants

# Miranda Jarvis Oct 2015
# Updated by Elliot Meyer Jan 2016, May 2017

from pylab import *
import serial
from time import *
from Tkinter import *
import ttk
import sys
import signal
from power_control import connect_to_power

###################################################
def timeout(func, args=(), kwargs={}, timeout_duration=1, default=None):
    """Handles timeouts when querying the arduinos. Ensures the program does not hang."""
    class TimeoutError(Exception):
        pass

    def handler(signum, frame):
        raise TimeoutError()

    # set the timeout handler
    signal.signal(signal.SIGALRM, handler) 
    signal.alarm(timeout_duration)
    try:
        result = func(*args, **kwargs)
    except TimeoutError as exc:
        result = default
    finally:
        signal.alarm(0)

    return result

def setup_arduinos(fport,sport):
    """Connect to both arduinos. Ensure the USB hub is powered. 
    The script determines which arduino is which.
    Returns the two arduino serial variables."""

    #sphere, flag = connect_sphere(fport, sport)
    sphere = serial.Serial(sport, 9600)
    print("Resetting Sphere Arduino")
    sleep(3) 
    
    out = None
    if sphere:
        sphere.write(bytes('L'))
        out=timeout(sphere.readline)

        if not out:
            print 'Port may be wrong for the sphere arduino, trying other port...'
            fport,sport=sport,fport
            sphere=serial.Serial(sport,9600)
            print("Resetting Sphere Arduino")
            sleep(3)
        elif out.split('\r')[0] != 'OFF':
            print 'Port may be wrong for the sphere arduino, trying other port...'
            fport,sport=sport,fport
            sphere=serial.Serial(sport,9600)
            print("Resetting Sphere Arduino")
            sleep(3)
    else:
        print 'Port may be wrong for the sphere arduino, trying other port...'
        fport,sport=sport,fport
        sphere=serial.Serial(sport,9600)
        print("Resetting Sphere Arduino")
        sleep(3)
        if not sphere:
            print 'It appears that there are no arduinos attached. Please check the connections.'
            return

    #Now connecting to the flipper Arduino
    try: flip = serial.Serial(fport, 9600)
    except: 
        print 'Warning: unable to conect to arduino at'+fport
        flip = None
    print("Resetting Flipper Arduino")
    sleep(3) 

    #put each pin to low mode (won't move flippers if power is off which could 
    #cause some problems)
    if flip:
        flip.write(bytes('L'))
        flip.write(bytes('M'))

    #first check to make sure there aren't any messages cached on the arduino 
    #defined timeout() above to stop it after a few seconds 
    
    if flip:
        out='0' #initialize loop parameter

        #loop until out = None if function times out rather than finishing will 
        #return NONE instead of whatever was written on the board
        while out!=None:     
            #read off the board until empty   
            out=timeout(flip.readline) 

        #do same thing for sphere arduino 
        out='0' #initialize loop parameter

        while out!=None:
            #read off the board until empty   
            out=timeout(sphere.readline) 

        #put pin to low mode
        sphere.write(bytes('L'))

    return flip, sphere

class CalibrationControl(): 
    """Defines the GUI including the buttons as well as the button functions."""
    
    def __init__(self):#,switch1,switch2): #setup basic gui stuff
        
        #port for flipper arduino
        fport='/dev/flipper_arduino'
        #port for sphere arduino
        sport='/dev/sphere_arduino'

        ser,ser2 = setup_arduinos(fport,sport)
       
        if (ser == None) and (ser2 == None):
            print "THE ARDUINOS ARE NOT PROPERLY CONNECTED. PLEASE CHECK THEM AND RESTART THIS SCRIPT."
            print "######### CALIBRATION CONTROL WILL NOT WORK #############"
            return

        self.ser = ser
        self.ser2 = ser2
        self.switch1, self.switch2 = connect_to_power()

    #Flipper Controls#  
    ######################################################
    def flip1pos1(self):
        self.ser.write(bytes('M'))
        q='1'
        while q=='1':
            self.ser.write(bytes('V'))
            q=self.ser.readline()[0]
            sleep(1)

    def flip1pos2(self):
        self.ser.write(bytes('N'))
        q='1'
        while q=='1':
            self.ser.write(bytes('V'))
            q=self.ser.readline()[0]
            sleep(1)

    def flip2pos1(self):
        self.ser.write(bytes('L'))
        q='1'
        while q=='1':
            self.ser.write(bytes('R'))
            q=self.ser.readline()[0]
            sleep(1)

    def flip2pos2(self):
        self.ser.write(bytes('H'))
        q='1'
        while q=='1':
            self.ser.write(bytes('R'))
            q=self.ser.readline()[0]
            sleep(1)

    def flatsetup(self):
        self.flip2pos2()
        self.flip1pos1()
        if self.switch2[0].state == 'OFF':
            self.switch2[0].state = 'ON'
        if self.switch2[1].state == 'ON':
            self.switch2[1].state = 'OFF'


    def arcsetup(self):
        self.flip2pos2()
        self.flip1pos2()
        if self.switch2[0].state == 'ON':
            self.switch2[0].state = 'OFF'
        if self.switch2[1].state == 'OFF':
            self.switch2[1].state = 'ON'

    def sourcesetup(self):
        self.flip2pos1()
        if self.switch2[0].state == 'ON':
            self.switch2[0].state = 'OFF'
        if self.switch2[1].state == 'ON':
            self.switch2[1].state = 'OFF'

def run_calib_gui(tkroot,mainloop = False):
    """Function for running the calibration as part of the launch_controls.py
    program. To run as standalone just run this scipt."""

    #port for flipper arduino
    fport='/dev/flipper_arduino'
    #port for sphere arduino
    sport='/dev/sphere_arduino'

    ser,ser2 = setup_arduinos(fport,sport)
    
    if (ser == None) and (ser2 == None):
        print "THE ARDUINOS ARE NOT PROPERLY CONNECTED. PLEASE CHECK THEM AND RESTART THIS SCRIPT"
    
    print 'Activating Calibration GUI'

    root = Toplevel(tkroot) #gui set up stuff
    root.title("Calibration Unit Control") #gui name

    app = MainApplication(root,ser,ser2) #set up gui class

    return ser, ser2

def run_calib_gui_standalone():
    """Standalone version of this script for use in case launch_controls fails
    or for testing"""

    #port for flipper arduino
    fport='/dev/flipper_arduino'

    #port for sphere arduino
    sport='/dev/sphere_arduino'

    ser,ser2 = setup_arduinos(fport,sport)
   
    if (ser == None) and (ser2 == None):
        print "THE ARDUINOS ARE NOT PROPERLY CONNECTED. PLEASE CHECK THEM AND RESTART THIS SCRIPT"

    print 'activating gui'
    root = Tk() #gui set up stuff
    root.title("Calibration Unit Control") #gui name

    app = MainApplication(root,ser,ser2) #set up gui class

    root.mainloop() #run gui loop
    
    #clean up in case user didn't hit exit calibration mode button: 
    #make sure all arduino pins in low mode
    if ser:
        ser.write(bytes('L'))
        ser.write(bytes('M'))
    #ser2.write(bytes('L'))

if __name__ == '__main__':
    run_calib_gui_standalone()
