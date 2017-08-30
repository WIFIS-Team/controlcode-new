import serial
import time
import csv

# Open serial ports for Lakeshore temperature controller
# and MKS vacuum sensor
def open_serial_port(ser_temp,ser_pressure):
    # Open serial port for Lakeshore
    ser_temp.port = "/dev/ttyUSB2"
    ser_temp.baudrate = 57600 
    ser_temp.bytesize = serial.SEVENBITS
    ser_temp.stopbits=serial.STOPBITS_ONE
    ser_temp.parity=serial.PARITY_ODD
    ser_temp.timeout=0
    ser_temp.open()
    if ser_temp.isOpen():
        print 'Serial port opened - Lakeshore'
    else:
        print 'Unable to open serial port - Lakeshore'
    
    # Open serial port for MKS
    ser_pressure.port = '/dev/ttyUSB3'
    ser_pressure.baudrate = 9600
    ser_pressure.timeout=0
    ser_pressure.open()
    time.sleep(5)
    if ser_pressure.isOpen():
        print 'Serial port opened - MKS'
    else:
        print 'Unable to open serial port - MKS'

# Send read pressure command to MKS and return pressure
def read_pressure(ser_pressure):
    ser_pressure.write('@253PR4?;FF')
    time.sleep(1)
    result = ser_pressure.read(18)
    pressure = result[7:15]

    ser_pressure.flush()
    
    return pressure

# Function for sending command packet to Lakeshore controller
def sendPacket(ser_temp,packetString): #send query message to T-controller and wait for response
    ser_temp.write(packetString)
    time.sleep(0.05)
    response = ser_temp.read(10)
    time.sleep(0.05)
    return response

# Read five temperatures from the Lakeshore controller
# A - Detector #1
# B - Detector #2
# C - ASIC board temperature
# D1 - Optics plate temperature
# D2 - Cold plate temperature
def read_temperature(ser_temp):  
    currentTime = time.time()

    sensorList = ['A', 'B','C','D1','D2'] #name of inputs

    returnedString = []
    returnedString.append(time.asctime())
    returnedString.append(time.time())
    for sensor in sensorList:
        queryString = 'KRDG? '+sensor +'\n'
        result = sendPacket(ser_temp,queryString).replace('\r\n', '')
        returnedString.append(result)  
    
    return returnedString

# Main program, open serial ports
ser_temp = serial.Serial()
ser_pressure = serial.Serial()

open_serial_port(ser_temp,ser_pressure)

# Output filesname
fname = 'cooldown03182017-2.csv'
# File header
outFileHeader = ['#Time Stamp','seconds since epoch', 'Input A',  'Input B','Input C','Input D1', 'Input D2','Pressure']

f = open(fname, 'wb')
outData = csv.writer(f, dialect='excel')
outData.writerow(outFileHeader)

# Run data ACQ loop
while(True):
    outval = read_temperature(ser_temp)
    outval.append(read_pressure(ser_pressure))

    outData.writerow(outval)
    f.flush()
    print(outval)
    
f.close()    
