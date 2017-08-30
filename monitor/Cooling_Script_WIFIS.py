#Program Functions

# -- Read temperatures from temperature controller
# -- Generate setpoint that changes at a rate defined by the 'cooling_gradient' variable
# -- Turn off heaters if temperature gradient is warming up faster than specified in max_gradient
# -- Increase heater dissipation if temperature gradient is cooling faster than specified in max_cooling_gradient
# -- Write temperature readings to file
# -- Generate a webpage with temperature info.

#User parameters
temperature_limit = 300.0  #heaters will turn off above this temperature regardless of all other conditions
interval = 5.0 #time between each batch of sensor reading in seconds, should not be less than 5
max_gradient = +0.6 #if temperature rate of change is larger than this number, turn off heaters, in k/min, should be postive
max_cooling_gradient = -1.0 #fastest cooling allowed, should be negative
cooling_gradient = -0.8 #target cooling gradient (should be slower than max_cooling_gradient), should be negative
setpoint_update_interval = 60.0 #seconds between setpoint updates
manual_heater = 30.0 #how much extra power to use if cooling faster than max_cooling_gradient, in %
PID = '50,50,0'#PID control parameters to use, first value is P, second value is I, 3rd value is D
website_update_frequency = 15.0  #how often to upload sensor readings and graphs to the website, in seconds.
pc_ref_voltage = 5.04


#global variables, do not change
import serial
import time
import csv
from collections import deque
import sys
import os
import paramiko
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy
import Image
sensorList = ['A', 'B', 'C', 'D1', 'D2'] #name of inputs
outputList = ['1','2'] #name of outputs
last_read = []
last_setpoint = 0.0
input_A_list = deque([])
input_B_list = deque([])
input_C_list = deque([])
input_D_list = deque([])
input_E_list = deque([])
heater_1_list = deque([])
heater_2_list = deque([])
setpoint_1_list = deque([])
setpoint_2_list = deque([])
pressure_list = deque([])
dT_dt_list= deque([])
timestamp_list = deque([])
startTime = time.time()
f=open(time.asctime().replace(':', '-')+'.csv', 'w')
outData = csv.writer(f, dialect='excel')
outFileHeader = ['#Time Stamp','seconds since epoch', 'Input A',  'Input B',  'Input C',  'Input D', 'Input E', 'Output 1', 'Output 2','Setpoint 1','Setpoint 2','pressure']
outData.writerow(outFileHeader)
last_setpoint_update_time = startTime - setpoint_update_interval
ser = serial.Serial()
ser_pressure = serial.Serial()
g_dT_dt = 0.0 #global variable containing the current DT/dt
image_generated = False #did the script produce history plots of temperatures?


#=====================================Cooling Algorithm is contained in this function ========================================================
def cooling_setpoints(): #dynamically generate setpoints for cooling
    global last_read
    global last_setpoint
    global last_setpoint_update_time
    global g_dT_dt
    heater_off = False #are the heaters currently on?
    mout_set = False
    actual_setpoint_update_interval = setpoint_update_interval
    last_website_upload_time = time.time()
    
    while True: #Will run until interrupted by the user. Will read the sensors at regular intervals as set in the 'interval' variable, and command the temperature controller to change setpoint every 'setpoint_update_interval' 
        time_now = time.time()
        
        if len(last_read) == 0: #first iteration, just read the sensors
            last_read = read_temperature()
            stored_Temperature = (float(last_read[2])+float(last_read[3]))/2
            stored_Time = float(last_read[1])
            print last_read #====Testing
            print 'first run' #====Testing
            wait_time(interval-(time.time()-time_now))
            continue #skip the rest of the loop
            
        current_read = read_temperature()
        print current_read #====Testing
        
        dt = float(last_read[1])-float(current_read[1]) #time between reads, in seconds
        dT_A = float(last_read[2])-float(current_read[2]) #difference in input A readings
        dT_B = float(last_read[3])-float(current_read[3]) #difference in input B readings
        dT_dt_A = dT_A/(dt/60.0)
        dT_dt_B = dT_B/(dt/60.0) #convert to K/min
        
        average_dT_dt = (dT_dt_A+dT_dt_B)/2.0 #average the reading across both sensors
        g_dT_dt = average_dT_dt
        
        print 'DT/dt: ',  average_dT_dt
        
        Td = (float(current_read[2])+float(current_read[3]))/2.0 #detector temperature is the average of input A and B
        Td = float(current_read[3])
        Twork = float(current_read[6]) #worksurface temperature is input D
        
        last_read = current_read #update the variable
        write_html(current_read) #upload readings to website
        record_readings_to_file(current_read) #record the readings to file
        if time_now - last_website_upload_time >= website_update_frequency:
            upload_html_and_plots() #upload readings to website
            last_website_upload_time = time.time()
        
        
        if Td > temperature_limit:
            turn_off_heaters()
            heater_off = True
            print 'Temperature Exceeds max limit, heaters turned off.'
