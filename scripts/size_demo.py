# -*- coding: utf-8 -*-
"""大小调节演示：1.2 秒后把宠物放大到 520px"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as m

root = tk.Tk()
pet = m.DesktopPet(root)
root.after(1200, lambda: pet.set_size(520))
root.after(6000, pet.quit)
root.mainloop()
print("demo done")
