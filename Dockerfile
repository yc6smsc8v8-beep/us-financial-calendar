FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["sh", "-c", "gunicorn app_combined_safe:app --bind 0.0.0.0:${PORT:-5000} --workers 1 --timeout 120"]