#            print 'Trigger 0' #====Testing
            wait_time(interval-(time.time()-time_now))
            continue #skip the rest of the loop
        
        if heater_off: #If heaters has been turned off in previous loop, turn it back on
            turn_on_heaters()
            heater_off = False
            print 'HEATERS Turned ON'
#            print 'Trigger 1' #====Testing
            

        if average_dT_dt > max_gradient: #If temperature is increasing faster than rate set in 'max_gradient', turn off the heaters
            turn_off_heaters()
            heater_off = True
            print 'HEATERS Turned OFF'
            wait_time(interval-(time.time()-time_now))
#            print 'Trigger 3' #====Testing
            continue #skip the rest of the loop
        
        if average_dT_dt > cooling_gradient: #cooling slower than specified, update setpoint to follow the real temperature
            stored_Temperature = (float(current_read[2])+float(current_read[3]))/2
            stored_Temperature = float(current_read[3])
            stored_Time = float(current_read[1])
        #new setpoints are always generaged based on the stored temperautre
        time_since_stored_Temperature_recorded = time.time()-stored_Time
#        print 'Time since stored temperature update: ', time_since_stored_Temperature_recorded #====Testing
        new_setpoint = stored_Temperature + cooling_gradient*((time_since_stored_Temperature_recorded+actual_setpoint_update_interval)/60.0)
            
        if average_dT_dt < max_cooling_gradient: #if cooling too fast, manually increase power dissipation of the heaters (final heater output = PID + MOUT)
#        if False: #Not using this part of the algorithm
            cmd_String_A = 'MOUT '+'1,'+ str(manual_heater)+'\n'
            sendCmdPacket(cmd_String_A)
            time.sleep(0.05)
            
            cmd_String_B = 'MOUT '+'2,' + str(manual_heater)+'\n'
            sendCmdPacket(cmd_String_B)
            time.sleep(0.05)
            
            mout_set = True
            print 'Extra power to heaters',  manual_heater #====Testing
#            print 'Trigger 5' #====Testing
        else:
            if mout_set: #If heater dissipation has been manually increased in the previous loop, reset the manual component to 0.
                cmd_String_A = 'MOUT '+'1,'+ '0'+'\n'
                sendCmdPacket(cmd_String_A)
                time.sleep(0.05)
                cmd_String_B = 'MOUT '+'2,' + '0'+'\n'
                sendCmdPacket(cmd_String_B)
                time.sleep(0.05)
            
                mout_set = False
                print 'Heaters reset to normal' #====Testing
#                print 'Trigger 2' #====Testing
            
            
        #send the new setpoints to the controller
        if float(current_read[1]) -  last_setpoint_update_time>= setpoint_update_interval - interval: #there always seems to be 1 too many read cycle between setpoint updates.
            cmd_String_A = 'SETP '+'1,'+ str(new_setpoint)+'\n'
            sendCmdPacket(cmd_String_A)
            time.sleep(0.05)
            cmd_String_B = 'SETP '+'2,' + str(new_setpoint)+'\n'
            sendCmdPacket(cmd_String_B)
            time.sleep(0.05)
            actual_setpoint_update_interval = time.time() - last_setpoint_update_time
            last_setpoint_update_time = time.time()
            print 'actual time since setpoint update: ',  actual_setpoint_update_interval
            
            print 'Trigger 6' #====Testing
            
        print 'execution time: ',  time.time()-time_now #====Testing
        wait_time(interval-(time.time()-time_now)) #sleep for the remaining time left in interval



