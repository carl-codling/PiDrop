#!/bin/bash
LOCKFILE=/tmp/pidroplock.txt
#STORAGE=/media/pidrive # Full path of the drive where your local dropbox is
PIDROPFILE=/home/pi/pidrop/pidrop.py # Full path to your pidrop.py file 


# if  mountpoint -q ${STORAGE}; then
#     echo "${STORAGE} is mounted"
# else
#     echo "${STORAGE} is not a mountpoint"
#     exit
# fi

# if grep "\sro[\s,]" ${STORAGE}; then
#     echo "${STORAGE} is not writable"
#     exit
# else
#     echo "${STORAGE} is writable"
# fi     

if [ -e ${LOCKFILE} ] && kill -0 `cat ${LOCKFILE}`; then
    echo "already running"
    exit
fi

# make sure the lockfile is removed when we exit and then claim it
trap "rm -f ${LOCKFILE}; exit" INT TERM EXIT
echo $$ > ${LOCKFILE}

python ${PIDROPFILE}

rm -f ${LOCKFILE}