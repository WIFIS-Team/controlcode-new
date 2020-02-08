# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# Name:             WIFISmotor.py
# Purpose:          Motor control backend for WIFIS Control GUI
# Author:           R Elliot Meyer
#------------------------------------------------------------------------------

"""
This is a module that contains methods to control the WIFIS motors.
"""

# initialize a serial RTU client instance
from pymodbus.client.sync import ModbusSerialClient as ModbusClient  
import time
from PyQt5.QtCore import QObject, pyqtSignal, QThread
import traceback
from serial import SerialException
import logger
import os

class MotorControl(QObject):

    updateText = pyqtSignal(str, str, int)

    def __init__(self):
        super(MotorControl, self).__init__()

        homedir = os.path.split(os.path.realpath(__file__))[0]

        #Set up logger
        self.logger = logging.getLogger('motors')
        self.logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(homedir + '/log/motor.log')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        #Default values
        self.motor_speed1 = 10
        self.motor_speed2 = 500
        self.motor_speed3 = 10

        #Connect to the motor
        self.connectMotor()

    def connectMotor(self):
        try:
            print "Connecting to motors..."
            self.logger.info("Connecting to motor modbus serial client")

            self.client = ModbusClient(method="rtu", port="/dev/motor", stopbits=1, \
            bytesize=8, parity='E', baudrate=9600, timeout=0.1)
            self.motorclient.connect()

            self.logger.info("Connected to motor modbus serial client")

            self.motorson = True
        except Exception as e:
            print "Something went wrong connecting to the motors...."
            print e
            self.logger.exception("Something went wrong with motor connection")
            self.motorson = False

    def get_position(self):
        
        #Focus, Filter, Grating
        self.logger.info("Getting the positions of all motors")
        for i in range(3):
            unit = i + 1
            try:
                self.logger.info("Reading positon of motor %s", unit)
                temp = self.client.read_holding_registers(0x0118, 2, unit=unit)
                self.logger.info("Read position of motor %s", unit)
                #print "temp ", temp
                if temp != None:
                    self.motor_position = (temp.registers[0] << 16) + temp.registers[1]
                    self.logger.info("Position of motor %s is %s", self.motor_position)
                    if self.motor_position >= 2**31:
                        self.logger.debug("Motor position was above 32 bit signed limit")
                        self.motor_position -= 2**32
                    self.updateText.emit(str(self.motor_position), 'Position', i)
            #except Exception as e:
            #    print traceback.print_exc()
            #    print e
            #    print "EXCEPTION (UPDATE STATUS)"
            except SerialException:
                self.logger.exception("Serial exception during the acquisition of motor %s position", \
                        unit)
                print traceback.print_exc()
                print "Unit: ", unit
                print "Serial Exception (get_position)..."
            except:
                self.logger.exception("Exception during the acquisition of motor %s position", \
                        unit)

    def update_status(self):
        #Returns 1025 if moving, 43009 if home, 8193 if stopped and not home, 
        #32768 if not operating/communicating (?) 
        #Focus, Filter, Grating

        self.logger.info("Getting the status of all motors")
        try:
            for unit in range(1,4):
                self.logger.info("Getting the status motor %s", unit)
                resp = self.client.read_holding_registers(0x0020,1, unit=unit)
                self.logger.info("Received the status motor %s", unit)

                if resp != None:
                    bin_resp = '{0:016b}'.format(resp.registers[0])
                    if bin_resp[5] == '1' and bin_resp[2] == '0':
                        self.logger.debug("Motor %s is MOVING with response %s", \
                                unit, bin_resp)
                        self.updateText.emit("MOVING",'Status',unit-1)
                    elif bin_resp[4] == '1' and bin_resp[2] == '1':
                        self.updateText.emit("HOME",'Status',unit-1)
                        self.logger.debug("Motor %s is HOME with response %s", \
                                unit, bin_resp)
                    elif bin_resp[4] == '0' and bin_resp[2] == '1':
                        self.updateText.emit("READY",'Status',unit-1)
                        self.logger.debug("Motor %s is READY with response %s", \
                                unit, bin_resp)
                    elif bin_resp[0] == '1' and bin_resp[2] == '0':
                        self.updateText.emit("OFF/ERR",'Status',unit-1)
                        self.logger.debug("Motor %s is OFF/ERR with response %s", \
                                unit, bin_resp)
                    else:
                        self.updateText.emit("UNKN",'Status',unit-1)
                        self.logger.debug("Motor %s is UNKN with response %s", \
                                unit, bin_resp)

        except SerialException:
        #except Exception as e:
            print traceback.print_exc()
            #print "EXCEPTION (UPDATE STATUS)"
            print "Serial Exception (Update Status)..."
            self.logger.exception("Serial exception during the acquisition of the position of motor %s", \
                        unit)
        except:
            self.logger.exception("Exception during the acquisition of status of motor %s", \
                        unit)

    def stepping_operation(self, value, unit):

        self.logger.info("Initializing a step operation of %s for motor %s", step, unit)

        step = int(value)
        if step < 0:
            step += 2**32
        upper = step >> 16
        lower = step & 0xFFFF

        self.logger.info("Step of %s converted to upper: %s, and lower: %s", step, upper, lower)

        try:
            self.logger.info("Writing to register 0x001E")
            self.client.write_register(0x001E, 0x2000, unit=unit)
            self.logger.info("Writing to register 0x0402")
            self.client.write_registers(0x0402, [upper, lower], unit=unit)
            self.logger.info("Writing to register 0x001E")
            self.client.write_register(0x001E, 0x2101, unit=unit)
            self.logger.info("Writing to register 0x001E")
            self.client.write_register(0x001E, 0x2001, unit=unit)
        except SerialException:
            print traceback.print_exc()
            print "Value: ", value
            print "Unit: ", unit
            print "Serial Exception (stepping operation)..."
            self.logger.exception("Serial exception during a stepping operation for motor %s", \
                        unit)
        except:
            self.logger.exception("Exception during a stepping operation for motor %s", \
                        unit)

    def homing_operation(self, unit):
        
        #position_labels = [self.pos1,self.pos2,self.pos3]
        
        #if int(position_labels[unit-1]) % 1000 < 500:         
        #    units = [0x01,0x02,0x03]
            #Forces motor to reverse
        #    self.client.write_register(0x001E, 0x2000, unit=units[unit-1])
        #    self.client.write_register(0x001E, 0x2401, unit=units[unit-1])
        #    while (int(position_labels[unit-1]) % 1000 < 500) or (int(position_labels[unit-1]) % 1000 > 950):
                #Waits until the motor has gone past home
        #        position_labels = [self.pos1,self.pos2,self.pos3]
            #Stops the motor
        #    self.client.write_register(0x001E, 0x2001, unit=units[unit-1])
        
        #Homes the motor
        try:
            self.client.write_register(0x001E, 0x2000, unit=unit)
            self.client.write_register(0x001E, 0x2800, unit=unit)
            self.client.write_register(0x001E, 0x2000, unit=unit)
        except SerialException:
            print traceback.print_exc()
            print "Unit: ", unit
            print "Serial Exception (Homing Operation)..."

    #Actions
    def gotoTB(self):
        self.m2_step(action='20000')
        time.sleep(3)
        self.m3_step(action='-180')

    def gotoH(self):
        self.m2_step(action='40000')
        time.sleep(3)
        self.m3_step(action='360')

    def gotoBlank(self):
        self.m2_step(action='0')
    
    # Motor 1 methods
    def m1_speed(self):
        speed = int(self.motor_speed1)
        upper = speed >> 16
        lower = speed & 0xFFFF
        self.client.write_registers(0x0502, [upper, lower], unit=0x01)

    def m1_step(self):
        self.updateText.emit('','Step',0)

    def m1_home(self):
        self.updateText.emit("",'Home',0)

    #def m1_forward(self):
    #    self.client.write_register(0x001E, 0x2000, unit=0x01)
    #    self.client.write_register(0x001E, 0x2201, unit=0x01)

    #def m1_reverse(self):
    #    self.client.write_register(0x001E, 0x2000, unit=0x01)
    #    self.client.write_register(0x001E, 0x2401, unit=0x01)

    def m1_stop(self):
        self.client.write_register(0x001E, 0x2001, unit=0x01)

    def m1_off(self):
        self.client.write_register(0x001E, 0x0000, unit=0x01)

    # Motor 2 methods
    def m2_speed(self):
        speed = int(self.motor_speed2)
        upper = speed >> 16
        lower = speed & 0xFFFF
        self.client.write_registers(0x0502, [upper, lower], unit=0x02)

    def m2_step(self, action=False):
        if not action:
            self.updateText.emit('','Step', 1)
        elif action:
            self.updateText.emit(action,'Step', 1)

    def m2_home(self):
        self.updateText.emit("",'Home',1)

    #def m2_forward(self):
    #    self.client.write_register(0x001E, 0x2000, unit=0x02)
    #    self.client.write_register(0x001E, 0x2201, unit=0x02)

    #def m2_reverse(self):
    #    self.client.write_register(0x001E, 0x2000, unit=0x02)
    #    self.client.write_register(0x001E, 0x2401, unit=0x02)

    def m2_stop(self):
        self.client.write_register(0x001E, 0x2001, unit=0x02)

    def m2_off(self):
        self.client.write_register(0x001E, 0x0000, unit=0x02)

    # Motor 3 methods
    def m3_speed(self):
        speed = int(self.motor_speed3)
        upper = speed >> 16
        lower = speed & 0xFFFF
        self.client.write_registers(0x0502, [upper, lower], unit=0x03)

    def m3_step(self, action=False):
        if not action:
            self.updateText.emit('','Step',2)
        elif action:
            self.updateText.emit(action,'Step', 2)

    def m3_home(self):
        self.updateText.emit("",'Home',2)

    #def m3_forward(self):
    #    self.client.write_register(0x001E, 0x2000, unit=0x03)
    #    self.client.write_register(0x001E, 0x2201, unit=0x03)

    #def m3_reverse(self):
    #    self.client.write_register(0x001E, 0x2000, unit=0x03)
    #    self.client.write_register(0x001E, 0x2401, unit=0x03)

    def m3_stop(self):
        self.client.write_register(0x001E, 0x2001, unit=0x03)

    def m3_off(self):
        self.client.write_register(0x001E, 0x0000, unit=0x03)

