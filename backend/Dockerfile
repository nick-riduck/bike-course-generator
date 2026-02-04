# Use official lightweight Python image
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port (Cloud Run defaults to 8080)
ENV PORT=8080

# Run the application
# Cloud Run injects the PORT env var, but we set a default above.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