#=====================================Supporting Functions, do not change ========================================================
def open_serial_port():
    global ser
    global ser_pressure
    ser.port = "/dev/lakeshore"
    ser.baudrate = 57600 
    ser.bytesize = serial.SEVENBITS
    ser.stopbits=serial.STOPBITS_ONE
    ser.parity=serial.PARITY_ODD
    ser.timeout=0
    ser.open()
    if ser.isOpen():
        print 'Serial port opened - T_control'
    else:
        print 'Unable to open serial port - T_control'
        
    ser_pressure.port = '/dev/pressure'
    ser_pressure.baudrate = 9600
    ser_pressure.timeout=0
    ser_pressure.open()
    time.sleep(5)
    if ser_pressure.isOpen():
        print 'Serial port opened - Pressure'
    else:
        print 'Unable to open serial port - Pressure'

def close_serial_port():
    global ser
    global ser_pressure
    ser.close()
    ser_pressure.close()
    print 'Serial port closed'

def readPressure():
    ser_pressure.write('@253PR4?;FF')
    time.sleep(0.5)
    result = ser_pressure.read(18)
    pressure = result[7:15]

    ser_pressure.flush()

    return pressure

def sendPacket(packetString): #send query message to T-controller and wait for response
    global ser
    ser.write(packetString)
    time.sleep(0.05)
    response = ser.read(10)
    time.sleep(0.05)
    return response
    
def sendCmdPacket(packetString): #send command message to T_controller and wait until operation is complete
    global ser
    ser.write(packetString)
    time.sleep(0.05)
    ser.write('*OPC\n') 
    time.sleep(0.05)
    
def temperature_check(str_array):
    inputA = float(str_array[2])
    inputB = float(str_array[3])
    if abs(inputA - inputB) > 3.0:
        print 'Warning: input A and B do not agree.'
        print 'Using input B as the reliable source.'
        str_array[2] = str_array[3]
    return str_array


def read_temperature():  #reads all 4 temperature sensors and 2 heaters, and 2 setpoints
    #//////// This section of codes reads the sensor inputs

    currentTime = time.time()

    returnedString = []
    returnedString.append(time.asctime())
    returnedString.append(time.time())
    for sensor in sensorList:
        queryString = 'KRDG? '+sensor +'\n'
        result = sendPacket(queryString).replace('\r\n', '')
        returnedString.append(result)


    for output in outputList:
        queryString = 'HTR? '+output +'\n'
        result = sendPacket(queryString).replace('\r\n', '')
        returnedString.append(result)

        
    for output in outputList:
        queryString = 'SETP? '+output +'\n'
        result = sendPacket(queryString).replace('\r\n', '')
        returnedString.append(result)

    pressure = readPressure()
    returnedString.append(pressure)
    
    current_temperatures = temperature_check(returnedString)#!!!!!!!!!!!!!!!!!!!!Temp code!!!!!!!!!!!!!!Take out once input A reliability issue is fixed!!!!!!!!!!!!!!!!!!!!!!!!
    #//////// End of sensor input reading    
    
    return returnedString