class HandleMotors(QThread):

    updateText = pyqtSignal(list)

    def __init__(self, motorcontrol, motorlabels):
        QThread.__init__(self)

        self.motorcontrol = motorcontrol
        self.FocusPosition, self.FilterPosition, self.GratingPosition,\
                    self.FocusStatus, self.FilterStatus, self.GratingStatus,\
                    self.FocusStep, self.FilterStep, self.GratingStep= motorlabels
        self.stopthread = False
        self.isrunning = False
        self.action = False
        self.update = False

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopthread = True
        self.isrunning = False

    def movemotor1(self):
        self.action = True
        while self.update:
            pass
        self.motorcontrol.stepping_operation(self.FocusStep.text(), unit=0x01)
        self.sleep(1)
        self.action = False

    def movemotor2(self):
        self.action = True
        while self.update:
            pass
        self.motorcontrol.stepping_operation(self.FocusStep.text(), unit=0x01)
        self.sleep(1)
        self.action = False

    def movemotor3(self):
        self.action = True
        while self.update:
            pass
        self.motorcontrol.stepping_operation(self.FocusStep.text(), unit=0x01)
        self.sleep(1)
        self.action = False

    def run(self):

        while not self.stopthread:
            self.isrunning = True
            try:
                self.update = True

                if self.update and not self.action:
                    self.motorcontrol.update_status()
                    self.motorcontrol.get_position()
                
                self.update = False

                self.sleep(5)

            except Exception as e:
                print "############################"
                print "ERROR IN LABEL UPDATE THREAD"
                print traceback.print_exc()
                print e
                print "############################"
        self.isrunning = False


