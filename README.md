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
sudo ~/pidrop/pidrop.py cfg
```
- You can then run the script again in default mode and any folders you chose to sync will now start to download 
```console
sudo ~/pidrop/pidrop.py 
```
