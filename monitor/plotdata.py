import numpy as np
import matplotlib.pyplot as plt

def deriv(x,y):
    
    deriv_arr = np.zeros(len(x))
    
    for i in range(len(x)-1):
        deriv_arr[i] = (y[i+1]-y[i])/(x[i+1]-x[i])
        
    return(deriv_arr)

def smooth(x,window_len=11,window='hanning'):
        if x.ndim != 1:
                raise ValueError, "smooth only accepts 1 dimension arrays."
        if x.size < window_len:
                raise ValueError, "Input vector needs to be bigger than window size."
        if window_len<3:
                return x
        if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
                raise ValueError, "Window is on of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'"
        s=np.r_[2*x[0]-x[window_len-1::-1],x,2*x[-1]-x[-1:-window_len:-1]]
        if window == 'flat': #moving average
                w=np.ones(window_len,'d')
        else:  
                w=eval('np.'+window+'(window_len)')
        y=np.convolve(w/w.sum(),s,mode='same')
        return y[window_len:-window_len+1]

plt.close('all')
plt.ion()

data = np.loadtxt('cooldown03182017.csv',delimiter=',',usecols=(1,2,3,7))

# 1437076800.928176 July 16/2015 4:00 pm refill

time = (data[:,0]-1489599000.248219)/3600.
temp1 = data[:,1]
temp2 = data[:,2]
pressure = data[:,3]

plt.figure(1)
plt.plot(time,temp2)
plt.plot(time,temp1)
plt.title('First Toronto Cooldown of WIFIS Cryostat (Start July 16/2015)')
plt.xlabel('Time Since Final Fill (hr)')
plt.ylabel('Temperature (K)')
plt.grid(True)

plt.savefig('full_temp.png',dpi=300)

plt.figure(2)
plt.plot(time,temp2)
plt.plot(time,temp1)
plt.title('First Toronto Cooldown of WIFIS Cryostat (Start July 16/2015)')
plt.xlabel('Time Since Final Fill (hr)')
plt.ylabel('Temperature (K)')
#plt.xlim([-5,15])
plt.grid(True)
plt.savefig('full_temp_zoom.png',dpi=300)

plt.figure(3)
grad = np.diff(temp2)*60/np.diff(time)
plt.plot(time,smooth(deriv(time,temp2),window_len=30)/60.,'.-')
plt.xlabel('Time Since Final Fill (hr)')
plt.ylabel('Cooling Rate (K/min)')
plt.title('Thermal Switch Performance (Start July 16/2015)')
plt.grid(True)
plt.savefig('cooling_rate.png',dpi=300)

plt.figure(4)
plt.plot(time,pressure)
plt.yscale('log')
plt.xlabel('Time Since Final Fill (hr)')
plt.ylabel('Pressure (Torr)')
plt.title('First Toronto Cooldown of WIFIS Cryostat (Start July 16/2015)')
plt.grid(True)
plt.savefig('full_pressure.png',dpi=300)
