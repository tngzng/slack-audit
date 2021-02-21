FROM python:3.8.5-slim

WORKDIR /app

# install requirements
COPY ./requirements.txt /app/
COPY ./setup.py /app/

RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app/

CMD ["python", "/app/scrape_slack.py"]
