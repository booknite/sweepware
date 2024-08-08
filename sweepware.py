import subprocess
import xml.etree.ElementTree as ET
import time
import csv
import math
import os
import json
import threading
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# Global variables
save_location = os.path.expanduser("~/Documents")
file_name = "sweep.csv"
settings = {
    "excluded_top_y": 500
}

class Worker(QThread):
    progress_update = pyqtSignal(int)
    log_message = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop_scanning = False
        self.first_scroll_log = True

    def run(self):
        self.scrape_data()

    def stop(self):
        self.stop_scanning = True

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_message.emit(f"{timestamp} - {message}")

    def get_screen_size(self):
        result = subprocess.run(['adb', 'shell', 'wm', 'size'], capture_output=True, text=True)
        output = result.stdout.strip()
        self.log(f"Screen size output: {output}")
        if "size:" in output:
            size_str = output.split("size:")[-1].strip()
            width, height = map(int, size_str.split('x'))
            return width, height
        else:
            raise ValueError(f"Unexpected output from adb: {output}\nConnect your android device and enable USB debugging.")

    def dump_ui_hierarchy(self, file_name):
        with open('/dev/null', 'w') as devnull:
            subprocess.run(['adb', 'shell', 'uiautomator', 'dump', f'/sdcard/{file_name}'], stdout=devnull, stderr=devnull)
            subprocess.run(['adb', 'pull', f'/sdcard/{file_name}', '.'], stdout=devnull, stderr=devnull)

    def extract_text_from_ui_xml(self, filename):
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

    def scroll_down(self, duration_ms=500):
        with open('/dev/null', 'w') as devnull:
            subprocess.run(['adb', 'shell', 'input', 'swipe', '500', '1500', '500', '500', str(duration_ms)], stdout=devnull, stderr=devnull)

    def ui_hierarchy_is_stable(self, file1, file2):
        with open(file1, 'r', encoding='utf-8') as f1, open(file2, 'r', encoding='utf-8') as f2:
            return f1.read() == f2.read()

    def save_to_csv(self, texts, filename):
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            for text in texts:
                writer.writerow([text])

    def delete_ui_dump_files(self):
        for file in os.listdir("."):
            if file.startswith("ui_dump") and file.endswith(".xml"):
                os.remove(file)

    def scrape_data(self):
        all_texts = []
        try:
            screen_width, screen_height = self.get_screen_size()
        except ValueError as e:
            self.error.emit(str(e))
            return

        iteration = 0
        retries = 0
        max_retries = 3
        previous_texts = set()

        while not self.stop_scanning:
            iteration += 1

            self.dump_ui_hierarchy(f'ui_dump_{iteration}_1.xml')
            time.sleep(2)
            self.dump_ui_hierarchy(f'ui_dump_{iteration}_2.xml')

            while not self.ui_hierarchy_is_stable(f'ui_dump_{iteration}_1.xml', f'ui_dump_{iteration}_2.xml'):
                if self.stop_scanning:
                    break
                time.sleep(1)
                self.dump_ui_hierarchy(f'ui_dump_{iteration}_1.xml')
                time.sleep(1)
                self.dump_ui_hierarchy(f'ui_dump_{iteration}_2.xml')

            if self.stop_scanning:
                break

            extracted_texts, boxes = self.extract_text_from_ui_xml(f'ui_dump_{iteration}_2.xml')

            current_texts = set(extracted_texts)
            if current_texts == previous_texts:
                retries += 1
                if retries >= max_retries:
                    break
            else:
                retries = 0
                previous_texts = current_texts

            all_texts.extend(extracted_texts)

            if self.first_scroll_log:
                self.log("Scrolling, please be patient.")
                self.first_scroll_log = False
            else:
                self.log("Sweeping...")

            self.scroll_down(duration_ms=1000)
            time.sleep(2)

            percentage = min(math.ceil((iteration / (iteration + max_retries)) * 100), 99)
            self.progress_update.emit(percentage)

            if percentage > 90:
                self.log("Almost finished.")

        # Remove duplicate texts before saving
        all_texts = list(dict.fromkeys(all_texts))
        self.save_to_csv(all_texts, os.path.join(save_location, file_name))

        self.progress_update.emit(100)
        self.delete_ui_dump_files()
        self.log("Complete.")
        self.finished.emit(f"Extraction complete. Data saved to {os.path.join(save_location, file_name)}")

# Function to load settings
def load_settings():
    global settings
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
    except FileNotFoundError:
        save_settings()

# Function to save settings
def save_settings():
    with open('settings.json', 'w') as f:
        json.dump(settings, f)

# Function to change excluded top Y setting
def change_excluded_top_y():
    global settings
    new_value, ok = QInputDialog.getInt(window, "Change Excluded Top Y (default 500)", 
                                        "Enter new value for excluded top Y:", 
                                        value=settings['excluded_top_y'])
    if ok:
        settings['excluded_top_y'] = new_value
        save_settings()
        QMessageBox.information(window, "Settings Updated", f"Excluded top Y changed to: {new_value}")

