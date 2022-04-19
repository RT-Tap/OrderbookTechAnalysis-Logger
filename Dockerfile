# systemd package supports 3.9 at the highest atm if run onyl as application and not service remove from requirements.txt then we can use 3.1x
FROM python3
WORKDIR /fintechapp
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 6634
CMD [ "python", "main.py" ]
# $ docker build -t fintechapp_backend/logger:V0.1 .
# $ docker run -it --rm --name myAppNamep fintechapp_backend/logger:V0.1
# single python script
# $ docker run -it --rm --name test -v "$PWD":/usr/src/myapp -w /usr/src/myapp python:3 python your-daemon-or-script.py