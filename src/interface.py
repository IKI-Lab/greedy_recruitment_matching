from tkinter import *
from tkinter import ttk
from tkinter import filedialog
import threading
import matching
 
def load_file(label):
    path = filedialog.askopenfilename()
    if path:
        label.config(text=path)


def run_program():
    enrolled_path = enrolled_label.cget("text")
    pool_path = pool_label.cget("text")

    if enrolled_path == "No file selected":
        results.insert(END, "Please select an enrolled file first.\n")
        return
    if pool_path == "No file selected":
        pool_path = None
    
    results.delete("1.0", END)
    run_button.config(state=DISABLED)
    def task():
        try:
            output = matching.run(
                enrolled_path, pool_path, 50, 50, None, None, (0.4, 0.4, 0.2), silent=True
            )
            results.after(0, lambda: results.insert(END, output))
        except Exception as e:
            results.after(0, lambda err=e: results.insert(END, f"Error: {err}"))
        finally:
            results.after(0, lambda: run_button.config(state=NORMAL))
    results.insert(END, "Running...\n")
    threading.Thread(target=task, daemon=True).start()

root = Tk()
root.title("Recruitment matching tool")
content = ttk.Frame(root, padding=(3,3,12,12))
content.grid(column=0, row=0, sticky=[N, W, E, S])

enrolled_label = ttk.Label(content, text="No file selected")
enrolled_label.grid(column=1, row=0)
ttk.Button(content, text="Load File: Enrolled",
           command=lambda: load_file(enrolled_label)).grid(column=0, row=0, sticky=[W, E])

pool_label = ttk.Label(content, text="No file selected")
pool_label.grid(column=1, row=1)
ttk.Button(content, text="Load File: Pool",
           command=lambda: load_file(pool_label)).grid(column=0, row=1, sticky=[W, E])


run_button = ttk.Button(content, text="Run", command=run_program)
run_button.grid(column=1, row=2)

results = Text(content)
results.grid(column=0, columnspan=2, row=3)


root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
content.columnconfigure(1, weight=1)
root.mainloop()