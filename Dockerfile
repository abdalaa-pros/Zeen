FROM python:3.11-slim

# أدوات ومكتبات لازمة لتشغيل كروم داخل الحاوية
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl unzip gnupg ca-certificates \
    libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libx11-6 libx11-xcb1 libxcb1 libxext6 libcups2 libxrender1 \
    libxi6 libxtst6 libdbus-1-3 libxshmfence1 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Google Chrome (stable)
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
 && apt-get update \
 && apt-get install -y ./google-chrome-stable_current_amd64.deb \
 && rm -f google-chrome-stable_current_amd64.deb

# تنزيل chromedriver المطابق لإصدار Chrome
RUN set -eux; \
  CHROME_MAJOR=$(google-chrome --version | awk '{print $3}' | cut -d'.' -f1); \
  LATEST=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR}"); \
  curl -L "https://chromedriver.storage.googleapis.com/${LATEST}/chromedriver_linux64.zip" -o /tmp/chromedriver.zip; \
  unzip /tmp/chromedriver.zip -d /usr/local/bin/; \
  rm /tmp/chromedriver.zip; \
  chmod +x /usr/local/bin/chromedriver

# تثبيت باكدجات بايثون
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# تشغيل البوت
CMD ["python", "main.py"]
