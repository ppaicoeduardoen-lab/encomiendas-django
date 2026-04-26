# Usamos exactamente la misma versión que tienes en tu laptop
FROM python:3.13-slim

# Evitar archivos .pyc y buffering de stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar el código
COPY . .

# Puerto
EXPOSE 8000

# Comando para iniciar
#CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]