import power_control as pc
import numpy as np
import matplotlib.pyplot as mpl
import time

lim = 200
fl = '/home/utopea/WIFIS-Team/controlcode/monitor/Mon Jun 12 13-08-34 2017.csv'
#fl = '/Users/relliotmeyer/wifiswarm/Sat May 13 12-14-54 2017.csv'
power = pc.power_edit()
switch = power[0]

while True:
    try:
        data = np.genfromtxt(fl, skip_footer=1, skip_header=1,delimiter=',')

#        time = data[:,1]
        temp = data[:,6]
        templast = float(temp[-1])

        print "TEMP IS: %f" % (templast)

        if templast > lim:
            print "TEMPERATURE REACHED LIMIT, SWITCHING OFF HEATER"
            switch.off(outlet=8)
            break
        time.sleep(5)
    except:
        print "Something went wrong...not sure but continuuing...\t"+time.ctime()
        time.sleep(5)


#timediff = time - np.roll(time, 1)
#tempdiff = temp - np.roll(temp, 1)
#mpl.plot((time-time[0])/60/60,tempdiff/(timediff/60))
#mpl.plot(temp,tempdiff/(timediff/60))
#mpl.show()
