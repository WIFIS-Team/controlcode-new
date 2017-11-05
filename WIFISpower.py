#relies on dlipower.py, (from https://pypi.python.org/pypi/dlipower)  which is 
#uploaded here as well gui to control web power switches
#updates to show changes made from other places than this app but LAGS so no 
#pressing buttons a lot without being patient.

# Miranda Jarvis Oct 2015

from dlipower import PowerSwitch
from pylab import *
from Tkinter import *
from time import *
import ttk
from sys import exit

class PowerControl(): 
    #this class holds all of the gui into and button functions. 
    
    def __init__(self, power_widgets): #sets up gui stuff 
        print('Connecting to a DLI PowerSwitch at http://192.168.0.120 and '+\
            'another at http://192.168.0.110 ')  
        try:
            self.switch2 = PowerSwitch(hostname="192.168.0.120", userid="admin",\
                password='9876',timeout=5)
            self.switch1 = PowerSwitch(hostname="192.168.0.110", userid="admin",\
                password='9876',timeout=5)
        except Exception as e:
            print e
            print "ERROR IN CONNECTING TO POWER SUPPLIES"
            return

        self.Power11, self.Power12, self.Power13, self.Power14, self.Power15,\
            self.Power16, self.Power17, self.Power18, self.Power21, self.Power22,\
            self.Power23, self.Power24, self.Power25, self.Power26, self.Power27,\
            self.Power28 = power_widgets

        self.Power11.setText(self.switch1[0].description)
        self.Power12.setText(self.switch1[1].description)
        self.Power13.setText(self.switch1[2].description)
        self.Power14.setText(self.switch1[3].description)
        self.Power15.setText(self.switch1[4].description)
        self.Power16.setText(self.switch1[5].description)
        self.Power17.setText(self.switch1[6].description)
        self.Power18.setText(self.switch1[7].description)


        self.Power21.setText(self.switch2[0].description)
        self.Power22.setText(self.switch2[1].description)
        self.Power23.setText(self.switch2[2].description)
        self.Power24.setText(self.switch2[3].description)
        self.Power25.setText(self.switch2[4].description)
        self.Power26.setText(self.switch2[5].description)
        self.Power27.setText(self.switch2[6].description)
        self.Power28.setText(self.switch2[7].description)

        self.checkOn()

    def create_widgets(self): 
        
        if self.switch2:
            #label columns 
            Label(self, text="Outlet", font='bold').grid(row=0, column=0, \
                padx=15)
            Label(self, text="Hostname", font='bold').grid(row=0, column=1, \
                padx=15)
            Label(self, text="State", font='bold').grid(row=0, column=2, padx=15)
            Label(self, text="Toggle", font='bold').grid(row=0, column=3, padx=15)

            #outlet number
            Label(self, text="1").grid(row=1, column=0, padx=15)
            Label(self, text="2").grid(row=2, column=0, padx=15)
            Label(self, text="3").grid(row=3, column=0, padx=15)
            Label(self, text="4").grid(row=4, column=0, padx=15)
            Label(self, text="5").grid(row=5, column=0, padx=15)
            Label(self, text="6").grid(row=6, column=0, padx=15)
            Label(self, text="7").grid(row=7, column=0, padx=15)
            Label(self, text="8").grid(row=8, column=0, padx=15)
            #seperate power control 1 from two, should probalby label which is 
            #which but haven't for now.
            ttk.Separator(self,orient=HORIZONTAL).grid(row=9, columnspan=4, \
                sticky="ew")


            #gets description from power bars of which plug is which, to change 
            #this log on to their IP addresses in web browser (IP should be writtin
            #on bars and later in this code) 
            Label(self, text=self.switch2[0].description).grid(row=1, column=1, padx=15)
            Label(self, text=self.switch2[1].description).grid(row=2, column=1, padx=15)
            Label(self, text=self.switch2[2].description).grid(row=3, column=1, padx=15)
            Label(self, text=self.switch2[3].description).grid(row=4, column=1, padx=15)
            Label(self, text=self.switch2[4].description).grid(row=5, column=1, padx=15)
            Label(self, text=self.switch2[5].description).grid(row=6, column=1, padx=15)
            Label(self, text=self.switch2[6].description).grid(row=7, column=1, padx=15)
            Label(self, text=self.switch2[7].description).grid(row=8, column=1, padx=15)
            
            #look if each plug is currently on or off, print status to reflect this
            #look at each for on or off to get colour right 
            c=strs = ["" for x in range(8)]
            for i in arange(8):
                if self.switch2[i].state=='OFF': c[i]='red'
                else: c[i]='green'
            
            self.status1 = Label(self, text=self.switch2[0].state,fg=c[0])
            self.status1.grid(row=1, column=2)
            self.status2 = Label(self, text=self.switch2[1].state,fg=c[1])
            self.status2.grid(row=2, column=2)
            self.status3 = Label(self, text=self.switch2[2].state,fg=c[2])
            self.status3.grid(row=3, column=2)
            self.status4 = Label(self, text=self.switch2[3].state,fg=c[3])
            self.status4.grid(row=4, column=2)
            self.status5 = Label(self, text=self.switch2[4].state,fg=c[4])
            self.status5.grid(row=5, column=2)
            self.status6 = Label(self, text=self.switch2[5].state,fg=c[5])
            self.status6.grid(row=6, column=2)
            self.status7 = Label(self, text=self.switch2[6].state,fg=c[6])
            self.status7.grid(row=7, column=2)
            self.status8 = Label(self, text=self.switch2[7].state,fg=c[7])
            self.status8.grid(row=8, column=2)
            
            Button(self, text="On/Off", command=self.toggle_plug1, width=5).grid(\
                row=1, column=3)
            Button(self, text="On/Off", command=self.toggle_plug2, width=5).grid(\
                row=2, column=3)
            Button(self, text="On/Off", command=self.toggle_plug3, width=5).grid(\
                row=3, column=3)
            Button(self, text="On/Off", command=self.toggle_plug4, width=5).grid(\
                row=4, column=3)
            Button(self, text="On/Off", command=self.toggle_plug5, width=5).grid(\
                row=5, column=3)
            Button(self, text="On/Off", command=self.toggle_plug6, width=5).grid(\
                row=6, column=3)
            Button(self, text="On/Off", command=self.toggle_plug7, width=5).grid(\
                row=7, column=3)
            Button(self, text="On/Off", command=self.toggle_plug8, width=5).grid(
                row=8, column=3)
            
        if self.switch1:

            Label(self, text="1").grid(row=10, column=0, padx=15)
            Label(self, text="2").grid(row=11, column=0, padx=15)
            Label(self, text="3").grid(row=12, column=0, padx=15)
            Label(self, text="4").grid(row=13, column=0, padx=15)
            Label(self, text="5").grid(row=14, column=0, padx=15)
            Label(self, text="6").grid(row=15, column=0, padx=15)
            Label(self, text="7").grid(row=16, column=0, padx=15)
            Label(self, text="8").grid(row=17, column=0, padx=15)

            Label(self, text=self.switch1[0].description).grid(row=10, column=1, padx=15)
            Label(self, text=self.switch1[1].description).grid(row=11, column=1, padx=15)
            Label(self, text=self.switch1[2].description).grid(row=12, column=1, padx=15)
            Label(self, text=self.switch1[3].description).grid(row=13, column=1, padx=15)
            Label(self, text=self.switch1[4].description).grid(row=14, column=1, padx=15)
            Label(self, text=self.switch1[5].description).grid(row=15, column=1, padx=15)
            Label(self, text=self.switch1[6].description).grid(row=16, column=1, padx=15)
            Label(self, text=self.switch1[7].description).grid(row=17, column=1, padx=15)

            #For the second power bar
            c=strs = ["" for x in range(8)]         
            for i in arange(8):
                if self.switch1[i].state=='OFF': c[i]='red'
                else: c[i]='green'

            self.status9 = Label(self, text=self.switch1[0].state,fg=c[0])
            self.status9.grid(row=10, column=2)
            self.status10 = Label(self, text=self.switch1[1].state,fg=c[1])
            self.status10.grid(row=11, column=2)
            self.status11 = Label(self, text=self.switch1[2].state,fg=c[2])
            self.status11.grid(row=12, column=2)
            self.status12 = Label(self, text=self.switch1[3].state,fg=c[3])
            self.status12.grid(row=13, column=2)
            self.status13 = Label(self, text=self.switch1[4].state,fg=c[4])
            self.status13.grid(row=14, column=2)
            self.status14 = Label(self, text=self.switch1[5].state,fg=c[5])
            self.status14.grid(row=15, column=2)
            self.status15 = Label(self, text=self.switch1[6].state,fg=c[6])
            self.status15.grid(row=16, column=2)
            self.status16 = Label(self, text=self.switch1[7].state,fg=c[7])
            self.status16.grid(row=17, column=2)

            #make buttons to toggle on or off state, each has to have own function 
            #defined later
            

            Button(self, text="On/Off", command=self.toggle_plug9, width=5).grid(\
                row=10, column=3)
            Button(self, text="On/Off", command=self.toggle_plug10, width=5).grid(\
                row=11, column=3)
            Button(self, text="On/Off", command=self.toggle_plug11, width=5).grid(\
                row=12, column=3)
            Button(self, text="On/Off", command=self.toggle_plug12, width=5).grid(\
                row=13, column=3)
            Button(self, text="On/Off", command=self.toggle_plug13, width=5).grid(\
                row=14, column=3)
            Button(self, text="On/Off", command=self.toggle_plug14, width=5).grid(\
                row=15, column=3)
            Button(self, text="On/Off", command=self.toggle_plug15, width=5).grid(\
                row=16, column=3)
            Button(self, text="On/Off", command=self.toggle_plug16, width=5).grid(\
                row=17, column=3)


    def checkOn(self):

        if self.switch1[0].state == 'OFF':
            self.Power11.setStyleSheet('background-color: red')
        else:
            self.Power11.setStyleSheet('background-color: green')
        if self.switch1[1].state == 'OFF':
            self.Power12.setStyleSheet('background-color: red')
        else:
            self.Power12.setStyleSheet('background-color: green')
        if self.switch1[2].state == 'OFF':
            self.Power13.setStyleSheet('background-color: red')
        else:
            self.Power13.setStyleSheet('background-color: green')
        if self.switch1[3].state == 'OFF':
            self.Power14.setStyleSheet('background-color: red')
        else:
            self.Power14.setStyleSheet('background-color: green')
        if self.switch1[4].state == 'OFF':
            self.Power15.setStyleSheet('background-color: red')
        else:
            self.Power15.setStyleSheet('background-color: green')
        if self.switch1[5].state == 'OFF':
            self.Power16.setStyleSheet('background-color: red')
        else:
            self.Power16.setStyleSheet('background-color: green')
        if self.switch1[6].state == 'OFF':
            self.Power17.setStyleSheet('background-color: red')
        else:
            self.Power17.setStyleSheet('background-color: green')
        if self.switch1[7].state == 'OFF':
            self.Power18.setStyleSheet('background-color: red')
        else:
            self.Power18.setStyleSheet('background-color: green')

        if self.switch2[0].state == 'OFF':
            self.Power21.setStyleSheet('background-color: red')
        else:
            self.Power21.setStyleSheet('background-color: green')
        if self.switch2[1].state == 'OFF':
            self.Power22.setStyleSheet('background-color: red')
        else:
            self.Power22.setStyleSheet('background-color: green')
        if self.switch2[2].state == 'OFF':
            self.Power23.setStyleSheet('background-color: red')
        else:
            self.Power23.setStyleSheet('background-color: green')
        if self.switch2[3].state == 'OFF':
            self.Power24.setStyleSheet('background-color: red')
        else:
            self.Power24.setStyleSheet('background-color: green')
        if self.switch2[4].state == 'OFF':
            self.Power25.setStyleSheet('background-color: red')
        else:
            self.Power25.setStyleSheet('background-color: green')
        if self.switch2[5].state == 'OFF':
            self.Power26.setStyleSheet('background-color: red')
        else:
            self.Power26.setStyleSheet('background-color: green')
        if self.switch2[6].state == 'OFF':
            self.Power27.setStyleSheet('background-color: red')
        else:
            self.Power27.setStyleSheet('background-color: green')
        if self.switch2[7].state == 'OFF':
            self.Power28.setStyleSheet('background-color: red')
        else:
            self.Power28.setStyleSheet('background-color: green')

