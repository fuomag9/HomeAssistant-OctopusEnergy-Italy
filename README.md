# Home Assistant Octopus Energy

![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_energy.total) [![](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86)](https://github.com/sponsors/fuomag9)
- [Home Assistant Octopus Energy](#home-assistant-octopus-energy)
  - [Features](#features)
  - [How to install](#how-to-install)
    - [HACS](#hacs)
    - [Manual](#manual)
  - [How to setup](#how-to-setup)
  - [FAQ](#faq)

Custom component built from the ground up to bring your Octopus Energy details into Home Assistant to help you towards a more energy efficient (and or cheaper) home. This integration is built against the API provided by Octopus Energy IT only.

# Warnings:
- ### Currently it only supports the first house automatically.
- ### Currently it does not have a way to specify that the data it gathers it's in the past because I suck at developing for home assistant (PLEASE HELP THIS CODE WORKS BY MIRACLES)

This integration is in no way affiliated with Octopus Energy.

## Features

Below are the main features of the integration

* Electricity support including consumption data

## How to install

Add the `Octopus Energy Italy` integration from the `Devices` page and put your credentials there.

### HACS

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This integration can be installed directly via HACS. To install:

* [Add the repository](https://my.home-assistant.io/redirect/hacs_repository/?owner=fuomag9&repository=HomeAssistant-OctopusEnergy-Italy&category=integration) to your HACS installation
* Click `Download`

### Manual

You should take the latest [published release](https://github.com/fuomag9/HomeAssistant-OctopusEnergy-Italy/releases). The current state of `develop` will be in flux and therefore possibly subject to change.

To install, place the contents of `custom_components` into the `<config directory>/custom_components` folder of your Home Assistant installation. Once installed, remember to restart your home assistant instance for the integration to be picked up.

## FAQ

If you have questions, then you can raise a [discussion](https://github.com/fuomag9/HomeAssistant-OctopusEnergy-Italy/discussions). If you have found a bug or have a feature request please [raise it](https://github.com/fuomag9/HomeAssistant-OctopusEnergy-Italy/issues)
