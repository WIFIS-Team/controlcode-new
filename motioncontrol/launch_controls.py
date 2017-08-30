#############################
# Author:   Elliot Meyer
# Date:     Jan 2016
#############################

## This script launches all four control GUIs (Power, Calibration,
## Guider (FLI), and Motor). The Power control GUI is the ROOT GUI.

###################################################################
## TO SHUT DOWN ALL THE GUIS JUST CLOSE THE POWER CONTROL WINDOW ##
###################################################################

import calibration_control_toplevel as calib
import power_control as pc
import fli_controller as flic
import motor_controller as mot
import time

print "\nLaunching root (Power) control GUI...\n"
#Start power control GUI as main GUI & switch on USB hub
root, switch1, switch2= pc.run_power_gui()

#Allow for time for arduinos to connect
print "\nGiving time for USB devices to connect...\n"
time.sleep(15)
print "Continuing...\n"

#Set up Calib GUI
print "Setting up Calibration control GUI...\n"
ser, ser2 = calib.run_calib_gui(root)

#Set up FLI/Guider Control GUI
print "\nSetting up FLI control GUI..."
flic.run_fli_gui(root)

#Set up Motor Controller GUI
print "\nSetting up Motor control GUI...\n"
client = mot.run_motor_gui(root)

#Mainloop all GUIs
root.mainloop()

#Cleaning up
print "\nShutting down GUIs and cleaning up...\n"

#Closes the underlying socket connection
#client.close()
#Writes low signal to Arduino
#ser.write(bytes('L'))
#ser.write(bytes('M'))
#Turns off various power
#switch1[2].state = 'OFF'
#switch2[1].state = 'OFF'
#switch2[2].state = 'OFF'
#switch2[3].state = 'OFF'
print "###### Finished ######"
