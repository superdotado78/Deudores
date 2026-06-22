FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8501
# Default local DB value; can be overridden by Render / env vars
ENV DATABASE_URL=sqlite:///prestamos.db
# Use shell form to allow expansion of $PORT at runtime (Render sets PORT)
CMD ["bash", "-lc", "streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8501}"]
