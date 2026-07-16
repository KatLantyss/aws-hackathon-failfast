FROM python:3.12-slim

WORKDIR /app

# lightgbm needs libgomp1 (OpenMP runtime), not included in python:slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install all dependencies
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]==0.34.0" \
    boto3==1.42.58 \
    pandas \
    "xgboost[cpu]==2.1.4" \
    lightgbm==4.6.0 \
    scikit-learn==1.6.1 \
    "numpy>=2" \
    shap==0.52.0

# Copy application files
COPY handler.py app.py nlu.py ./
COPY model/ ./model/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