def set_controller_to_closedloop(): #set controller to closed loop mode to allow use of setpoints
    print 'Setting temperature controller to closed loop mode...'
    cmd_String_A = 'OUTMODE 1,1,1,0'+'\n'  #set to close loop
    cmd_String_B = 'OUTMODE 2,1,2,0'+'\n'
    sendCmdPacket(cmd_String_A)
    time.sleep(0.05)
    sendCmdPacket(cmd_String_B)
    time.sleep(0.05)
    
    cmd_String_A = 'RAMP 1,0,0'+'\n' #turn off ramping
    cmd_String_B = 'RAMP 2,0,0'+'\n'
    sendCmdPacket(cmd_String_A)
    time.sleep(0.05)
    sendCmdPacket(cmd_String_B)
    time.sleep(0.05)
    
    cmd_String_A = 'RANGE 1,0'+'\n' #enable heaters, need testing.
    cmd_String_B = 'RANGE 2,0'+'\n'
    sendCmdPacket(cmd_String_A)
    time.sleep(0.05)
    sendCmdPacket(cmd_String_B)
    time.sleep(0.05)
    
    cmd_String_A = 'PID 1,'+PID+'\n' #set PID parameters
    cmd_String_B = 'PID 2,'+PID+'\n'
    sendCmdPacket(cmd_String_A)
    time.sleep(0.05)
    sendCmdPacket(cmd_String_B)
    time.sleep(0.05)
    
    cmd_String_A = 'MOUT '+'1,'+ '0'+'\n'
    sendCmdPacket(cmd_String_A)
    time.sleep(0.05)
    cmd_String_B = 'MOUT '+'2,' + '0'+'\n'
    sendCmdPacket(cmd_String_B)
    time.sleep(0.05)
    

def write_html(sensor_readings):
    global image_generated
    
    returnedString = sensor_readings
    
    image_generated = generate_history_plot(returnedString)

    html_file = open('t_stream.html', 'w')
    html_file.write('<!DOCTYPE html>' + '\n')
    html_file.write('<head>' + '\n')
    html_file.write('<meta http-equiv="refresh" content="30">' + '\n')
    html_file.write('</head>' + '\n')
    html_file.write('<html>' + '\n')
    html_file.write('<body>' + '\n')
    html_file.write('<h1> Time: ' + returnedString[0] + '</h1>' + '\n')
    html_file.write('<h2> Cooling script running </h2>' + '\n')

    html_file.write('<table>' + '\n')
    html_file.write('<tr>' + '\n')
    html_file.write('<th> Temperatures </th>' + '\n')
    html_file.write('<th> Heaters </th>' + '\n')
    html_file.write('<th> Setpoints </th>' + '\n')
    html_file.write('</tr>' + '\n')
    html_file.write('<tr>' + '\n')
    html_file.write('<td>Input A (Detector): ' + returnedString[2] + '</td>' + '\n')
    html_file.write('<td>Output 1 (percent): ' + returnedString[7] + ' &nbsp;</td>' + '\n')
    html_file.write('<td>Setpoint 1: ' + returnedString[9] + '</td>' + '\n')
    html_file.write('</tr>' + '\n')
    html_file.write('<tr>' + '\n')
    html_file.write('<td>Input B (Detector): ' + returnedString[3] + '</td>' + '\n')
    html_file.write('<td>Output 2 (percent): ' + returnedString[8] + ' &nbsp;</td>' + '\n')
    html_file.write('<td>Setpoint 2: ' + returnedString[10] + '</td>' + '\n')
    html_file.write('</tr>' + '\n')
    html_file.write('<tr>' + '\n')
    html_file.write('<td>Input C (ASIC): ' + returnedString[4] + '</td>' + '\n')
    html_file.write('<td> </td>' + '\n')
    html_file.write('<td> </td>' + '\n')
    html_file.write('</tr>' + '\n')
    html_file.write('<tr>' + '\n')
    html_file.write('<td>Input D (Optics Plate): ' + returnedString[5] + '</td>' + '\n')
    html_file.write('<td> </td>' + '\n')
    html_file.write('<td>DT/dt: ' + str(g_dT_dt) + '</td>' + '\n')
    html_file.write('</tr>' + '\n')
    html_file.write('<td>Input E (Worksurface): ' + returnedString[6] + '</td>' + '\n')
    html_file.write('<td> </td>' + '\n')
    html_file.write('<td>DT/dt: ' + str(g_dT_dt) + '</td>' + '\n')
    html_file.write('</tr>' + '\n')
    html_file.write('</table>' + '\n')

    if returnedString[11] >= 1.0:
        html_file.write('<p>Pressure: ' + str(returnedString[11]) + ' Torr</p>')
    else:
        html_file.write('<p>Pressure: ' + str(returnedString[11] * 1000.) + ' mTorr</p>')
    if image_generated:
        html_file.write('<p> <img src="history_plot.jpg" width="300" height="225"  />')
        html_file.write('<img src="history_plot_heater.jpg" width="300" height="225"  />')
        html_file.write('<img src="history_plot_Tgrad.jpg" width="300" height="225"  />')
        html_file.write('<img src="pressure_plot.jpg" width="300" height="225"  />')
        html_file.write('</p>'+'\n')
    html_file.write('<p> Page will update every 30 seconds</p>'+'\n')

    html_file.write('</body>'+'\n')
    html_file.write('</html>'+'\n')

    html_file.close()


