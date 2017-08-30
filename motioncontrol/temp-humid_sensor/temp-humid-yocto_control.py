#code for use of the temperature and humidity sensor. A lot of it is copied from the manual which can be found here: http://www.yoctopuce.com/projects/yoctometeo/METEOMK1.usermanual-EN.pdf
#relies on the yocto-meteo libraries (http://www.yoctopuce.com/FR/downloads/YoctoLib.python.21816.zip)
#the location contents of the zip file downloaded from the yoctopuce will need to be fed into the code in line 11. 
#this should be run from a fairly isolated directory so that it's log files (save in the same directory as the code right now) don't get all mixed up with other stuff.

#this code reads off the yocto-meteo and prints the results to terminal, it also prints a warning if the values are outside of a region defined in this code
#on closing it saves a log file with the temp and humid readings while the code was running

import time
import sys
sys.path.insert(0, '/home/miranda/Documents/yocto/library/Sources') #tell it where to find source files this will need to be changed for each user 

#import libraries to control sensor
from yocto_api import *
from yocto_humidity import * 
from yocto_temperature import *

#how long to wait between readings in seconds
t=5

#humidity range, for now based on quoted operating ranges for sphere power supply, fiber usb converter, power control bars, guider / flipper power supplies and flippers
humidmin=30
humidmax=80

#temperature range, for now based on quoted operating ranges for sphere power supply, lakeshore, fiber usb converter, power control bars, guider / flipper power supplies and flippers
tempmin=15
tempmax=35

#lines 28-50 are taken almost line by line from the example code given in the manual pretty much connect to the sensor, then set up functions to read it off

errmsg=YRefParam()

#Get access to your device, connected locally on USB for instance 

if YAPI.RegisterHub("usb", errmsg)!= YAPI.SUCCESS:
    sys.exit("init error"+errmsg.value)

target='any'

if target=='any':
# retreive any humidity sensor 
      sensor = YHumidity.FirstHumidity() 
      if sensor is None :
          die('No module connected')
      m = sensor.get_module()
      target = m.get_serialNumber()

print 'looked at thing'
if not m.isOnline() : die('device not connected')


humSensor = YHumidity.FindHumidity(target+'.humidity')
tempSensor = YTemperature.FindTemperature(target+'.temperature')

#write readings to a file saved as temp_humid_date

current_time = datetime.datetime.now().time() #get time
current_time = current_time.isoformat() #put in format I want

#set up log file
target = open('temp_humid_'+current_time+'.log', 'w')
target.write('#prints humidity as %RH and temp in degrees celsius every 5s or so \n')
target.write('#humidity(%RH) \t temperature(celsius) \n')


#read sensor
while True:
	t=tempSensor.get_currentValue() #read temp
	h=humSensor.get_currentValue() #read humid
	 
	#print results
	print h,'percent RH' 
	print t,'degrees celcious'
	
	#write to file
	target.write(str(h)+'\t'+str(t)+'\n')
	if h<humidmin or h>humidmax: print 'error, humidity out of desired range!!!'
	if t<tempmin or t>tempmax: print 'error, temperature out of desired range!!!'
	
	#wait 5 second then do again
	time.sleep(t)
