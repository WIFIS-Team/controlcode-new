//this is the code that should be loaded onto the arduino controling the mirror flippers in the calibration unit

int flip1 = 12;
int flip2 = 13;
int incomingByte = 0;
int inPin = 7;   // flipper input connected to digital pin 7
int inPin2 = 8;   // flipper 2 input connected to digital pin 8
int val = 0;     // variable to store the read value
 
void setup() {
    pinMode(flip1, OUTPUT);
    pinMode(flip2, OUTPUT);
    pinMode(inPin, INPUT);      // sets the digital pin 7 as input
    pinMode(inPin2, INPUT);      // sets the digital pin 7 as input
     
    //Setup Serial Port with baud rate of 9600
    Serial.begin(9600);
    
}
 
void loop() {
    if (Serial.available() > 0) {
        // read the incoming byte:
        incomingByte = Serial.read();
     
        if(incomingByte == 'H'){
            digitalWrite(flip1, HIGH);
            
        }else if(incomingByte == 'L'){
            digitalWrite(flip1, LOW);
            
        }else if(incomingByte == 'M'){
            digitalWrite(flip2, LOW);
            
        }else if(incomingByte == 'N'){
            digitalWrite(flip2, HIGH);
            
        }else if(incomingByte == 'R'){
            val=digitalRead(inPin);
            Serial.println(val);
        }else if(incomingByte == 'V'){
            val=digitalRead(inPin2);
            Serial.println(val);
        }else{
            Serial.println("invalid!");
        }
       
    }
    
}
