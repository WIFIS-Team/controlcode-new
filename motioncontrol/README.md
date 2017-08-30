# WIFIS System Control Scripts

## WIFIS Motor Controller
This is a GUI module used to control the motors for WIFIS. Three motors are currently installed.

### How to use
#### Starting up
Using the terminal, clone the repository, then navigate to the directory containing the module (under `/wherever_you_keep_your_code/WIFIS-Code/control/`). Enter the command

> ```python motor_controller.py```

to start up the GUI module. Immediately, you should see three columns of buttons – one for each motor.

#### Moving the motors
The first thing to remember is that the position and movement of motors is measured in *steps*, where **1000 steps equals one revolution**. Positive steps are in the clockwise direction, negative in the counterclockwise direction (e.g., –1000 steps equals one counterclockwise revolution). Position 0 is the initial position of the motor when it was powered on (also called the *home* position).

The various buttons are pretty straightforward:
* **Set** | sets the speed of revolution at the selected rate entered in the field above (default = 1000)
* **Step** | moves the motor by the selected number of steps (1 revolution = 1000 steps)
* **Home** | returns the motor to the home position (i.e., position 0)
* **Fwd** | (Forward) continuously rotates the motor clockwise at the determined speed
* **Rev** | (Reverse) continuously rotates the motor counterclockwise at the determined speed
* **Stop** | ceases the motor's operation, but keeps it on
* **Off** | turns the motor off

At a given moment, each motor can be in one of four states: **ON**, **MOVE**, **HOME**, or **OFF**. Note that the motor will not execute any "move" commands while it is already in a MOVE or HOME state. Click the Stop button to return it to the ON state prior to sending additional commands.

#### Exiting
Simply close the module – no special commands required`*`. Remember to shut off the power!

`*`*Optional*: you may wish to return the motor to the home position before exiting. This ensures that position 0 – the home position – is in the same place every time the motor is powered on. **There is no way to save the position internally**.

## WIFIS FLI Controller

### Dependencies

* Chimera
* Chimera-FLI
* Python-FLI
* FLI Linux Drivers
* FLI SDK

Install the FLI Linux Drivers and FLI SDK from FLI first. Then clone the repos of Chimera, Python-FLI, and Chimera-FLI and install in that order. The GUI should then work.

### Starting

To start the GUI navigate to WIFIS-Code/control and run,

> '''python fli_controller.py'''

### Operation Notes

* The focuser has a maximum extent of 7000 steps or roughly a 1/3 inch
* The CCD can get hot quickly so minimize operation time when not being cooled:


## Web Power Switch Control
This is a gui to control the two web power bars that will be powering most componants of WIFIS. NOTE: these can also be controled via a web browser on the control computer by going to their IP addresses (currently 192.168.0.110 for Power Control #1 and 192.168.0.120 for Power Control #2)

### How to use
Make sure you have both ''power_control.py'' and ''dlipower.py''. Both are saved in the directory ''Power_Control''

Run ''power_control.py''.

A gui window will apear, listing each of the plugs by a number and what should be plugged into it. Each plug has a button that toggles the power to that plug on and off. The status should update after a pause if the power is toggled elsewhere (example ''calibration_control_toplevel.py'' described later does this).

IMPORTANT NOTE: This code lags a bit so be sure to wait a few seconds after toggling the power for it to actually take effect. 


## Calibration Unit Control

(for a more detailed set of instructions on the GUI and the mechanical set up of the calibration unit componants see 'calibration_instructions.pdf' in the directory 'Calibration_Control')

This is a gui that can be used to easily perform calibration functions. Specifically it controls the two flip mirrors in the calibration unit, the arc-lamp and Integrating sphere power supplies and turns on and off the plugs powering each componant as needed. 

### How to use

Make sure have both ''calibration_control_toplevel.py'' and ''dlipower.py'' (which can be found in the directories 'Calibration_Control' and 'Power_Control' respectively).

Running the python script ''calibration_control_toplevel.py'' should start a gui. If not see the section below on 'if things aren't runnung correctly'.

The Gui is split vertically into two halves. The left contains a series of buttons which should be used to conrol the calibration unit in most scenarios. Buttons apear eather depressed or raised, this shows which buttons should be pushed at any given time. The Right half is used to monitor the status of and control individual elements should this be needed. NOTE: for normal operations one shouldn't need to control elements using the buttons on the right. 

####The function of the various buttons is descirbed below:
#####Left Side
* **Enter Calibration Mode** | This is the first button that should be pushed. Turns on power to the flippers, turns on power to the Integrating sphere, moves the mirror mounted on WIFIS into the calibration position that feeds light from the calibration unit into the instrument and blocks light from the telescope. 
* **Prepare to take Flats ** | moves the mirror in the calibration box to feed light from the integrating sphere into WIFIS, turns on the integrating sphere using ttl connection
* **Finished taking Flats** | turns off the integrating sphere using ttl connection
* **Prepare to take Arcs** | moves mirror in calibration box to feed light from arc lamp into WIFIS, turns arc lamp on.
* **Finished taking Arcs** | turns the arc lamp off
* **Exit Calibration Mode** | moves the mirror on WIFIS into observation mode (not blocking light from telescope) makes sure everything else off (flippers, integrating sphere (both at ttl and power), arc lamp)

#####Right Side:
The 'On/Off' buttons in the Integrating Sphere and Arc Lamp boxes toggle the power to the respective light sources (I will probably add another button to the sphere part to turn the sphere on / off with ttl. The status of each is also displayed (on or off)

Mirror Flippers: the status at the top is if power is being supplied to the flippers.  There are two buttons for each flipper that control what position they are, each is labeled to describe what positon that is, the depressed button is the current position of the mirror. The text to the right says if the mirror is currently in motion or not. 

### If things aren't running correctly:
The main places that I forsee things going wrong are with the arduinos and the flippers internal programing.

In the directory "Calibration_Control" are the codes to be programed into the two arduinos (for the integrating sphere and mirror flippers).  Lines 46 and 49 of the code are the locations where they are mounted, if these are wrong the code wil exit without opening the gui and print a warning that states which port did not connect, figure out where the arduino is actully mounted and edit either line 46 or 49 appropriatly. The code should automatically sort it out if the wrong one is given in the wrong line but the path to both arduinos needs to be given in one or the other of these lines. If problems persist makes sure you do have the right path on the right line since this will simplify things. 

The code will also exit without opening the gui if either of the power bars isn't connected properly, a warning will be printed saying which bar didn't connect. If this happens make sure the bar is powered on and the ethernet cables are plugged in at both ends. 

For the flippers themselves if misbehaving need to be plugged into a computer with windos via usb with the control softwear from Thorlabs installed. Their SMA plug one is set to ‘go to position’ mode with ‘Logic Edge Input (Swap Pos.) ‘ as the digital signal mode. SMA plug two is set to ‘Output: InMotion’ and digital signal mode: ‘Logic Level Output’.  Make sure the 'persistant settings' (or something like that) box is ticked to keep these instructions on the flippers until next plugged in.

##Temperature and Humidity sensor
Controls the yocto-meteo sensors

when "temp-humid-yocto_control.py" is run it prints the temperature and humidity as well as a warning if either is outside of a range set in the code, ever x seconds where x is set in the code and saves all readints in a log file.

To use simply run "temp-humid-yocto_control.py" in it's own directory. NOTE: relies on libraries from the yocto-puce website (http://www.yoctopuce.com/EN/products/usb-sensors/yocto-meteo)





