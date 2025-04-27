import os
import time
import random
import subprocess
import json
import requests
import openai
import undetected_chromedriver as uc
import platform

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager
from fake_useragent import UserAgent
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    ElementNotInteractableException
)

#################################
# 0) ANSWER BANK CLASS
#################################
class AnswerBank:
    def __init__(self, filepath="answer_bank.json"):
        self.filepath = filepath
        self.data = {}
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.data = json.load(f)
            except json.JSONDecodeError:
                self.data = {}

    def _make_key(self, question_text, question_type):
        return f"{question_type.lower()}::{question_text.strip().lower()}"

    def get_answer(self, question_text, question_type):
        key = self._make_key(question_text, question_type)
        return self.data.get(key)

    def add_answer(self, question_text, question_type, answer):
        key = self._make_key(question_text, question_type)
        self.data[key] = answer
        self._save()

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=4)

answer_bank = AnswerBank()

def get_answer_cached(question_text, question_type, options=None):
    existing = answer_bank.get_answer(question_text, question_type)
    if existing:
        print(f"[DEBUG] Using cached answer for '{question_type}' question: {question_text}")
        return existing
    ans = get_telegram_answer(question_text, options)
    answer_bank.add_answer(question_text, question_type, ans)
    return ans

#################################
# 1) ENV & TELEGRAM SETUP
#################################
from dotenv import load_dotenv
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINKEDIN_LI_AT = os.getenv("LINKEDIN_LI_AT")
LINKEDIN_JSESSIONID = os.getenv("LINKEDIN_JSESSIONID")

openai.api_key = OPENAI_API_KEY

TELEGRAM_SEND_MESSAGE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
TELEGRAM_GET_UPDATES_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

LAST_UPDATE_ID = 0

def drain_old_updates():
    global LAST_UPDATE_ID
    while True:
        try:
            resp = requests.get(TELEGRAM_GET_UPDATES_URL, params={"offset": LAST_UPDATE_ID + 1, "timeout": 2})
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", [])
            if not results:
                break
            for upd in results:
                upd_id = upd["update_id"]
                if upd_id > LAST_UPDATE_ID:
                    LAST_UPDATE_ID = upd_id
        except Exception as e:
            print("[ERROR] drain_old_updates =>", e)
            break
    print("[INFO] Drained old updates. LAST_UPDATE_ID =>", LAST_UPDATE_ID)

def send_telegram_message(msg, options=None):
    drain_old_updates()
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    if options:
        kb = [[{"text": opt}] for opt in options]
        data["reply_markup"] = json.dumps({
            "keyboard": kb,
            "one_time_keyboard": True,
            "resize_keyboard": True
        })
    try:
        r = requests.post(TELEGRAM_SEND_MESSAGE_URL, json=data)
        r.raise_for_status()
        print("[DEBUG] Sent Telegram:", msg)
        return wait_for_telegram_reply()
    except Exception as e:
        print("[ERROR] send_telegram_message =>", e)
        return "default"

def wait_for_telegram_reply():
    global LAST_UPDATE_ID
    timeout = 36000  # 10 hours
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            r = requests.get(TELEGRAM_GET_UPDATES_URL, params={"offset": LAST_UPDATE_ID + 1})
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                for upd in data.get("result", []):
                    upd_id = upd["update_id"]
                    if upd_id > LAST_UPDATE_ID:
                        LAST_UPDATE_ID = upd_id
                        msg = upd.get("message", {})
                        if msg.get("chat", {}).get("id") == int(TELEGRAM_CHAT_ID) and "text" in msg:
                            reply = msg["text"]
                            print("[DEBUG] Received Telegram reply:", reply)
                            return reply
            time.sleep(2)
        except Exception as e:
            print("[ERROR] wait_for_telegram_reply =>", e)
            break
    print("[WARN] No reply after 10 hours => using 'default'")
    return "default"

def get_telegram_answer(question, options=None):
    ans = "default"
    while ans.lower() == "default":
        ans = send_telegram_message(question, options)
        if ans.lower() == "default":
            print("[WARN] No valid Telegram answer => retrying in 5 seconds...")
            time.sleep(5)
    return ans

#################################
# 2) SELENIUM SETUP (MAC COMPAT)
#################################
def get_chrome_version():
    try:
        if platform.system() == "Darwin":
            cmd = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"]
        else:
            cmd = ["google-chrome", "--version"]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        v = r.stdout.strip().split()[-1]
        print(f"[INFO] Detected Chrome version: {v}")
        return v
    except Exception as e:
        print("[ERROR] get_chrome_version =>", e)
        return None

