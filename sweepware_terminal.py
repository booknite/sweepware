import subprocess
import xml.etree.ElementTree as ET
import time
import csv
import math
import os
import signal
import sys

# Global flag to indicate if scanning should stop
stop_scanning = False

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

def extract_text_from_ui_xml(filename, excluded_top_y):
    tree = ET.parse(filename)
    root = tree.getroot()
    texts = []
    boxes = []

    for elem in root.iter():
        if 'bounds' in elem.attrib:
            bounds = elem.attrib['bounds']
            left, top, right, bottom = [int(coord) for part in bounds.strip('][').split('][') for coord in part.split(',')]
            if top < excluded_top_y:
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

def print_loading_bar(percentage):
    bar_length = 40
    block = int(round(bar_length * percentage / 100))
    text = f"\rLoading... [{'#' * block + '-' * (bar_length - block)}] {percentage}%"
    print(text, end='')

def delete_ui_dump_files():
    for file in os.listdir("."):
        if file.startswith("ui_dump") and file.endswith(".xml"):
            os.remove(file)

def signal_handler(sig, frame):
    global stop_scanning
    print("\nScan interrupted. Saving collected data...")
    stop_scanning = True

if __name__ == "__main__":
    # Register the signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    welcome_message = """
Welcome to Sweepware - Android Content Scraper!

This tool scrapes the text from an app using adb and saves it to a .csv file.

**Start SCRCPY on your desktop and navigate to the app you want to scrape.
**Adjust your phone's screen to the area where you want the scraping to begin.
**Please be patient and don't touch your phone while the script automatically scrolls to the bottom.
**If scrolling does not begin after 10 seconds, try closing and re-opening the app on your phone.

Press [ENTER] to start.
"""
    print(welcome_message)
    input()

    all_texts = []

    screen_width, screen_height = get_screen_size()

    excluded_top_y = 500

    iteration = 0
    retries = 0
    max_retries = 3

    print_loading_bar(0)

    previous_texts = set()

    while not stop_scanning:
        iteration += 1

        dump_ui_hierarchy(f'ui_dump_{iteration}_1.xml')
        time.sleep(2)
        dump_ui_hierarchy(f'ui_dump_{iteration}_2.xml')

        stable = False
        while not ui_hierarchy_is_stable(f'ui_dump_{iteration}_1.xml', f'ui_dump_{iteration}_2.xml'):
            if stop_scanning:
                break
            time.sleep(1)
            dump_ui_hierarchy(f'ui_dump_{iteration}_1.xml')
            time.sleep(1)
            dump_ui_hierarchy(f'ui_dump_{iteration}_2.xml')
            stable = True

        if stop_scanning:
            break

        extracted_texts, boxes = extract_text_from_ui_xml(f'ui_dump_{iteration}_2.xml', excluded_top_y)

        # Check if we have reached the bottom by comparing texts
        current_texts = set(extracted_texts)
        if current_texts == previous_texts:
            retries += 1
            if retries >= max_retries:
                break
        else:
            retries = 0
            previous_texts = current_texts

        if iteration == 1:
            top_boxes = [box for box in boxes if box[1] < excluded_top_y]
            if top_boxes:
                excluded_top_y = max(box[3] for box in top_boxes) + 1

        all_texts.extend(extracted_texts)

        scroll_down(duration_ms=1000)
        time.sleep(2)

        percentage = min(math.ceil((iteration / (iteration + max_retries)) * 100), 99)
        print_loading_bar(percentage)

    # Remove duplicate texts before saving
    all_texts = list(dict.fromkeys(all_texts))
    
    save_to_csv(all_texts, 'sweep.csv')

    print_loading_bar(100)
    print("\nExtraction complete.")

    # Delete UI dump files
    delete_ui_dump_files()

