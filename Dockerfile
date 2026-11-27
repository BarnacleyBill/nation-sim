FROM python:3.12-slim
WORKDIR /app
COPY sim ./sim
ENV NATION_DATA=/data PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["python", "-m", "sim"]
CMD ["status"]
