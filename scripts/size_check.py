# -*- coding: utf-8 -*-
"""直接验证 set_size 放大到 520px"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as m

root = tk.Tk()
pet = m.DesktopPet(root)
root.update()
print("before:", pet._size, pet.win_w, pet.win_h, pet.images["idle"].width())
pet.set_size(520)
root.update()
print("after :", pet._size, pet.win_w, pet.win_h, pet.images["idle"].width(),
      "geom=", root.geometry())
pet.quit()
print("OK")
