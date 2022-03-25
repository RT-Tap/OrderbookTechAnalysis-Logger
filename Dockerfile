# systemd package supports 3.9 at the highest atm if run onyl as application and not service remove from requirements.txt then we can use 3.1x
FROM python:3.9
WORKDIR /fintechapp
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python", "main.py" ]
# $ docker build -t my-python-app .
# $ docker run -it --rm --name my-running-app my-python-app
# single python script
# $ docker run -it --rm --name my-running-script -v "$PWD":/usr/src/myapp -w /usr/src/myapp python:3 python your-daemon-or-script.py