#These are the toggle plug buttons. each is the same turns the right plug 
#on or off and changes the status to reflect this change
    def toggle_plug1(self):
        n=0
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power21.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power21.setStyleSheet('background-color: green')

    def toggle_plug2(self):
        n=1
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power22.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power22.setStyleSheet('background-color: green')

    def toggle_plug3(self):
        n=2
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power23.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power23.setStyleSheet('background-color: green')

    def toggle_plug4(self):
        n=3
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power24.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power24.setStyleSheet('background-color: green')

    def toggle_plug5(self):
        n=4
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power25.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power25.setStyleSheet('background-color: green')

    def toggle_plug6(self):
        n=5
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power26.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power26.setStyleSheet('background-color: green')

    def toggle_plug7(self):
        n=6
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power27.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power27.setStyleSheet('background-color: green')

    def toggle_plug8(self):
        n=7
        status=self.switch2[n].state
        if status=='ON': 
            self.switch2[n].state='OFF'
            self.Power28.setStyleSheet('background-color: red')
        else: 
            self.switch2[n].state='ON'
            self.Power28.setStyleSheet('background-color: green')

    def toggle_plug9(self):
        n=0
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power11.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power11.setStyleSheet('background-color: green')

    def toggle_plug10(self):
        n=1
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power12.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power12.setStyleSheet('background-color: green')

    def toggle_plug11(self):
        n=2
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power13.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power13.setStyleSheet('background-color: green')

    def toggle_plug12(self):
        n=3
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power14.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power14.setStyleSheet('background-color: green')

    def toggle_plug13(self):
        n=4
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power15.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power15.setStyleSheet('background-color: green')

    def toggle_plug14(self):
        n=5
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power16.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power16.setStyleSheet('background-color: green')

    def toggle_plug15(self):
        n=6
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power17.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power17.setStyleSheet('background-color: green')

    def toggle_plug16(self):
        n=7
        status=self.switch1[n].state
        if status=='ON': 
            self.switch1[n].state='OFF'
            self.Power18.setStyleSheet('background-color: red')
        else: 
            self.switch1[n].state='ON'
            self.Power18.setStyleSheet('background-color: green')