chrome_version = get_chrome_version() or "latest"
service = Service(ChromeDriverManager(driver_version=chrome_version).install())

try:
    ua = UserAgent().random
except Exception:
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

opts = Options()
if platform.system() == "Darwin":
    opts.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
opts.add_argument(f"user-agent={ua}")
opts.add_argument("--disable-blink-features=AutomationControlled")
opts.add_argument("--start-maximized")
opts.add_argument("--disable-extensions")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")

driver = uc.Chrome(service=service, options=opts)
stealth(
    driver,
    languages=["en-US", "en"],
    vendor="Google Inc.",
    platform="Win32",
    webgl_vendor="Intel Inc.",
    renderer="Intel Iris OpenGL Engine",
    fix_hairline=True
)
wait = WebDriverWait(driver, 15)

#################################
# 3) UTILITY FUNCTIONS
#################################
def safe_click(elem):
    driver.execute_script("arguments[0].scrollIntoView(true);", elem)
    time.sleep(1)
    try:
        elem.click()
    except ElementClickInterceptedException:
        print("[WARN] Normal click intercepted => using JS fallback.")
        driver.execute_script("arguments[0].click();", elem)

def safe_send_keys(el, text, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", el)
            time.sleep(1)
            el.clear()
            el.send_keys(text)
            return
        except ElementNotInteractableException as e:
            print(f"[WARN] Element not interactable (attempt {attempt+1}/{max_attempts}): {e}")
            time.sleep(2)
    print("[ERROR] Could not send keys => fallback to JS.")
    driver.execute_script("arguments[0].value = arguments[1];", el, text)

def get_form_state(main_container):
    st = []
    try:
        items = main_container.find_elements(
            By.XPATH,
            ".//div[@data-test-form-element or contains(@class,'jobs-easy-apply-form-element') or contains(@class,'artdeco-form-element')]"
        )
        for i in items:
            t = i.text.strip()
            if t:
                st.append(t)
    except Exception as e:
        print("[ERROR] get_form_state =>", e)
    return tuple(st)

#################################
# 4) LOGIN & CAPTCHA
#################################
def load_cookies():
    print("[INFO] Using cookies from .env to log in.")
    driver.get("https://www.linkedin.com")
    driver.delete_all_cookies()
    if LINKEDIN_LI_AT:
        print(f"[DEBUG] Setting li_at: {LINKEDIN_LI_AT}")
        driver.add_cookie({
            "name": "li_at",
            "value": LINKEDIN_LI_AT,
            "domain": ".linkedin.com",
            "path": "/",
            "secure": True
        })
        print("[DEBUG] Set li_at cookie.")
    else:
        print("[WARN] LINKEDIN_LI_AT not set in .env")
    if LINKEDIN_JSESSIONID:
        print(f"[DEBUG] Setting JSESSIONID: {LINKEDIN_JSESSIONID}")
        driver.add_cookie({
            "name": "JSESSIONID",
            "value": LINKEDIN_JSESSIONID,
            "domain": ".linkedin.com",
            "path": "/",
            "secure": True
        })
        print("[DEBUG] Set JSESSIONID cookie.")
    else:
        print("[WARN] LINKEDIN_JSESSIONID not set in .env")
    for i in range(5):
        driver.refresh()
        time.sleep(random.uniform(1,3))
        try:
            driver.find_element(By.XPATH, "//a[contains(@href,'feed')]")
            print("[INFO] Logged in with cookies, attempt", i+1)
            return
        except:
            pass
    print("[ERROR] Could not log in with cookies after attempts.")
    driver.quit()
    exit()

def handle_captcha():
    try:
        v = driver.find_element(By.ID, "home_children_button")
        print("[INFO] CAPTCHA detected => verifying.")
        safe_click(v)
        time.sleep(1.5)
    except:
        print("[INFO] No CAPTCHA detected.")

#################################
# 5) FORM-FILLING
#################################
def is_resume_step(main_container):
    txt = main_container.text.lower()
    if any(k in txt for k in ["docx", "pdf", "updated resume", "upload resume"]):
        return True
    return False

def fill_question_form(main_container):
    if is_resume_step(main_container):
        print("[INFO] Resume step detected => pressing Next.")
        next_btns = main_container.find_elements(By.XPATH, ".//button[@data-easy-apply-next-button]")
        if next_btns:
            safe_click(next_btns[0])
            time.sleep(2)
        return
    fill_text_fields(main_container)
    fill_dropdowns(main_container)
    fill_radio_buttons(main_container)

def fill_text_fields(main_container):
    skip_keywords = [
        "search by title, skill, or company",
        "city, state, or zip code"
    ]
    text_fields = main_container.find_elements(By.XPATH, ".//input[@type='text']")
    for field in text_fields:
        val = field.get_attribute("value") or ""
        if val.strip():
            print("[DEBUG] Text field already filled =>", val)
            continue
        question_text = extract_text_input_label(field)
        print("[DEBUG] TEXT question =>", question_text)
        if any(sk.lower() in question_text.lower() for sk in skip_keywords):
            print("[DEBUG] Skipping text field =>", question_text)
            continue
        if "experience" in question_text.lower():
            safe_send_keys(field, "5")
            print("[DEBUG] Auto-filled experience field with 5.")
        elif "salary" in question_text.lower():
            safe_send_keys(field, "80000")
            print("[DEBUG] Auto-filled salary field with 80000.")
        else:
            ans = get_answer_cached(question_text, "text")
            safe_send_keys(field, ans)
            print("[DEBUG] Filled text field:", question_text, "with", ans)
        time.sleep(random.uniform(1,3))

def extract_text_input_label(field):
    from selenium.common.exceptions import NoSuchElementException
    try:
        container = field.find_element(
            By.XPATH,
            "./ancestor::div[@data-test-form-element or contains(@class,'jobs-easy-apply-form-element') or contains(@class,'artdeco-form-element')]"
        )
    except NoSuchElementException:
        return "Open ended question"
    try:
        label_el = container.find_element(By.XPATH, ".//label[contains(@class,'artdeco-text-input__label')]")
        label_text = label_el.text.strip()
        if label_text:
            return label_text
    except NoSuchElementException:
        pass
    hidden_spans = container.find_elements(By.CSS_SELECTOR, "span.visually-hidden")
    combined_spans = [sp.text.strip() for sp in hidden_spans if sp.text.strip()]
    if combined_spans:
        return " ".join(combined_spans).strip()
    cont_text = container.text.strip()
    return cont_text if cont_text else "Open ended question"

def fill_dropdowns(main_container):
    containers = main_container.find_elements(
        By.XPATH,
        ".//div[@data-test-form-element or contains(@class,'jobs-easy-apply-form-element') or contains(@class,'artdeco-form-element')]"
    )
    for container in containers:
        selects = container.find_elements(By.XPATH, ".//select")
        if not selects:
            continue
        hidden_spans = container.find_elements(By.CSS_SELECTOR, "span.visually-hidden")
        question_text = ""
        if hidden_spans:
            combined = [sp.text.strip() for sp in hidden_spans if sp.text.strip()]
            question_text = " ".join(combined).strip()
        if not question_text:
            question_text = container.text.strip()
        for dd in selects:
            current_val = dd.get_attribute("value") or ""
            if current_val.strip() and current_val.lower() not in ["select an option", ""]:
                print(f"[DEBUG] Dropdown already selected => {current_val}")
                continue
            sel = Select(dd)
            options = [o.text.strip() for o in sel.options if o.text.strip()]
            if not options:
                print("[WARN] No valid options in this dropdown => skipping.")
                continue
            q_lines = question_text.split("\n")
            cleaned_lines = [line.strip() for line in q_lines if line.strip() not in options]
            final_question_text = "\n".join(cleaned_lines).strip()
            if not final_question_text:
                final_question_text = question_text
            print(f"[DEBUG] final_question_text => {final_question_text}")
            print(f"[DEBUG] dropdown options => {options}")
            ans = get_answer_cached(final_question_text, "dropdown", options)
            matched = False
            if ans.isdigit():
                idx = int(ans) - 1
                if 0 <= idx < len(options):
                    sel.select_by_visible_text(options[idx])
                    matched = True
                    print(f"[DEBUG] Digit-based selection => {options[idx]}")
            else:
                for opt in options:
                    if ans.lower() == opt.lower():
                        sel.select_by_visible_text(opt)
                        matched = True
                        print(f"[DEBUG] Matched text => {opt}")
                        break
            if not matched:
                if len(options) > 1:
                    sel.select_by_index(1)
                    print(f"[DEBUG] Defaulted to => {options[1]}")
                else:
                    sel.select_by_index(0)
                    print(f"[DEBUG] Only one option => {options[0]}")
            time.sleep(random.uniform(1,3))

def fill_radio_buttons(main_container):
    fieldsets = main_container.find_elements(By.XPATH, ".//fieldset[.//input[@type='radio']]")
    for fs in fieldsets:
        radio_inputs = fs.find_elements(By.XPATH, ".//input[@type='radio']")
        if any(r.is_selected() for r in radio_inputs):
            print("[DEBUG] Radio group already answered => skipping.")
            continue
        container = fs
        try:
            container = fs.find_element(
                By.XPATH,
                "./ancestor::div[@data-test-form-element or contains(@class,'jobs-easy-apply-form-element') or contains(@class,'artdeco-form-element')]"
            )
        except NoSuchElementException:
            pass
        hidden_spans = container.find_elements(By.CSS_SELECTOR, "span.visually-hidden")
        question_text = ""
        if hidden_spans:
            combined = [sp.text.strip() for sp in hidden_spans if sp.text.strip()]
            question_text = " ".join(combined).strip()
        if not question_text:
            question_text = container.text.strip()
        radio_inputs = fs.find_elements(By.XPATH, ".//input[@type='radio']")
        radio_labels = []
        for r in radio_inputs:
            r_label = (r.get_attribute("aria-label") or r.get_attribute("value") or "").strip()
            if not r_label:
                rid = r.get_attribute("id") or ""
                if rid:
                    try:
                        label_for = fs.find_element(By.XPATH, f".//label[@for='{rid}']")
                        r_label = label_for.text.strip()
                    except NoSuchElementException:
                        pass
            if not r_label:
                r_label = "Option"
            radio_labels.append(r_label)
        if not radio_labels:
            print("[WARN] No radio labels found => skipping fieldset.")
            continue
        q_lines = question_text.split("\n")
        cleaned_lines = [line.strip() for line in q_lines if not any(line.strip().lower() == rl.lower() for rl in radio_labels)]
        final_question_text = "\n".join(cleaned_lines).strip()
        if not final_question_text:
            final_question_text = question_text or "Open ended radio question"
        print(f"[DEBUG] final_question_text => {final_question_text}")
        print(f"[DEBUG] radio options => {radio_labels}")
        prompt_text = f"Radio question: {final_question_text}\nOptions:\n" + "\n".join(f"{i+1}) {lab}" for i, lab in enumerate(radio_labels))
        ans = get_answer_cached(final_question_text, "radio", radio_labels)
        chosen_index = None
        if ans.isdigit():
            idx = int(ans) - 1
            if 0 <= idx < len(radio_labels):
                chosen_index = idx
        else:
            for i, lab in enumerate(radio_labels):
                if ans.lower() == lab.lower():
                    chosen_index = i
                    break
        if chosen_index is None:
            chosen_index = 0
            print("[WARN] No valid match => defaulting to first radio option")
        safe_click(radio_inputs[chosen_index])
        print(f"[DEBUG] Picked radio => {radio_labels[chosen_index]}")
        time.sleep(random.uniform(1,3))

#################################
# 6) DYNAMIC NAVIGATION (ENTIRE DOM)
#################################
def attempt_dynamic_navigation():
    next_buttons = driver.find_elements(
        By.XPATH,
        "//button[@data-easy-apply-next-button or contains(translate(text(),'CONTINUE','continue'),'continue')]"
    )
    if next_buttons:
        safe_click(next_buttons[0])
        print("[INFO] Clicked Next/Continue.")
        time.sleep(2)
        return True
    review_buttons = driver.find_elements(By.XPATH, "//button[@aria-label='Review your application']")
    if review_buttons:
        safe_click(review_buttons[0])
        print("[INFO] Clicked Review.")
        time.sleep(2)
        return True
    submit_buttons = driver.find_elements(By.XPATH, "//button[@aria-label='Submit application']")
    if submit_buttons:
        safe_click(submit_buttons[0])
        print("[INFO] Clicked Submit.")
        time.sleep(2)
        for attempt in range(10):
            done_buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(@class,'artdeco-button--primary') and .//span[text()='Done']]"
            )
            if done_buttons:
                safe_click(done_buttons[0])
                print("[INFO] Clicked Done => Application submitted.")
                time.sleep(2)
                return "submitted"
            else:
                print("[WARN] No Done button found yet. Retrying in 2 seconds...")
            time.sleep(2)
        print("[ERROR] 'Done' not found after multiple tries.")
        return False
    print("[INFO] No Next/Continue/Review/Submit found => fill form.")
    return False

