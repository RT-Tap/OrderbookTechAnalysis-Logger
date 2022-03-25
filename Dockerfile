FROM python:3
WORKDIR /fintechapp
RUN apt-get install python-systemd python3-systemd
COPY . .
# COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python", "main.py" ]
# $ docker build -t my-python-app .
# $ docker run -it --rm --name my-running-app my-python-app
# single python script
# $ docker run -it --rm --name my-running-script -v "$PWD":/usr/src/myapp -w /usr/src/myapp python:3 python your-daemon-or-script.py