def power_edit():

    #connect to power bars
    print('Connecting to a DLI PowerSwitch at http://192.168.0.120 and '+\
        'another at http://192.168.0.110 ')  
    switch2 = PowerSwitch(hostname="192.168.0.120", userid="admin",\
        password='9876',timeout=5)
    switch1 = PowerSwitch(hostname="192.168.0.110", userid="admin",\
        password='9876',timeout=5)
    
    if (not switch1.verify()) and (not switch2.verify()):
        print("The powerswitches are not connected. Please connect them before running this software.")
    if (not switch1.verify()):
        switch1 = None
    if (not switch2.verify()):
        switch2 = None

    return switch1, switch2

def connect_to_power():


    print('Connecting to a DLI PowerSwitch at http://192.168.0.120 and '+\
        'another at http://192.168.0.110 ')  
    switch2 = PowerSwitch(hostname="192.168.0.120", userid="admin",\
        password='9876',timeout=5)
    switch1 = PowerSwitch(hostname="192.168.0.110", userid="admin",\
        password='9876',timeout=5)
    
    return switch1, switch2

def run_power_gui(mainloop = False):

    #connect to power bars
    switch1, switch2 = connect_to_power()

    if (not switch1.verify()) and (not switch2.verify()):
        print("The powerswitches are not connected. Please connect them before running this software.")
        return None, None, None
    
    #switch2[2].state='ON'

    root = Tk() 
    root.title("Power Switch Control") #name gui

    app = MainApplication(root,switch1,switch2) #initialize gui 
    
    #tell it to start doing the update_labels function after a few seconds
    #app.after(5,app.update_labels)  

    return root,switch1,switch2

def run_power_gui_standalone():

    #connect to power bars
    switch1, switch2 = connect_to_power()

    if (not switch1.verify()) and (not switch2.verify()):
        print("The powerswitches are not connected. Please connect them before running this software.")
    if (not switch1.verify()):
        switch1 = None
    if (not switch2.verify()):
        switch2 = None

    root = Tk() #something about gui
    root.title("Power Switch Control") #name gui

    app = MainApplication(root,switch1,switch2) #initialize gui 

    #tell it to start doing the update_labels function after a few seconds
    #app.after(5,app.update_labels)  

    root.mainloop() #loop over gui until closed

if __name__ == '__main__':
    run_power_gui_standalone()
