FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 blood \
    && useradd --uid 10001 --gid blood --no-create-home blood
COPY backend/ /app/backend/
COPY results/ /app/results/
USER blood
EXPOSE 5000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "--bind", "0.0.0.0:5000", "wsgi:app"]
