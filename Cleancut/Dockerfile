# Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies required by OpenCV and Rembg
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Pre-download the rembg model to bake it into the Docker image.
# This prevents BrokenPipeError/timeouts on Hugging Face startup.
RUN python -c "from rembg import new_session; new_session('isnet-general-use')"

# Ensure the database directory has proper permissions
RUN chmod -R 777 .

# Run the FastAPI application on port 7860 (Hugging Face default)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
