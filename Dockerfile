FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

EXPOSE 18001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "18001"]
