# Dockerfile for CAN Backend
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for USB support
RUN apt-get update && apt-get install -y \
    libusb-1.0-0 \
    libusb-1.0-0-dev \
    udev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy drivers (from parent directory)
COPY drivers/ /app/drivers/

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "api.py"]
