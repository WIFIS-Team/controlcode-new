# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# Name:     motor_controller.py
# Purpose:  Motor control interface for WIFIS
# Authors:  Jason Leung
# Date:     July 2015
#------------------------------------------------------------------------------
"""
This is a module used to control the motors for WIFIS
"""

# initialize a serial RTU client instance
from __future__ import print_function
from pymodbus.client.sync import ModbusSerialClient as ModbusClient  
import time

class MotorControl():

    def __init__(self, motor_modules):

        self.FocusStatus, self.FilterStatus, self.GratingStatus, self.FocusPosition,\
                self.FilterPosition, self.GratingPosition, self.FocusStep,\
                self.FilterStep, self.GratingStep = motor_modules
        self.motor_speed1 = 10
        self.motor_speed2 = 500
        self.motor_speed3 = 10

        self.client = ModbusClient(method="rtu", port="/dev/motor", stopbits=1, \
        bytesize=8, parity='E', baudrate=9600, timeout=0.1)
        print("Connecting to motors...")
        self.client.connect()


    def get_position(self):
        
        position_labels = [self.FocusPosition,self.FilterPosition,self.GratingPosition]

        for i in range(3):
            unit = i + 1
            temp = self.client.read_holding_registers(0x0118, 2, unit=unit)
            if temp != None:
                self.motor_position = (temp.registers[0] << 16) + temp.registers[1]
                if self.motor_position >= 2**31:
                    self.motor_position -= 2**32
                poslabel = position_labels[unit-1]
                poslabel.setText(str(self.motor_position))

    def update_status(self):
        #Returns 1025 if moving, 43009 if home, 8193 if stopped and not home, 
        #32768 if not operating/communicating (?) 
        statuses = [self.FocusStatus, self.FilterStatus, self.GratingStatus]
        for unit in range(1,4):
            resp = self.client.read_holding_registers(0x0020,1, unit=unit)
            if resp != None:
                bin_resp = '{0:016b}'.format(resp.registers[0])
                if bin_resp[5] == '1' and bin_resp[2] == '0':
                    statuses[unit-1].setText("MOVING")
                elif bin_resp[4] == '1' and bin_resp[2] == '1':
                    statuses[unit-1].setText("HOME")
                elif bin_resp[4] == '0' and bin_resp[2] == '1':
                    statuses[unit-1].setText("READY")
                elif bin_resp[0] == '1' and bin_resp[2] == '0':
                    statuses[unit-1].setText("OFF/ERR")
                else:
                    statuses[unit-1].setText("UNKN")

    def stepping_operation(self, value, unit):
        step = int(value)
        if step < 0:
            step += 2**32
        upper = step >> 16
        lower = step & 0xFFFF
        self.client.write_register(0x001E, 0x2000, unit=unit)
        self.client.write_registers(0x0402, [upper, lower], unit=unit)
        self.client.write_register(0x001E, 0x2101, unit=unit)
        self.client.write_register(0x001E, 0x2001, unit=unit)

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
        self.client.write_register(0x001E, 0x2000, unit=unit)
        self.client.write_register(0x001E, 0x2800, unit=unit)
        self.client.write_register(0x001E, 0x2000, unit=unit)

    #Actions
    def gotoTB(self):
        self.m2_step(action='20000')
        time.sleep(1)
        self.m3_step(action='-200')

    def gotoH(self):
        self.m2_step(action='40000')
        time.sleep(1)
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
        self.stepping_operation(self.FocusStep.text(), unit=0x01)

    def m1_home(self):
        self.homing_operation(0x01)

    def m1_forward(self):
        self.client.write_register(0x001E, 0x2000, unit=0x01)
        self.client.write_register(0x001E, 0x2201, unit=0x01)

    def m1_reverse(self):
        self.client.write_register(0x001E, 0x2000, unit=0x01)
        self.client.write_register(0x001E, 0x2401, unit=0x01)

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
            self.stepping_operation(self.FilterStep.text(), unit=0x02)
        elif action:
            self.stepping_operation(action, unit=0x02)

    def m2_home(self):
        self.homing_operation(0x02)

    def m2_forward(self):
        self.client.write_register(0x001E, 0x2000, unit=0x02)
        self.client.write_register(0x001E, 0x2201, unit=0x02)

    def m2_reverse(self):
        self.client.write_register(0x001E, 0x2000, unit=0x02)
        self.client.write_register(0x001E, 0x2401, unit=0x02)

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
            self.stepping_operation(self.GratingStep.text(), unit=0x03)
        elif action:
            self.stepping_operation(action, unit=0x03)

    def m3_home(self):
        self.homing_operation(0x03)

    def m3_forward(self):
        self.client.write_register(0x001E, 0x2000, unit=0x03)
        self.client.write_register(0x001E, 0x2201, unit=0x03)

    def m3_reverse(self):
        self.client.write_register(0x001E, 0x2000, unit=0x03)
        self.client.write_register(0x001E, 0x2401, unit=0x03)

    def m3_stop(self):
        self.client.write_register(0x001E, 0x2001, unit=0x03)

    def m3_off(self):
        self.client.write_register(0x001E, 0x0000, unit=0x03)

