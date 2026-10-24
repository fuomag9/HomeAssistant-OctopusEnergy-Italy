# Home Assistant Octopus Energy

![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_energy.total) [![](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86)](https://github.com/sponsors/fuomag9)
- [Home Assistant Octopus Energy](#home-assistant-octopus-energy)
  - [Features](#features)
  - [How to install](#how-to-install)
    - [HACS](#hacs)
    - [Manual](#manual)
  - [How to setup](#how-to-setup)
  - [Delayed data and the Energy dashboard](#delayed-data-and-the-energy-dashboard)
  - [Gas](#gas)
  - [FAQ](#faq)

Custom component built from the ground up to bring your Octopus Energy details into Home Assistant to help you towards a more energy efficient (and or cheaper) home. This integration is built against the API provided by Octopus Energy IT only.

# Warnings:
- ### Currently it only supports the first house automatically.

This integration is in no way affiliated with Octopus Energy.

## Features

Below are the main features of the integration

* Electricity support including consumption data, in total and split by F1/F2/F3 band
* Daily readings imported as long-term statistics on the day they were consumed (see [Delayed data](#delayed-data-and-the-energy-dashboard))
* Gas support: monthly meter readings imported as a gas consumption statistic (see [Gas](#gas))

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

## Delayed data and the Energy dashboard

Octopus Energy Italy publishes smart meter readings with a delay (currently about two days). A sensor can only hold a value "now", so the `Octopus IT Daily ...` sensors always show the most recent complete day available. The day that value belongs to is exposed in their `measurement_date` attribute.

To keep the history on the correct days, the integration also imports the last 30 days of readings as long-term statistics, stamped with the day they were actually consumed. They are refreshed on every update, so late corrections from Octopus are picked up. One statistic is created per sensor:

| Statistic | Content |
| --- | --- |
| `Octopus IT Daily Total` | Total consumption |
| `Octopus IT Daily F1` / `F2` / `F3` | Consumption per band |

Use these statistics, not the sensor entities, wherever the date matters:

* **Energy dashboard**: *Settings > Dashboards > Energy > Add consumption* and pick `Octopus IT Daily Total`.
* **Statistics graph card**: select the same statistics by name.

Readings are daily, so each day's consumption appears as a single bar at the start of that day and the hourly breakdown is not available.

The sensors no longer record their own statistics, as these would be dated when they were polled rather than when the energy was used. If you used them in the Energy dashboard before, replace them with the statistics above. Home Assistant may also offer to remove the old statistics under *Developer tools > Statistics*.

## Gas

If your property has a gas supply, the integration also imports its consumption as a statistic named `Octopus IT Gas Consumption`, in m³. There are no gas sensors.

Octopus provides one gas meter reading per month (a cumulative meter index in m³, dated the last day of the month), so gas works differently from electricity:

* A month's consumption is the difference between two consecutive readings, so the first reading is only a starting point and the newest month appears once its reading arrives, a while after the month ends.
* The whole month's consumption is recorded on the day of the reading. Month and year views in the Energy dashboard are accurate, while day and week views show it as one spike on the last day of the month.
* Only actual readings are used. Estimates are ignored, so properties without a smart gas meter may have few or no readings.

To use it, add *Settings > Dashboards > Energy > Add gas source* and pick `Octopus IT Gas Consumption`. Gas readings are checked twice a day.

## FAQ

If you have questions, then you can raise a [discussion](https://github.com/fuomag9/HomeAssistant-OctopusEnergy-Italy/discussions). If you have found a bug or have a feature request please [raise it](https://github.com/fuomag9/HomeAssistant-OctopusEnergy-Italy/issues)
