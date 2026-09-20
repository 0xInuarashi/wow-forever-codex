"""Desktop reply banner; never creates a game frame or sends input to WoW."""
import tkinter as tk
import ctypes


class ReplyBanner:
    def __init__(self, root, open_reply):
        self.root, self.open_reply = root, open_reply
        self.window = None
        self.timer = None
        self.title = tk.StringVar(master=root)
        self.preview = tk.StringVar(master=root)

    def dismiss(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.window is not None:
            self.window.destroy()
            self.window = None

    def open(self):
        self.dismiss()
        self.open_reply()

    def show(self, state, reply):
        self.dismiss()
        self.title.set('Codex replied' if state == 'done' else 'Codex needs attention')
        summary=' '.join(reply.split()) or 'Open the companion to read the result.'
        self.preview.set(summary[:180]+('…' if len(summary)>180 else ''))
        window=tk.Toplevel(self.root)
        self.window=window
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg='#18212c',borderwidth=2,relief='solid')
        window.attributes('-topmost', True)
        width,height=390,175
        x=max(0,self.root.winfo_screenwidth()-width-24)
        y=max(0,self.root.winfo_screenheight()-height-64)
        window.geometry(f'{width}x{height}+{x}+{y}')
        tk.Label(window,textvariable=self.title,bg='#18212c',fg='#f3cb76',
                 font=('Segoe UI',12,'bold')).pack(anchor='w',padx=12,pady=(10,4))
        tk.Label(window,textvariable=self.preview,bg='#18212c',fg='white',
                 wraplength=360,justify='left',font=('Segoe UI',10)).pack(anchor='w',padx=12)
        buttons=tk.Frame(window,bg='#18212c')
        buttons.pack(side='bottom',fill='x',padx=12,pady=10)
        tk.Button(buttons,text='Read reply',command=self.open).pack(side='left')
        tk.Button(buttons,text='Dismiss',command=self.dismiss).pack(side='right')
        # Keep keyboard focus in the game. These are only our own desktop HWNDs.
        if hasattr(ctypes,'windll'):
            from ctypes import wintypes
            window.update_idletasks()
            user32=ctypes.windll.user32
            user32.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
            user32.GetAncestor.restype=wintypes.HWND
            user32.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
            user32.GetWindowLongPtrW.restype=ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
            user32.SetWindowLongPtrW.restype=ctypes.c_ssize_t
            hwnd=user32.GetAncestor(window.winfo_id(),2)
            style=user32.GetWindowLongPtrW(hwnd,-20)
            user32.SetWindowLongPtrW(hwnd,-20,style|0x08000000|0x00000080)
        window.deiconify()
        self.timer=self.root.after(15000,self.dismiss)
