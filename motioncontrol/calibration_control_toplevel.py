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

class MainApplication(Frame): 
    """Defines the GUI including the buttons as well as the button functions."""
    
    def __init__(self,master,ser,ser2):#,switch1,switch2): #setup basic gui stuff
        Frame.__init__(self, master)
        self.grid()
        self.ser = ser
        self.ser2 = ser2
        self.create_widgets()
        self.switch1, self.switch2 = connect_to_power()

        if self.switch2[0].state == 'OFF':
            self.b7.config(fg='red')
        else:
            self.b7.config(fg='green')

        if self.switch2[1].state == 'OFF':
            self.b6.config(fg='red')
        else:
            self.b6.config(fg='green')


    def create_widgets(self): #create all the buttons and labesl and stuff
        
        ######################################################################
        # Integrating Sphere Control
        ######################################################
        Label(self, text="Integrating Sphere", font='bold').grid(row=0, \
            column=1, padx=15)

        Button(self, text="On/Off", command=self.toggle_sphere, width=5).grid(\
            row=0, column=3)
        Label(self, text="Status:", font='bold').grid(row=0, column=4)
        
        self.status_sphere = Label(self, text='OFF', font='bold', fg ='red' ) 
        self.status_sphere.grid(row=0, column=5)

        
        ######################################################################
        # Calibration Box Flipper Control 
        ######################################################

        Label(self, text="Flipper 1 (In Calibration Box)", font='bold',\
            anchor=W).grid(row=2, column=1,columnspan=2, padx=15,sticky="ew")
        self.b1=Button(self, text="Pos1 (Integrating Sphere)", \
            command=self.flip1pos1,relief=SUNKEN)
        self.b1.grid(row=2, column=3)
        self.b2=Button(self, text="Pos2 (Arc Lamp)", command=self.flip1pos2, \
            relief=RAISED)
        self.b2.grid(row=2, column=4)
        self.s1 = Label(self, text='in position', fg ='green' )
        self.s1.grid(row=2, column=5, padx=15)

        ######################################################################
        # WIFIS Flipper Control 
        ######################################################

        Label(self, text="Flipper 2 (On WIFIS)", font='bold',anchor=W).grid(\
            row=3, column=1,columnspan=2, padx=15,sticky="ew")
        self.b3=Button(self, text="Pos1 (Observation Mode)", \
            command=self.flip2pos1, relief=SUNKEN)
        self.b3.grid(row=3, column=3)
        self.b4=Button(self, text="Pos2 (Calibration Mode)", \
            command=self.flip2pos2, relief=RAISED)
        self.b4.grid(row=3, column=4)
        self.s2 = Label(self, text='in position', fg ='green' )
        self.s2.grid(row=3, column=5, padx=15)

        self.b5 = Button(self, text='Source Setup', \
                command=self.sourcesetup)
        self.b5.grid(row=4, column=2)
        self.b6 = Button(self, text='Arc Setup', \
                command=self.arcsetup)
        self.b6.grid(row=4,column=3)
        self.b7 = Button(self, text='Flat Setup', \
                command=self.flatsetup)
        self.b7.grid(row=4, column=4)
    #Sphere Control#
    ######################################################
    def toggle_sphere(self):
        #to toggle by arduino
        message=self.ser2.readline()[0:3]

        if message=='ON-':
            self.ser2.write(bytes('L'))
            self.status_sphere["text"] = "OFF"
            self.status_sphere["fg"] = "red"    
    
        if message=='OFF':
            self.ser2.write(bytes('H'))
            self.status_sphere["text"] = "ON"
            self.status_sphere["fg"] = "green"
        
    #Flipper Controls#  
    ######################################################
    def flip1pos1(self):
        self.ser.write(bytes('M'))
        self.s1["text"] = "In Motion"
        self.s1["fg"] = "red"
        self.update()
        q='1'
        while q=='1':
            self.ser.write(bytes('V'))
            q=self.ser.readline()[0]
            sleep(1)
        self.s1["text"] = "In Position"
        self.s1["fg"] = "green"
        self.b1['relief']=SUNKEN
        self.b2['relief']=RAISED

    def flip1pos2(self):
        self.ser.write(bytes('N'))
        self.s1['text']='In Motion'
        self.s1['fg']='red'
        self.update()
        q='1'
        while q=='1':
            self.ser.write(bytes('V'))
            q=self.ser.readline()[0]
            sleep(1)
        self.s1["text"] = "In Position"
        self.s1["fg"] = "green" 
        self.b2['relief']=SUNKEN
        self.b1['relief']=RAISED

    def flip2pos1(self):
        self.ser.write(bytes('L'))
        self.s2["text"] = "In Motion"
        self.s2["fg"] = "red"
        self.update()
        q='1'
        while q=='1':
            self.ser.write(bytes('R'))
            q=self.ser.readline()[0]
            sleep(1)
        self.s2["text"] = "In Position"
        self.s2["fg"] = "green"
        self.b3['relief']=SUNKEN
        self.b4['relief']=RAISED

    def flip2pos2(self):
        self.ser.write(bytes('H'))
        self.s2['text']='In Motion'
        self.s2['fg']='red'
        self.update()
        q='1'
        while q=='1':
            self.ser.write(bytes('R'))
            q=self.ser.readline()[0]
            sleep(1)
        self.s2["text"] = "In Position"
        self.s2["fg"] = "green" 
        self.b4['relief']=SUNKEN
        self.b3['relief']=RAISED

    def flatsetup(self):
        self.flip2pos2()
        self.flip1pos1()
        if self.switch2[0].state == 'OFF':
            self.switch2[0].state = 'ON'
            self.b7.config(fg='green')
        if self.switch2[1].state == 'ON':
            self.switch2[1].state = 'OFF'
            self.b6.config(fg='red') 


    def arcsetup(self):
        self.flip2pos2()
        self.flip1pos2()
        if self.switch2[0].state == 'ON':
            self.switch2[0].state = 'OFF'
            self.b7.config(fg='red')
        if self.switch2[1].state == 'OFF':
            self.switch2[1].state = 'ON'
            self.b6.config(fg='green')

    def sourcesetup(self):
        self.flip2pos1()
        if self.switch2[0].state == 'ON':
            self.switch2[0].state = 'OFF'
            self.b7.config(fg='red')
        if self.switch2[1].state == 'ON':
            self.switch2[1].state = 'OFF'
            self.b6.config(fg='red')

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
