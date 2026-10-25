# Runs ON the robot: scp to /home/pi/hack/, then
#   ssh -t pi@HOST 'sudo python3 /home/pi/hack/move_test.py'
import sys, time
sys.path.append('/home/pi/MasterPi/')
import HiwonderSDK.Board as Board
import HiwonderSDK.mecanum as mecanum
from ArmIK.ArmMoveIK import ArmIK

chassis = mecanum.MecanumChassis()
AK = ArmIK()
try:
    print("battery mV:", Board.getBattery())
    Board.setPWMServoPulse(1, 1500, 500)
    AK.setPitchRangeMoving((0, 6, 18), 0, -90, 90, 1500); time.sleep(1.6)
    chassis.set_velocity(40, 90, 0); time.sleep(1.0)
finally:
    chassis.set_velocity(0, 0, 0)
    print("stopped")
