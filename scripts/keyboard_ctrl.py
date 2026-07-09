#!/usr/bin/env python3
"""Keyboard remote control: W=forward S=back A=left D=right Space=stop Q=quit."""
import sys, os, tty, termios, select, time
sys.path.insert(0, os.path.expanduser("~/Rosmaster-App/rosmaster"))
from Rosmaster_Lib import Rosmaster

# config
PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/myserial"
SPEED = 30  # 0-100, keep low for safety

bot = Rosmaster(com=PORT, debug=False)
bot.create_receive_threading()
time.sleep(0.3)

print(f"Keyboard Control | port={PORT} speed={SPEED}")
print("  W=↑  S=↓  A=←  D=→  Space=Stop  Q=Quit")

def get_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        if select.select([sys.stdin], [], [], 0.1)[0]:
            return sys.stdin.read(1)
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

try:
    while True:
        k = get_key()
        if k is None:
            time.sleep(0.05)
            continue
        k = k.lower()
        if k == 'w':
            bot.set_car_run(1, SPEED, adjust=False)
            print("↑ 前进")
        elif k == 's':
            bot.set_car_run(2, SPEED, adjust=False)
            print("↓ 后退")
        elif k == 'a':
            bot.set_car_run(3, SPEED, adjust=False)
            print("← 左转")
        elif k == 'd':
            bot.set_car_run(4, SPEED, adjust=False)
            print("→ 右转")
        elif k == ' ':
            bot.set_car_run(7, 100, adjust=False)
            print("■ 停止")
        elif k == 'q':
            bot.set_car_run(7, 100, adjust=False)
            print("退出")
            break
except KeyboardInterrupt:
    pass
finally:
    bot.set_car_run(7, 100, adjust=False)
    print("已停止")
