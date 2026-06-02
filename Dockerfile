FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

EXPOSE 18001

COPY entrypoint.sh .
# RUN sed -i 's/\r$//' entrypoint.sh
RUN chmod +x entrypoint.sh
# CMD ["sh", "./entrypoint.sh"]
CMD ["./entrypoint.sh"]
