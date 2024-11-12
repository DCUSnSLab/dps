# 베이스 이미지
FROM python:3.9-slim

# 작업 디렉토리 설정
WORKDIR /app

RUN apt update
RUN apt upgrade -y
RUN apt install vim gedit -y

# 종속성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install -r requirements.txt

# 애플리케이션 파일 복사
COPY app.py .
COPY templates/ ./templates/

# Flask 서버 실행
CMD ["python", "app.py"]
