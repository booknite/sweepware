import subprocess
import xml.etree.ElementTree as ET
import time
import csv
import math
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
import json

# Global variables
stop_scanning = False
save_location = os.path.expanduser("~/Documents")
file_name = "sweep.csv"
settings = {
    "excluded_top_y": 500
}

def load_settings():
    global settings
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
    except FileNotFoundError:
        save_settings()

def save_settings():
    with open('settings.json', 'w') as f:
        json.dump(settings, f)

def change_excluded_top_y():
    global settings
    new_value = simpledialog.askinteger("Change Excluded Top Y (default 500)", 
                                        "Enter new value for excluded top Y:",
                                        initialvalue=settings['excluded_top_y'])
    if new_value is not None:
        settings['excluded_top_y'] = new_value
        save_settings()
        messagebox.showinfo("Settings Updated", f"Excluded top Y changed to: {new_value}")

def get_screen_size():
    result = subprocess.run(['adb', 'shell', 'wm', 'size'], capture_output=True, text=True)
    output = result.stdout.strip()
    print(f"Screen size output: {output}")  # Debug output
    if "size:" in output:
        size_str = output.split("size:")[-1].strip()
        width, height = map(int, size_str.split('x'))
        return width, height
    else:
        raise ValueError(f"Unexpected output from adb: {output}")

def dump_ui_hierarchy(file_name):
    with open('/dev/null', 'w') as devnull:
        subprocess.run(['adb', 'shell', 'uiautomator', 'dump', f'/sdcard/{file_name}'], stdout=devnull, stderr=devnull)
        subprocess.run(['adb', 'pull', f'/sdcard/{file_name}', '.'], stdout=devnull, stderr=devnull)

def extract_text_from_ui_xml(filename):
    tree = ET.parse(filename)
    root = tree.getroot()
    texts = []
    boxes = []
    for elem in root.iter():
        if 'bounds' in elem.attrib:
            bounds = elem.attrib['bounds']
            left, top, right, bottom = [int(coord) for part in bounds.strip('][').split('][') for coord in part.split(',')]
            if top < settings['excluded_top_y']:
                continue
            text = elem.attrib.get('text', '') or elem.attrib.get('content-desc', '')
            if text:
                texts.append(text)
                boxes.append((left, top, right, bottom))
    return texts, boxes

def scroll_down(duration_ms=500):
    with open('/dev/null', 'w') as devnull:
        subprocess.run(['adb', 'shell', 'input', 'swipe', '500', '1500', '500', '500', str(duration_ms)], stdout=devnull, stderr=devnull)

def ui_hierarchy_is_stable(file1, file2):
    with open(file1, 'r', encoding='utf-8') as f1, open(file2, 'r', encoding='utf-8') as f2:
        return f1.read() == f2.read()

def save_to_csv(texts, filename):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        for text in texts:
            writer.writerow([text])

def delete_ui_dump_files():
    for file in os.listdir("."):
        if file.startswith("ui_dump") and file.endswith(".xml"):
            os.remove(file)

def start_scraping():
    global stop_scanning
    stop_scanning = False
    start_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)
    threading.Thread(target=scrape_data, daemon=True).start()

def stop_scraping():
    global stop_scanning
    stop_scanning = True
    stop_button.config(state=tk.DISABLED)

def scrape_data():
    global stop_scanning
    all_texts = []
    try:
        screen_width, screen_height = get_screen_size()
    except ValueError as e:
        messagebox.showerror("Error", str(e))
        start_button.config(state=tk.NORMAL)
        stop_button.config(state=tk.DISABLED)
        return

    iteration = 0
    retries = 0
    max_retries = 3
    previous_texts = set()

    while not stop_scanning:
        iteration += 1

        dump_ui_hierarchy(f'ui_dump_{iteration}_1.xml')
        time.sleep(2)
        dump_ui_hierarchy(f'ui_dump_{iteration}_2.xml')

        while not ui_hierarchy_is_stable(f'ui_dump_{iteration}_1.xml', f'ui_dump_{iteration}_2.xml'):
            if stop_scanning:
                break
            time.sleep(1)
            dump_ui_hierarchy(f'ui_dump_{iteration}_1.xml')
            time.sleep(1)
            dump_ui_hierarchy(f'ui_dump_{iteration}_2.xml')

        if stop_scanning:
            break

        extracted_texts, boxes = extract_text_from_ui_xml(f'ui_dump_{iteration}_2.xml')

        current_texts = set(extracted_texts)
        if current_texts == previous_texts:
            retries += 1
            if retries >= max_retries:
                break
        else:
            retries = 0
            previous_texts = current_texts

        all_texts.extend(extracted_texts)

        scroll_down(duration_ms=1000)
        time.sleep(2)

        percentage = min(math.ceil((iteration / (iteration + max_retries)) * 100), 99)
        progress_var.set(percentage)
        root.update_idletasks()

    # Remove duplicate texts before saving
    all_texts = list(dict.fromkeys(all_texts))
    
    save_to_csv(all_texts, os.path.join(save_location, file_name))

    progress_var.set(100)
    root.update_idletasks()

    # Delete UI dump files
    delete_ui_dump_files()

    messagebox.showinfo("Info", f"Extraction complete. Data saved to {os.path.join(save_location, file_name)}")
    start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)

