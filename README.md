# PiDrop
This project was created uising the Dropbox Python SDK to give me some tools to manage a dropbox on my headless (no monitor) Raspberry Pi 3 Model B+ and provides basic syncing of dropbox folders and a text based UI (with Urwid) for manging those files and folders.

Dropbox does provide some CL tools for working on Linux systems but they are'nt compatible with ARM based architecture so this code may be either a solution or starting point for other projects on similar setups. 

## Assumed Setup:

This was built with:
- RaspberryPi 3 with Raspbian Stretch Lite installed
- External USB HD (I'm using a WD PiDrive) with enough storage for the dropbox folders you want to sync
- A device to SSH in to the Pi
- A dropbox account and API access token (get one here https://www.dropbox.com/developers/apps)

## Setup / Configure

- Clone this repo to the home dir of your Pi
```console
cd ~
git clone https://github.com/carl-codling/PiDrop.git
```
- install the Dropbox SDK
```console
pip install dropbox
```
- You'll also need Urwid installed:
```console
pip install urwid
```
- Now run PiDrops setup function
```console
sudo python ~/PiDrop/pidrop.py setup
```
- Once you've successfully entered your Dropbox API token the PiDrop UI will automatically open. From here you can make further configuration such as choosing folders to sync. Once some folders have synced you'll also be able to use the file browser/manager.
- Next time you wish to open the UI use the instructions in the following section:

## Text Based UI

__There's also a user interface for moving, deleting and importing files__


- To open the TUI:
```console
sudo python ~/PiDrop/pidrop.py ui 
```

__To make moving files back and forth between the Pi and the device SSHing in to it easier there's an import and export folder__
* See the section 'Simplify Sending and Recieviing from your local machine:' at the end of this file for more ideas

These can be configured through the config process mentioned above

For example you can then copy the whole export folder to the host machine with SCP
```console
scp -r -l 2000 pi@192.168.0.23:"'/path/to/pidrop_out'" ~/Target
```

Or send some files to your import folder:
```console
scp /path/of/file/to.send pi@192.168.0.23:/path/to/pidrop_in
```

## Setting it to run Auto-magically with Cron

- To do this you need to create a cronjob on the Pi
- First of all check that the bash script we'll trigger with cron is pointing to our Python script (if you installed in the home dir of your Pi it should be fine)
```console
sudo nano ~/PiDrop/pidrop_cron.sh
```
- And edit this line if you didn't install PiDrop in your Pi home dir:
```
PIDROPFILE=/home/pi/PiDrop/pidrop.py # Full path to your pidrop.py file 
```
- Now create a cron job by editing the cron file:
```console
sudo crontab -e
```
- And then add a cronjob to the end of the file such as:
```
0 * * * * sh /home/pi/PiDrop/pidrop_cron.sh
```
*(the above example will run the script once every hour on the hour)*

### Simplify Sending and Recieviing from your local machine:

To simplify this process I set up a Bash script on my local machine (Linux Mint) that allows me to simply type 'pidrop get' or 'pidrop send' in to a terminal. Here are the steps I followed:

1) Create 2 folders on your local machine that match the names of your import and export folders on the Pi. In the example we have pidrop_in and pidrop_out
2) Create a file called pidrop in /usr/bin
```console
sudo touch /usr/bin/pidrop
```
3) Give it execute permissions
```console
sudo chmod -x /usr/bin/pidrop
```
4) Open it for editing
```console
sudo nano /usr/bin/pidrop
```
5) Enter the following text changing PI_PATH, LOCAL_PATH, INBOX, OUTBOX and PIIP accordingly
```console
#!/bin/bash
PI_PATH=/media/pidrive #location of you import and export dirs on the Pi
LOCAL_PATH=/home/kailash #location of the folders on your local machine
INBOX=dbox_in #import dir name
OUTBOX=dbox_out #export dir name
if [ -z ${2+x} ]; then
    PIIP=192.168.0.23 #ip address of your Pi
else
    PIIP=$2
fi
if [[ $1 = 'send' ]]; then
    scp -r ${LOCAL_PATH}/${INBOX} pi@${PIIP}:${PI_PATH}
elif [[ $1 = 'get' ]]; then
    scp -r -l 2000 pi@${PIIP}:${PI_PATH}/${OUTBOX} ${LOCAL_PATH} # -l 2000 limitation can be removed if not necessary
fi
 ```
6) Now you can simply type 'pidrop get' or 'pidrop send' in to a terminal to transfer files back and forth.

NB. If the address of your Pi changes frequently you can run these commands as:
```
 pidrop get/send <Raspberry Pi IP>
```

#### Sending from Android

I set up a similar system on my (rooted) Android phone. This time I only wanted to send photos/videos from my phone to PiDrop.

Steps:

1) install the Termux app so we have a console to use
2) enter the following command in to Termux so we can access files on the phone:
```
termux-setup-storage
```
3)Create a file called pidrop in /system/bin and with a text editor add the following (modified for your systems file paths)
```
#!/system/bin/bash

scp -r /path/to/your/files/DCIM/Camera pi@192.168.0.23:/path/to/pidrop_in
```
- Now you can send your files to pidrop any time by using the following command in Termux:
```
sh /system/bin/pidrop
```