#!/bin/bash
result=$(python -m pip --version)
if [[ ${result} == "" ]]; then
    echo "pip does not exist please install pip before continuing"
    exit
fi
eval python -m pip install requirements.txt
mv vars.env /etc/systemd/fintechapp.conf
mv finTechApp_logger.service  /etc/systemd/user/fintechapp_logger.service
mv main.py /usr/bin/fintechapp
chmod +x /usr/bin/fintechapp