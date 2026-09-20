"""Real desktop capture smoke test of a test window, without generated input."""
import ctypes
import tempfile
from pathlib import Path
import tkinter as tk
from PIL import ImageGrab, ImageTk
from companion.protocol import encode, render, decode_image, Assembler
from companion.app import App
from argparse import Namespace

def main():
    if hasattr(ctypes,'windll'):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    root=tk.Tk(); root.title('Bridge capture test'); root.geometry('+80+80')
    root.attributes('-topmost',True)
    frame=encode('Desktop capture test: café 🌏')[0]
    picture=ImageTk.PhotoImage(render(frame))
    label=tk.Label(root,image=picture,borderwidth=0,highlightthickness=0)
    label.pack(padx=24,pady=24); root.update()
    result=[]
    def check():
        try:
            x,y=label.winfo_rootx(),label.winfo_rooty()
            captured=ImageGrab.grab(bbox=(x,y,x+512,y+16),all_screens=True)
            result.append(Assembler().accept(decode_image(captured)))
        finally: root.destroy()
    root.after(500,check); root.mainloop()
    assert result and result[0][1]=='Desktop capture test: café 🌏', result
    with tempfile.TemporaryDirectory() as d:
        root=tk.Tk()
        args=Namespace(state=Path(d),backend='mock',project=Path.cwd(),sandbox='read-only',region=[8,8,512,16])
        app=App(root,args); root.update(); app.close()
    print('PASS: actual desktop capture/decode and companion UI startup/shutdown')

if __name__=='__main__': main()