#################################
# 7) APPLY LOGIC
#################################
def gather_job_cards():
    cards = driver.find_elements(By.XPATH, "//div[contains(@class,'job-card-container')]")
    valid = []
    for c in cards:
        html = c.get_attribute("outerHTML").lower()
        if "applied" in html or "in progress" in html:
            print("[INFO] Skipping card (already applied/in progress).")
            continue
        valid.append(c)
    return valid

# Define a list of base URLs (LinkedIn and additional sites)
BASE_URLS = [
    "https://www.linkedin.com/jobs/search/?currentJobId=4179422278&distance=25&f_AL=true&f_TPR=r86400&geoId=103644278&keywords=cybersecurity%20analyst&origin=JOB_SEARCH_PAGE_JOB_FILTER&spellCorrectionEnabled=true",
    "https://www.linkedin.com/jobs/search/?currentJobId=4181500420&distance=25&f_AL=true&f_TPR=r86400&geoId=103644278&keywords=penetration%20tester&origin=JOB_SEARCH_PAGE_SEARCH_BUTTON&refresh=true"
    "https://www.linkedin.com/jobs/search/?currentJobId=4181551061&f_AL=true&f_TPR=r86400&geoId=103743442&keywords=it&origin=JOB_SEARCH_PAGE_SEARCH_BUTTON&refresh=true"# Replace with your additional website URL
]

