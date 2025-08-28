import os
import re
import logging
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zain-bot")

# خليه كمتغير بيئة في Railway: BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")

# -------- Selenium setup --------
def create_browser():
    opts = Options()
    # تشغيل Headless Chrome في الحاوية
    opts.binary_location = "/usr/bin/google-chrome"
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,2400")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    # User-Agent
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")

    service = Service("/usr/local/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=opts)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except Exception:
        pass
    return driver

def parse_amount_any(text: str) -> float:
    if not text:
        return 0.0
    clean = re.sub(r"(SR|ر?يال|SAR|ر\.س|\s)", "", text, flags=re.I)
    clean = clean.replace(",", "")
    m = re.search(r"(\\d+(\\.\\d+)?)", clean)
    try:
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0

def find_site_amount(driver) -> float:
    wait = WebDriverWait(driver, 15)
    try:
        el = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "input[id*=amount], input[name*=amount], input[formcontrolname*=amount]"
        )))
        val = (el.get_attribute("value") or el.get_attribute("placeholder") or "").strip()
        amt = parse_amount_any(val)
        if amt > 0:
            return amt
    except Exception:
        pass
    try:
        candidates = driver.find_elements(By.XPATH, "//*[contains(., 'SR') or contains(., 'ريال') or contains(., 'ر.س') or contains(., 'SAR')]")
        for c in candidates:
            amt = parse_amount_any(c.text)
            if amt > 0:
                return amt
    except Exception:
        pass
    try:
        nodes = driver.find_elements(By.XPATH, "//*")
        for n in nodes:
            t = (n.text or "").strip()
            if any(ch.isdigit() for ch in t):
                amt = parse_amount_any(t)
                if amt > 0:
                    return amt
    except Exception:
        pass
    return 0.0

def build_url(contract_number: str) -> str:
    cn = str(contract_number).strip()
    if cn.startswith("2"):
        return f"https://app.sa.zain.com/en/quickpay?account={cn}"
    return f"https://app.sa.zain.com/en/contract-payment?contract={cn}"

def check_single_contract(contract_number: str, sheet_amount) -> str:
    driver = create_browser()
    try:
        url = build_url(contract_number)
        logger.info(f"Opening: {url}")
        driver.get(url)
        site_amount = find_site_amount(driver)
        try:
            sheet_amount = float(sheet_amount)
        except Exception:
            sheet_amount = 0.0
        if site_amount <= 0:
            try:
                os.makedirs("shots", exist_ok=True)
                shot_path = f"shots/{contract_number}.png"
                driver.save_screenshot(shot_path)
                logger.info(f"Saved screenshot: {shot_path}")
            except Exception:
                pass
            return f"❌ لم يتم العثور على المبلغ للعقد: {contract_number}"
        if sheet_amount == 0:
            return f"📌 الموقع: {site_amount} ريال"
        if site_amount > sheet_amount:
            return f"📌 غير مسددة - الموقع: {site_amount} ريال | الملف: {sheet_amount} ريال"
        elif site_amount < sheet_amount:
            return f"⚠️ مختلف - الموقع: {site_amount} ريال | الملف: {sheet_amount} ريال"
        else:
            return f"📌 غير مسددة - {site_amount} ريال"
    finally:
        driver.quit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً! ارفع ملف Excel (عمود1: رقم العقد، عمود2: المبلغ).")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith((".xlsx", ".xls")):
        await update.message.reply_text("📄 من فضلك ارفع ملف Excel فقط (xlsx/xls).")
        return
    file = await doc.get_file()
    path = "uploaded.xlsx"
    await file.download_to_drive(path)
    df = pd.read_excel(path)
    results = []
    for _, row in df.iterrows():
        try:
            contract_number = str(row.iloc[0]).strip()
            sheet_amount = row.iloc[1]
            if not contract_number or not any(ch.isdigit() for ch in contract_number):
                continue
        except Exception:
            continue
        status = check_single_contract(contract_number, sheet_amount)
        results.append([contract_number, sheet_amount, status])
    out = pd.DataFrame(results, columns=["Contract", "Sheet_Amount", "Status"])
    out_path = "results.xlsx"
    out.to_excel(out_path, index=False)
    await update.message.reply_document(open(out_path, "rb"), caption="نتائج الفحص ✅")
    try:
        shots_dir = "shots"
        if os.path.isdir(shots_dir):
            shots = [os.path.join(shots_dir, f) for f in os.listdir(shots_dir) if f.endswith(".png")]
            for i, s in enumerate(shots[:5], start=1):
                await update.message.reply_photo(open(s, "rb"), caption=f"Screenshot #{i}")
    except Exception:
        pass

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود. أضفه في Railway Secrets.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()

if __name__ == "__main__":
    main()