class MotorThread(QThread):

    updateText = pyqtSignal(str, str, int)

    def __init__(self, motorcontrol, unit, move_pos):
        QThread.__init__(self)

        self.motorcontrol = motorcontrol
        self.unit = unit
        self.move_pos = move_pos

    def __del__(self):
        self.wait()

    def stop(self):
        self.stopthread = True

    def run(self):

        try: 
        
            t1 = time.time()
            temp = self.motorcontrol.client.read_holding_registers(0x0118, 2, unit=self.unit+1)
            resp = self.motorcontrol.client.read_holding_registers(0x0020, 1, unit=self.unit+1)

            if temp != None:
                self.motor_position = (temp.registers[0] << 16) + temp.registers[1]
                if self.motor_position >= 2**31:
                    self.motor_position -= 2**32
            else:
                print "NO MOTOR_POSITION VARIABLE..."
                print "TEMP IS ", temp
                print "RESP IS", resp
                self.stop()

            self.motor_position = str(self.motor_position)

            while self.motor_position != self.move_pos:

                temp = self.motorcontrol.client.read_holding_registers(0x0118, 2, unit=self.unit+1)
                resp = self.motorcontrol.client.read_holding_registers(0x0020, 1, unit=self.unit+1)

                if temp != None:
                    self.motor_position = (temp.registers[0] << 16) + temp.registers[1]
                    if self.motor_position >= 2**31:
                        self.motor_position -= 2**32
                    self.updateText.emit(str(self.motor_position), 'Position', self.unit)
                    
                self.motor_position = str(self.motor_position)
                
                if resp != None:
                    bin_resp = '{0:016b}'.format(resp.registers[0])
                    if bin_resp[5] == '1' and bin_resp[2] == '0':
                        self.updateText.emit("MOVING",'Status',self.unit)
                    elif bin_resp[4] == '1' and bin_resp[2] == '1':
                        self.updateText.emit("HOME",'Status',self.unit)
                    elif bin_resp[4] == '0' and bin_resp[2] == '1':
                        self.updateText.emit("READY",'Status',self.unit)
                    elif bin_resp[0] == '1' and bin_resp[2] == '0':
                        self.updateText.emit("OFF/ERR",'Status',self.unit)
                    else:
                        self.updateText.emit("UNKN",'Status',self.unit)
                

                t2 = time.time()
                if (((t2 - t1) / 60.) >= 2.):
                    print "MOTOR UPDATE TIMEOUT"
                    break

                self.usleep(500000)

        except Exception as e:
            print "############################"
            print "ERROR IN MOTOR UPDATE THREAD"
            print traceback.print_exc()
            print e
            print "############################"

