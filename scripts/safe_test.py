#!/usr/bin/env python3
"""Safe chassis test — start, sleep 0.5s, auto-stop."""
import sys, time, os
sys.path.insert(0, os.path.expanduser("~/Rosmaster-App/rosmaster"))
from Rosmaster_Lib import Rosmaster

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/myserial"
cmd = int(sys.argv[2]) if len(sys.argv) > 2 else 1
spd = int(sys.argv[3]) if len(sys.argv) > 3 else 20
dur = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5

print(f"Testing {port}: cmd={cmd} speed={spd} duration={dur}s")
bot = Rosmaster(com=port, debug=True)
bot.create_receive_threading()
time.sleep(0.3)
bot.set_car_run(cmd, spd, adjust=False)
time.sleep(dur)
bot.set_car_run(7, 100, adjust=False)
print("STOP sent")
time.sleep(0.2)