def apply_to_jobs():
    max_pages = 3
    for base_url in BASE_URLS:
        # For LinkedIn, we paginate; for others, we use the base URL as is.
        if "linkedin.com" in base_url:
            for page in range(1, max_pages + 1):
                start = (page - 1) * 25
                url = f"{base_url}&start={start}"
                print("[INFO] Opening LinkedIn page", page, ":", url)
                driver.get(url)
                time.sleep(random.uniform(1,3))
                process_job_cards()
        else:
            print("[INFO] Opening URL:", base_url)
            driver.get(base_url)
            time.sleep(random.uniform(1,3))
            process_job_cards()

def process_job_cards():
    cards = gather_job_cards()
    print(f"[INFO] Found {len(cards)} valid job cards.")
    for idx, card in enumerate(cards, start=1):
        print(f"[INFO] Processing card {idx}/{len(cards)}...")
        try:
            link = card.find_element(By.XPATH, ".//a[contains(@class, 'job-card-container__link')]")
        except NoSuchElementException:
            print("[WARN] No job link found => skipping card.")
            continue
        safe_click(link)
        time.sleep(random.uniform(1,3))
        try:
            easy_apply_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'jobs-apply-button')]")
            safe_click(easy_apply_btn)
            print("[INFO] Clicked Easy Apply.")
        except NoSuchElementException:
            print("[WARN] Easy Apply button not found => skipping job.")
            continue
        time.sleep(random.uniform(1,3))
        try:
            main_app_container = driver.find_element(
                By.XPATH,
                "//div[contains(@aria-label,'Your job application progress is at ')]"
            )
        except NoSuchElementException:
            print("[ERROR] Could not find main application container => skipping.")
            continue
        while True:
            old_state = get_form_state(main_app_container)
            nav = attempt_dynamic_navigation()
            new_state = get_form_state(main_app_container)
            if nav == "submitted":
                print("[INFO] Application submitted => moving to next job.")
                break
            if nav is True:
                if new_state == old_state:
                    print("[INFO] State unchanged => filling questions.")
                    fill_question_form(main_app_container)
                continue
            else:
                if new_state == old_state:
                    print("[INFO] No nav button and state unchanged => filling questions again.")
                    fill_question_form(main_app_container)
                else:
                    print("[INFO] State changed => filling questions again just in case.")
                    fill_question_form(main_app_container)
                time.sleep(2)

#################################
# 8) MAIN - REPEAT FOREVER
#################################
def main():
    drain_old_updates()
    load_cookies()
    handle_captcha()
    while True:
        apply_to_jobs()
        print("[INFO] All pages processed. Sleeping 2 hours before re-checking...")
        time.sleep(7200)  # 2 hours

if __name__ == "__main__":
    main()