# Function to check dependencies
def check_dependencies():
    dependencies = ['python3', 'pip', 'adb']
    missing = []
    for dep in dependencies:
        try:
            subprocess.run([dep, '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            missing.append(dep)
    
    if missing:
        QMessageBox.warning(window, "Missing Dependencies", f"The following dependencies are missing: {', '.join(missing)}")
    else:
        QMessageBox.information(window, "Dependencies", "All required dependencies are installed.")

# Function to prompt user to install dependencies
def install_dependencies():
    QMessageBox.information(window, "Install Dependencies", "Please use your system's package manager to install the required dependencies: python3, pip, adb")

# Function to change save location
def change_save_location():
    global save_location
    new_location = QFileDialog.getExistingDirectory(window, "Select Save Location", save_location)
    if new_location:
        save_location = new_location
        QMessageBox.information(window, "Save Location", f"Save location changed to: {save_location}")

# Function to rename output file
def rename_file():
    global file_name
    new_name, ok = QInputDialog.getText(window, "Rename File", "Enter new file name (including .csv extension):", text=file_name)
    if ok:
        if new_name.endswith('.csv'):
            file_name = new_name
            QMessageBox.information(window, "File Renamed", f"File will be saved as: {file_name}")
        else:
            QMessageBox.critical(window, "Invalid Name", "File name must end with .csv")

# Function to launch scrcpy
def launch_scrcpy():
    try:
        subprocess.Popen(['scrcpy'])
    except FileNotFoundError:
        QMessageBox.information(window, "scrcpy not found", 
                            "scrcpy is not installed on your system. "
                            "You can download and install it from:\n"
                            "https://github.com/Genymobile/scrcpy\n\n"
                            "After installation, restart Sweepware to use this feature.")

# Function to show about dialog
def show_about():
    about_text = """
    Sweepware - Android Content Scraper
    
    Sweepware is an open-source project created to
    simplify Android app content extraction for
    analysis and research purposes.
    
    How to use:
    1. Connect your Android device via USB and
    enable USB debugging.
    2. Open the app you want to scrape on your
    device.
    3. Click START to begin scraping.
    4. Click STOP to end the scraping process early.

    How it works:
    This program uses ADB to interact with your
    Android device, capturing UI elements and text
    content.

    Troubleshooting:
    - Ensure USB debugging is enabled on your
    device.
    - Check that all dependencies are installed.
    - Restart your device and the Sweepware app if
    issues persist.

    About the creator:
    Jonathan Booker Nelson
    License: MIT License
    GitHub: https://github.com/booknite/sweepware
    """
    QMessageBox.information(window, "About Sweepware", about_text)

# GUI Setup
app = QApplication([])

window = QWidget()
window.setWindowTitle("Sweepware - Android Content Scraper")
window.setGeometry(100, 100, 500, 400)
layout = QVBoxLayout(window)

menu_bar = QMenuBar(window)
file_menu = menu_bar.addMenu("File")
file_menu.addAction("Check Dependencies", check_dependencies)
file_menu.addAction("Install Dependencies", install_dependencies)
file_menu.addAction("Change Save Location", change_save_location)
file_menu.addAction("Rename Output File", rename_file)
file_menu.addAction("Launch scrcpy", launch_scrcpy)
file_menu.addAction("Exit", app.quit)

settings_menu = menu_bar.addMenu("Settings")
settings_menu.addAction("Exclude Fixed Navbar", change_excluded_top_y)

help_menu = menu_bar.addMenu("Help")
help_menu.addAction("About", show_about)

layout.setMenuBar(menu_bar)

# Remove the logo and add a log section
log_label = QLabel("Sweepware Logs")
layout.addWidget(log_label)

log_output = QTextEdit()
log_output.setReadOnly(True)
layout.addWidget(log_output)

button_layout = QHBoxLayout()

start_button = QPushButton("START")
button_layout.addWidget(start_button)

stop_button = QPushButton("STOP")
stop_button.setEnabled(False)
button_layout.addWidget(stop_button)

layout.addLayout(button_layout)

progress_var = QProgressBar()
layout.addWidget(progress_var)

window.setLayout(layout)

# Load settings
load_settings()

# Worker thread
worker = Worker()

def start_scraping():
    worker.start()
    start_button.setEnabled(False)
    stop_button.setEnabled(True)

def stop_scraping():
    worker.stop()
    stop_button.setEnabled(False)

def handle_progress_update(value):
    progress_var.setValue(value)

def handle_log_message(message):
    log_output.append(message)

def handle_error(message):
    QMessageBox.critical(window, "Error", message)
    start_button.setEnabled(True)
    stop_button.setEnabled(False)

def handle_finished(message):
    QMessageBox.information(window, "Info", message)
    start_button.setEnabled(True)
    stop_button.setEnabled(False)

start_button.clicked.connect(start_scraping)
stop_button.clicked.connect(stop_scraping)

worker.progress_update.connect(handle_progress_update)
worker.log_message.connect(handle_log_message)
worker.error.connect(handle_error)
worker.finished.connect(handle_finished)

window.show()
app.exec_()

