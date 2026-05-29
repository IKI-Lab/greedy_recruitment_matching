from tkinter import *
from tkinter import ttk
from tkinter import filedialog
import threading
import matching
 

class AppInterface:

    def __init__(self, root):
        root.title("Recruitment matching tool")
        self.content = ttk.Frame(root, padding=(3,3,12,12))
        self.content.grid(column=0, row=0, sticky=[N, W, E, S])

        self.control_frame = ttk.Frame(self.content)
        self.control_frame.grid(column=0, row=0, sticky=[N, W, E, S])
        self.text_frame = ttk.Frame(self.content)
        self.text_frame.grid(column=0, row=1, sticky=[N, W, E, S])

        # Loading Files
        self.enrolled_label = ttk.Label(self.control_frame, text="No file selected")
        self.enrolled_label.grid(column=1, row=0, sticky=[W, E])
        ttk.Button(self.control_frame, width=20, text="Load File: Enrolled",
                command=lambda: self.load_file(self.enrolled_label)).grid(column=0, row=0, sticky=[W])

        self.pool_label = ttk.Label(self.control_frame, text="No file selected")
        self.pool_label.grid(column=1, row=1, sticky=[W, E])
        ttk.Button(self.control_frame, width=20, text="Load File: Pool",
                command=lambda: self.load_file(self.pool_label)).grid(column=0, row=1, sticky=[W])

        # Settings
        self.settings_frame = ttk.Frame(self.control_frame)
        self.settings_frame.grid(column=0, columnspan=2, row=3, sticky=[W, E])
        self.w_age = StringVar(value="0.4")
        self.w_gender = StringVar(value="0.4")
        self.w_bmi = StringVar(value="0.2")
        self.n_patients = StringVar(value="100")
        self.n_controls = StringVar(value="100")
        self.recruit_method = StringVar(value="max")


        ttk.Label(self.settings_frame, text="Settings:").grid(column=0, row=0, sticky=W)
        # Recruitment number
        ttk.Label(self.settings_frame, text="N Patients:").grid(column=0, row=2, sticky=[W, E])
        ttk.Entry(self.settings_frame, textvariable=self.n_patients).grid(column=1, row=2, sticky=[W, E])
        ttk.Label(self.settings_frame, text="N Controls:").grid(column=2, row=2, sticky=[W, E])
        ttk.Entry(self.settings_frame, textvariable=self.n_controls).grid(column=3, row=2, sticky=[W, E])
        # How to recruit
        ttk.Radiobutton(self.settings_frame, text="New", variable=self.recruit_method, value="new").grid(column=4, row=2)
        ttk.Radiobutton(self.settings_frame, text="Max", variable=self.recruit_method, value="max").grid(column=5, row=2)


        self.run_button = ttk.Button(self.control_frame, text="Run", command=self.run_program)
        self.run_button.grid(column=1, row=5, sticky=E)
        self.save_button = ttk.Button(self.control_frame, text="Save", command=self.save_output)
        self.save_button.grid(column=2, row=5, sticky=W)

        # Text frame
        self.results = Text(self.text_frame)
        self.results.grid(column=0, row=0, sticky=[N, W, E, S])
        scrollbar = ttk.Scrollbar(self.text_frame, orient=VERTICAL, command=self.results.yview)
        scrollbar.grid(column=1, row=0, sticky=(N, S))
        self.results["yscrollcommand"] = scrollbar.set


        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(1, weight=1)
        # self.control_frame.columnconfigure(1, weight=1)
        self.text_frame.columnconfigure(0, weight=1)
        self.text_frame.rowconfigure(0, weight=1)


    def load_file(self, label):
        path = filedialog.askopenfilename()
        if path:
            label.config(text=path)


    def run_program(self):
        enrolled_path = self.enrolled_label.cget("text")
        pool_path = self.pool_label.cget("text")
        weights = [float(w.get()) for w in [self.w_age, self.w_gender, self.w_bmi]]
        n_patients = int(self.n_patients.get())
        n_controls = int(self.n_controls.get())
        

        if enrolled_path == "No file selected":
            self.results.insert(END, "Please select an enrolled file first.\n")
            return
        if pool_path == "No file selected":
            pool_path = None
        
        self.results.delete("1.0", END)
        self.run_button.config(state=DISABLED)
        def task():
            try:
                if self.recruit_method.get() == "max":
                    output = matching.run(
                        enrolled_path, pool_path, None, None, n_patients, n_controls, weights, silent=True
                    )
                elif self.recruit_method.get() == "new":
                    output = matching.run(
                        enrolled_path, pool_path, n_patients, n_controls, None, None, weights, silent=True
                    )
                else:
                    raise ValueError(f"Invalid value for self.recruit_method: {self.recruit_method.get()}")
                self.results.after(0, lambda: self.results.insert(END, output))
            except Exception as e:
                self.results.after(0, lambda err=e: self.results.insert(END, f"Error: {err}"))
            finally:
                self.results.after(0, lambda: self.run_button.config(state=NORMAL))
        self.results.insert(END, "Running...\n")
        threading.Thread(target=task, daemon=True).start()


    def save_output(self):
        content = self.results.get("1.0", END).strip()
        if not content:
            self.results.insert(END, "Nothing to save.\n")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
                self.results.insert(END, f"Saved to {path}\n")


def main():
    root = Tk()
    AppInterface(root)
    root.mainloop()


if __name__ == "__main__":
    main()