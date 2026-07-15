FROM python:3.12-slim

WORKDIR /app

# Install all dependencies
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]==0.34.0" \
    boto3 \
    pandas \
    "xgboost[cpu]==2.1.4" \
    lightgbm==4.6.0 \
    scikit-learn==1.6.1 \
    numpy==1.26.4

# Copy application files
COPY handler.py app.py ./
COPY model/ ./model/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
