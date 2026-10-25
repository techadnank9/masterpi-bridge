# Runs ON the robot (Pi 5 image): python3 /home/pi/hack/move_test_pi5.py
import sys, time
sys.path.append('/home/pi/MasterPi/')
import common.ros_robot_controller_sdk as rrc
from kinematics.arm_move_ik import ArmIK

board = rrc.Board()
AK = ArmIK()
AK.board = board
try:
    import common.mecanum as mecanum
    chassis = mecanum.MecanumChassis()
except Exception as e:
    print("mecanum import failed:", e)
    chassis = None

def stop():
    if chassis:
        chassis.set_velocity(0, 0, 0)
    board.set_motor_duty([[1, 0], [2, 0], [3, 0], [4, 0]])

try:
    board.pwm_servo_set_position(0.5, [[1, 1500]])
    print("arm home:", AK.setPitchRangeMoving((0, 6, 18), 0, -90, 90, 1500)); time.sleep(1.6)
    if chassis:
        chassis.set_velocity(40, 90, 0)
    else:
        board.set_motor_duty([[1, 40], [2, 40], [3, 40], [4, 40]])
    time.sleep(1.0)
finally:
    stop()
    print("stopped")
