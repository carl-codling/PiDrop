# PiDrop
This project was created uising the Dropbox Python SDK to give me some tools to manage a dropbox on my Raspberry Pi 3 Model B+ and provides basic (see limitations below) syncing of dropbox folders and a text based UI (with Urwid) for manging those files and folders.

Dropbox does provide some CL tools for working on Linux systems but they are'nt compatible with ARM based architecture so this code my be either a solution or starting point for other projects on similar setups. 

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
- On first run of pidrop if certain config options aren't set then you'll be asked to add them. It's best to run with the cfg option first and configure all available options
```console
sudo python ~/PiDrop/pidrop.py cfg
```
- You can then run the script again in default mode and any folders you chose to sync will now start to download 
```console
sudo python ~/PiDrop/pidrop.py 
```

## Text Based UI

__There's also a user interface for moving, deleting and importing files__

- You'll need Urwid installed for this:
```console
pip install urwid
```
- And then you can run
```console
sudo python ~/PiDrop/pidrop-ui.py 
```

__To make moving files back and forth between the Pi and the device SSHing in to it easier there's an import and export folder__
These can be configured through the config process mentioned above

For example you can then copy the whole export folder to the host machine with SCP
```console
scp -r -l 2000 pi@192.168.0.23:"'/path/to/export/directory'" ~/Target
```

Or send some files to your import folder:
```console
scp /path/of/file/to.send pi@192.168.0.23:/path/to/import/dir
```

## Setting it to run Auto-magically with Cron

- To do this you need to create a cronjob on the Pi
- First of all configure/edit the bash script we'll trigger with cron
```console
sudo nano ~/PiDrop/pidrop_cron.sh
```
- And edit these 2 lines to match your setup:
```
STORAGE=/media/pidrive # Full path of the drive where your local dropbox is
PIDROPFILE=/home/pi/PiDrop/pidrop.py # Full path to your pidrop.py file 
```
- Now create a cron job by editing the cron file:
```console
sudo crontab -e
```
- And then add a cronjob to the end of the file:
```
0 * * * * sh /home/pi/PiDrop/pidrop_cron.sh
```
*(the above example will run the script once every hour on the hour)*

## Limitations
- You can only sync root directories in your dropbox

__Your local folders and the folders on the Dropbox servers should stay in sync so long as all deletions and file moves are done locally. If you make changes from a different machine  (eg. online or from your home pc software) PiDrop on your Pi will not be aware of this and conflicts may happen. This has at least the following implications:__
- If you delete a file/folder from a different location such as another computer PiBox will see that it has a file/folder locally that doesn't exist on the server and upload it again
- Likewise if you move a file/folder PiBox will both upload to the old location and download from the new so you'll end up with duplicates.

*__For these reasons all modifications on synced folders should be done through the PiDrop UI__*