#/bin/bash
#USB HUB AND NETWORK SWTICH NEED TO BE TURNED ON MANUALLY

echo "IF THE USB HUB AND NETWORK SWITCH ARENT ON, PLEASE DO SO MANUALLY NOW"
echo -n "CONTINUE? (Y/N): "
read cont

if [ "$cont" == "Y" ]; then
    python /home/utopea/WIFIS-Team/controlcode/motioncontrol/power_control.py &
    sleep 5
    python /home/utopea/WIFIS-Team/controlcode/motioncontrol/motor_controller.py &
    sleep 5
    python /home/utopea/WIFIS-Team/controlcode/motioncontrol/calibration_control_toplevel.py &
fi
