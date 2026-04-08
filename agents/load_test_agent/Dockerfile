FROM python:3.11-slim

WORKDIR /app

# Install dependencies
# We assume the build context is the project root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code and dependencies
COPY . ./agents/load_test_agent

# Set working directory to test_agent
WORKDIR /app/agents/load_test_agent

# Set python path to include project root
ENV PYTHONPATH=/app

# Run the job driver
ENTRYPOINT ["python", "load_generator.py"]