def upload_html_and_plots():
    try:
        ssh = paramiko.SSHClient() 
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        #ssh.load_host_keys(os.path.expanduser(os.path.join("~", ".ssh", "known_hosts")))
        #server = 'jiyoon.astro.utoronto.ca'
        server = 'thor.dunlap.utoronto.ca'
        ssh.connect(server, username='fool', password='')
        sftp = ssh.open_sftp()
        localpath = 't_stream.html'
        localpath_image = 'history_plot.jpg'
        localpath_image_2 = 'history_plot_heater.jpg'
        localpath_image_3 = 'history_plot_Tgrad.jpg'
        localpath_image_4 = 'pressure_plot.jpg'
        remotepath = '/Users/mark/Sites/t_stream.html'
        remotepath_img = '/Users/mark/Sites/history_plot.jpg'
        remotepath_img_2 = '/Users/mark/Sites/history_plot_heater.jpg'
        remotepath_img_3 = '/Users/mark/Sites/history_plot_Tgrad.jpg'
        remotepath_img_4 = '/Users/mark/Sites/pressure_plot.jpg'
        sftp.put(localpath, remotepath)
        if image_generated:
            sftp.put(localpath_image, remotepath_img)
            sftp.put(localpath_image_2, remotepath_img_2)
            sftp.put(localpath_image_3, remotepath_img_3)
            sftp.put(localpath_image_4, remotepath_img_4)
        sftp.close()
        ssh.close()
    except:
        print 'Unable to upload to webserver'

