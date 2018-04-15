# PiDrop
CL Tools and Text Based UI for managing Dropbox folders on a headless RaspberryPi

## Assumed Setup:

- RaspberryPi 3
- External USB HD (I'm using a WD PiDrive) with enough storage for the dropbox folders you want to sync
- Raspbian Stretch Lite
- A device to SSH in to the Pi
- A dropbox account and API access token (get one here https://www.dropbox.com/developers/apps)

## Setup / Configure

- Clone this repo to the home dir of your Pi
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
- And add, for example (this will run the script once every hour on the hour)
```
0 * * * * sh /home/pi/pidrop_cron.sh
```

## Limitations

You will not get a full sync of the folder as if you had installed the Dropbox propriety software. Any changes you make to a folder which is synced to PiDrop from a different location will not be known by PiDrop. This has at least the following implications:
- If you delete a file/folder from a different location (eg. online or from your home pc software) PiBox will see that it has a file/folder locally that doesn't exist on the server and upload it again
- Likewise if you move a file/folder PiBox will both upload to the old location and download from the new sp you'll end up with  duplicates

* For these reasons all modifications on synced folders should be done through the PiDrop UI