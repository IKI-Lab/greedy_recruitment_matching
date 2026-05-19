
import tkinter as tk
from tkinter import filedialog
 
def load_file(label):
    path = filedialog.askopenfilename()
    if path:
        label.config(text=path)
 
root = tk.Tk()
root.title("File Loader")
root.geometry("800x400")
 
for filetype in ("Enrolled", "Pool"):
    frame = tk.Frame(root, pady=8)
    frame.pack(fill="x", padx=16)
 
    label = tk.Label(frame, text="No file selected", anchor="w", fg="gray")
 
    btn = tk.Button(frame, text=f"Load File: {filetype}",
                    command=lambda l=label: load_file(l))
    btn.pack(side="left")
    label.pack(side="left", padx=10)
 
root.mainloop()
 