def generate_history_plot(new_data):
    # returns False when no image is produced, True when an image is generated
    global input_A_list
    global input_B_list
    global input_C_list
    global input_D_list
    global input_E_list
    global heater_1_list
    global heater_2_list
    global dT_dt_list
    global timestamp_list
    global pressure_list
    time_now = time.time()

    queue_length = len(timestamp_list)

    if queue_length < 2:
        input_A_list.append(float(new_data[2]))
        input_B_list.append(float(new_data[3]))
        input_C_list.append(float(new_data[4]))
        input_D_list.append(float(new_data[5]))
        input_E_list.append(float(new_data[6]))
        heater_1_list.append(float(new_data[7]))
        heater_2_list.append(float(new_data[8]))
        dT_dt_list.append(g_dT_dt)
        timestamp_list.append(float(new_data[1]))
        pressure_list.append(float(new_data[11]))
        return False

    else:
        oldest_time = timestamp_list[0]
        newest_time = timestamp_list[queue_length - 1]
        if newest_time - oldest_time > 3600.0:
            input_A_list.popleft()
            input_B_list.popleft()
            input_C_list.popleft()
            input_D_list.popleft()
            input_E_list.popleft()
            heater_1_list.popleft()
            heater_2_list.popleft()
            dT_dt_list.popleft()
            timestamp_list.popleft()
            pressure_list.popleft()
        input_A_list.append(float(new_data[2]))
        input_B_list.append(float(new_data[3]))
        input_C_list.append(float(new_data[4]))
        input_D_list.append(float(new_data[5]))
        input_E_list.append(float(new_data[6]))
        heater_1_list.append(float(new_data[7]))
        heater_2_list.append(float(new_data[8]))
        dT_dt_list.append(g_dT_dt)
        timestamp_list.append(float(new_data[1]))
        pressure_list.append(float(new_data[11]))

        plt.ylabel('Temperature (K)', fontsize=19)
        plt.xlabel('Time (Minutes)', fontsize=19)
        plt.title('Temperature History', fontsize=19)
        plt.grid(True)
        p1,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(input_A_list,copy=True),  'b.-')
        p2,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(input_B_list,copy=True),  'g.-')
        #p3,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(input_C_list,copy=True),  'r.-')
        p4,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(input_D_list,copy=True),  'c.-')
        p5,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(input_E_list,copy=True),  'm.-')
        #plt.legend(['Det1','Det2','ASIC','Optics','Worksurface'], loc=9)
        plt.legend(['Det1','Det2','Optics','Worksurface'], loc=9)
        plt.savefig('history_plot.png',  format='png')
        Image.open('history_plot.png').save('history_plot.jpg','JPEG')
        plt.clf() #clear figure
        plt.cla()
        plt.close()
        
        plt.ylabel('Heater Power (%)', fontsize=19)
        plt.xlabel('Time (Minutes)', fontsize=19)
        plt.title('Heater power History', fontsize=19)
        plt.ylim(-10.0,  100.0)
        plt.grid(True)
        p1,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(heater_1_list,copy=True),  'bs')
        p2,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(heater_2_list,copy=True),  'g^')
        plt.legend(['Heater 1', 'Heater 2'], loc=9)
        plt.savefig('history_plot_heater.png',  format='png')
        Image.open('history_plot_heater.png').save('history_plot_heater.jpg','JPEG')
        plt.clf() #clear figure
        plt.cla()
        plt.close()
        
        plt.ylabel('DT/dt of Detector(K/min)', fontsize=19)
        plt.xlabel('Time (Minutes)', fontsize=19)
        plt.title('Detector temperature gradient', fontsize=19)
        plt.ylim(-1.5,  1.5)
        plt.grid(True)
        p1,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(dT_dt_list,copy=True),  'ro')
        p2,  = plt.plot((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(dT_dt_list,copy=True)*0.0+cooling_gradient,  'b--')
        plt.savefig('history_plot_Tgrad.png',  format='png')
        Image.open('history_plot_Tgrad.png').save('history_plot_Tgrad.jpg','JPEG')
        plt.clf() #clear figure
        plt.cla()
        plt.close()
        
        plt.ylabel('Pressure (Torr)', fontsize=19)
        plt.xlabel('Time (Minutes)', fontsize=19)
        plt.title('Pressure History', fontsize=19)
        plt.grid(True)
        p1,  = plt.semilogy((numpy.array(timestamp_list,copy=True)-time_now)/60,  numpy.array(pressure_list,copy=True),  'bs')
        plt.savefig('pressure_plot.png',  format='png')
        Image.open('pressure_plot.png').save('pressure_plot.jpg','JPEG')
        plt.clf() #clear figure
        plt.cla()
        plt.close()
        
        return True
        
def record_readings_to_file(sensor_readings):
    global startTime
    global outData
    global f
    returnedString = sensor_readings
    currentTime = time.time()

    outData.writerow(returnedString)
    
def turn_off_heaters(): 
    cmd_String_A = 'RANGE 1,0'+'\n' #disable heaters
    cmd_String_B = 'RANGE 2,0'+'\n'
    sendCmdPacket(cmd_String_A)
    time.sleep(0.05)
    sendCmdPacket(cmd_String_B)
    time.sleep(0.05)

    
def turn_on_heaters(): 
    cmd_String_A = 'RANGE 1,0'+'\n' #turn heaters back to high
    cmd_String_B = 'RANGE 2,0'+'\n'
    sendCmdPacket(cmd_String_A)
    time.sleep(0.05)
    sendCmdPacket(cmd_String_B)
    time.sleep(0.05)

def wait_time(time_to_wait):
    time_now = time.time()
    while time.time() - time_now <= time_to_wait: #sleep until the time has elapsed
        time.sleep(0.1)

class doCooling:
    open_serial_port()
    set_controller_to_closedloop()

    try:
        cooling_setpoints()
        close_serial_port()
    except:
        close_serial_port()
        print 'exit'