def check_dependencies():
    dependencies = ['python3', 'pip', 'adb']
    missing = []
    for dep in dependencies:
        try:
            subprocess.run([dep, '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            missing.append(dep)
    
    if missing:
        messagebox.showwarning("Missing Dependencies", f"The following dependencies are missing: {', '.join(missing)}")
    else:
        messagebox.showinfo("Dependencies", "All required dependencies are installed.")

def install_dependencies():
    messagebox.showinfo("Install Dependencies", "Please use your system's package manager to install the required dependencies: python3, pip, adb")

def change_save_location():
    global save_location
    new_location = filedialog.askdirectory(initialdir=save_location)
    if new_location:
        save_location = new_location
        messagebox.showinfo("Save Location", f"Save location changed to: {save_location}")

def rename_file():
    global file_name
    new_name = simpledialog.askstring("Rename File", "Enter new file name (including .csv extension):", initialvalue=file_name)
    if new_name:
        if new_name.endswith('.csv'):
            file_name = new_name
            messagebox.showinfo("File Renamed", f"File will be saved as: {file_name}")
        else:
            messagebox.showerror("Invalid Name", "File name must end with .csv")

def launch_scrcpy():
    try:
        subprocess.Popen(['scrcpy'])
    except FileNotFoundError:
        messagebox.showinfo("scrcpy not found", 
                            "scrcpy is not installed on your system. "
                            "You can download and install it from:\n"
                            "https://github.com/Genymobile/scrcpy\n\n"
                            "After installation, restart Sweepware to use this feature.")

def show_about():
    about_window = tk.Toplevel(root)
    about_window.title("About Sweepware")
    about_window.geometry("500x400")
    
    about_text = """
    Sweepware - Android App Content Scraper
    Sweepware is an open-source project created to simplify Android app
    content extraction for analysis and research purposes.
    
    How to use:
    1. Connect your Android device via USB and enable USB debugging.
    2. Open the app you want to scrape on your device.
    3. Click START to begin scraping.
    4. Click STOP to end the scraping process early.

    How it works:
    Sweepware uses ADB to interact with your Android device, capturing
    UI elements and text content.

    Troubleshooting:
    - Ensure USB debugging is enabled on your device.
    - Check that all dependencies are installed.
    - Restart your device and the Sweepware app if issues persist.

    About the creator:
    

    License: MIT License
    GitHub: https://github.com/booknite/sweepware
    """
    
    ttk.Label(about_window, text=about_text, wraplength=480, justify=tk.LEFT).pack(padx=10, pady=10)

# GUI Setup
root = tk.Tk()
root.title("Sweepware")
root.geometry("500x400")
root.configure(bg='#f0f0f0')

style = ttk.Style()
style.theme_use('clam')
style.configure('TButton', font=('Arial', 12), padding=10)
style.configure('TProgressbar', thickness=20)

# Menu
menu_bar = tk.Menu(root)
root.config(menu=menu_bar)

file_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="Check Dependencies", command=check_dependencies)
file_menu.add_command(label="Install Dependencies", command=install_dependencies)
file_menu.add_command(label="Change Save Location", command=change_save_location)
file_menu.add_command(label="Rename Output File", command=rename_file)
file_menu.add_command(label="Launch scrcpy", command=launch_scrcpy)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)

settings_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Settings", menu=settings_menu)
settings_menu.add_command(label="Exclude Fixed Navbar", command=change_excluded_top_y)

help_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Help", menu=help_menu)
help_menu.add_command(label="About", command=show_about)

frame = ttk.Frame(root, padding="20")
frame.pack(fill=tk.BOTH, expand=True)

# ASCII Logo
logo = """
 _____      _____  ___ _ ____      ____ _ _ __ ___ 
/ __\\ \\ /\\ / / _ \\/ _ \\ '_ \\ \\ /\\ / / _` | '__/ _ \\
\\__ \\\\ V  V /  __/  __/ |_) \\ V  V / (_| | | |  __/
|___/ \\_/\\_/ \\___|\\___| .__/ \\_/\\_/ \\__,_|_|  \\___|
                      |_|                          
"""

label = ttk.Label(frame, text=logo, font=("Courier", 10), justify=tk.CENTER)
label.pack(pady=10)

button_frame = ttk.Frame(frame)
button_frame.pack(pady=10)

start_button = ttk.Button(button_frame, text="START", command=start_scraping, width=10)
start_button.pack(side=tk.LEFT, padx=5)

stop_button = ttk.Button(button_frame, text="STOP", command=stop_scraping, state=tk.DISABLED, width=10)
stop_button.pack(side=tk.LEFT, padx=5)

progress_var = tk.DoubleVar()
progress_bar = ttk.Progressbar(frame, orient="horizontal", length=300, mode="determinate", variable=progress_var, style="Blue.Horizontal.TProgressbar")
progress_bar.pack(pady=10)

# Configure blue progress bar
style.configure("Blue.Horizontal.TProgressbar", background="royal blue")

# Load settings
load_settings()

root.mainloop()
