FROM python:3.11-slim

# Install ffmpeg and dependencies
RUN apt-get update && apt-get install -y ffmpeg

# Working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy your source code
COPY . .

# Expose your Flask API port
EXPOSE 5000

# Start Flask App
CMD ["gunicorn", "api:app", "--bind", "0.0.0.0:5000"]
