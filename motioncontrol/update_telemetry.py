import wifis_guiding as WG
from time import sleep

telSock = WG.connect_to_telescope()

while True:
    try:
        telemDict = WG.get_telemetry(telSock)
        WG.write_telemetry(telemDict)
        sleep(10)
    except:
        print "SOMETHING WENT WRONG WITH THE TELEMETRY WRITING...CONTINUING..."
