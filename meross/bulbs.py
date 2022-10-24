#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import os
from random import randint
from time import sleep

from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager
from meross_iot.model.enums import OnlineStatus

# https://albertogeniola.github.io/MerossIot/api-reference/controller/mixins/light.html

def configureLogging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        format='%(asctime)s:%(levelname)s:%(message)s', level=log_level)
    logging.debug("Log Level: " + str(logging.getLogger().getEffectiveLevel()
                                      ) + ".  To override, set LOG_LEVEL environment variable.")
    return logging.getLogger()

def baseLevel():
    return { "color": (255, 255, 255), "luminance": 30}


def stealth():
    return { "color": (139, 0, 0), "luminance": 5}


def psychedelic():
    psychedelicGreen = (71, 255, 49)
    psychedelicPink = (245, 106, 196)
    psychedelicAqua = (56, 215, 255)
    psychedelicYellow = (255, 245, 61)
    blue = (86, 0, 204)
    pink = (255, 1, 215)
    psychedelicBlue = (0, 56, 255)
    psychedelicPurple =  (223, 0, 255)
    return [psychedelicGreen, psychedelicBlue, psychedelicAqua, psychedelicPink, pink, psychedelicPurple, blue, psychedelicYellow]


def brightPrimary():
    yellow = (255, 235, 0)
    red = (252, 0, 25)
    green = (1, 255, 79)
    pink = (255, 1, 215)
    blue = (86, 0, 204)
    turquoise = (0, 237, 245)
    return [yellow, red, green, pink, blue, turquoise]

def brightPrimary2():
    return { 
        "yellow": { "color": (255, 235, 0), "luminance": 100},
        "red":(252, 0, 25),
        "green": (1, 255, 79),
        "pink": (255, 1, 215),
        "blue": (86, 0, 204),
        "turquoise": (0, 237, 245)
    }
    return [yellow, red, green, pink, blue, turquoise]


async def setColor(device, color, lum, on_off = None):
    if on_off != None:
        return await device.async_set_light_color(rgb = color, luminance = lum, onoff = on_off)
    return await device.async_set_light_color(rgb = color, luminance = lum)


def parseArgs():
    parser = argparse.ArgumentParser(description='Use to control Meross devices', allow_abbrev=True)
    parser.add_argument("-u", required=False, type=str, default=str(os.getenv('MU', "none@bunkemail.org")),
                        help="Meross user name")
    parser.add_argument("-p", required=False, type=str, default=str(os.getenv('MP', "MerossControlPlanePw")),
                        help="Meross password")
    parser.add_argument("--deviceUUID", "-d", required=False, type=str, default="20120758000988290d2148e1e93e2c41",
                        help="Meross Device UUID, default is %(default)s")
    parser.add_argument("--deviceType", "-t", required=False, type=str, default="msl120d",
                        help="Device model, default is %(default)s")
    parser.add_argument("--iterations", "-i", required=False, type=str, default=str(os.getenv('ITERATIONS', "1000")),
                        help="Number of iterations to run through.  Default is %(default)s")
    parser.add_argument("--colorGroup", "-c", required=False, type=str, default=str(os.getenv('COLORGROUP', "random")),
                        help="Color group.  Default is %(default)s", choices=["psychedelic", "primary", "stealth", "normal", "random", "off"])   
    return parser.parse_args()


async def main(logger):
    configureLogging()
    args = parseArgs()

    
    # Setup the HTTP client API from user-password
    http_api_client = await MerossHttpClient.async_from_user_password(
        str(args.u),
        str(args.p),
        api_base_url="https://iot.meross.com/"   
    )

    logger.info("Session info " + str(http_api_client.cloud_credentials))

    # Setup and start the device manager
    manager = MerossManager(
        http_client=http_api_client,
        auto_reconnect=True
    )

    await manager.async_init()

    if str(args.deviceUUID) != None:
        disco = await manager.async_device_discovery(meross_device_uuid=str(args.deviceUUID))
        bulbs = manager.find_devices(device_uuids=[args.deviceUUID], device_type=args.deviceType, online_status=OnlineStatus.ONLINE)
    else:
        disco = await manager.async_device_discovery()
        bulbs = manager.find_devices(device_type=args.deviceType, online_status=OnlineStatus.ONLINE)

    logger.debug("Discovered devices: " + str(disco))
    logger.debug("Found " + str(len(bulbs)) + " bulbs: " + str(bulbs))

    
    if len(bulbs) < 1:
        logger.error(f'No online {args.deviceType} bulbs found...')


    for dev in bulbs:

        # Update device status: this is needed only the very first time we play with this device (or if the
        #  connection goes down)
        await dev.async_update()

        if not dev.get_supports_rgb():
            logger.error(dev.name + " does not support RGB...")
            continue
        else:
            logger.debug("RGB is supported! Continuing...")
            base = baseLevel().get('color')
            baseLuminance = baseLevel().get('luminance')

            if not dev.get_light_is_on():
                logger.info("Turning on " + dev.name)
                await dev.async_set_light_color(rgb=base, luminance = baseLuminance, onff=True)


            # Check the current RGB color
            current_color = dev.get_rgb_color()
            luminance = dev.get_luminance()

            logger.debug(f"Device {dev.name} is set to color (RGB) = {current_color} - luminance = {luminance}")

            logger.debug("Name: " + dev.name + " - " + dev.uuid + ", Abilities: \n" + json.dumps(dev.abilities))



            if args.colorGroup == "psychedelic":
                colorSet = psychedelic()
                luminance = 100
            elif args.colorGroup == "primary":
                colorSet = brightPrimary()
                luminance = 100
            elif args.colorGroup == "stealth":
                await dev.async_set_light_color(rgb = stealth().get('color'), luminance = stealth().get('luminance'))
                #setColor(dev, stealth().get('color'), stealth().get('luminance'))
                sleep(2)
                break
            elif args.colorGroup == "normal":
                await dev.async_set_light_color(rgb = base, luminance = baseLuminance)
                #setColor(dev, baseLevel().get('color'), baseLevel().get('luminance'), True)
                sleep(2)
                break
            elif args.colorGroup == "off":
                await dev.async_set_light_color(rgb = base, luminance = baseLuminance, onff=False)
                #setColor(dev, baseLevel().get('color'), baseLevel().get('luminance'), False)
                sleep(2)
                break
            else:
                # Randomly chose a new color
                colorSet=[]
                for c in range(1, 10):
                    rando = randint(0, 255), randint(0, 255), randint(0, 255)
                    colorSet.append(rando)
                    print("Random color " + str(c) + ": " + str(rando))

            iterations = int(args.iterations)
            i = 0
            while i < iterations:
                i += 1
                for color in colorSet:
                    logger.debug(f"Setting color to {color}, iteration {i}")
                    await dev.async_set_light_color(rgb = color, luminance = luminance)
                    #setColor(dev, baseLevel().get('color'), baseLevel().get('luminance'))
                    await asyncio.sleep(3)

            logger.info(f'Completed!  Setting color to {current_color} after {iterations} iterations.')
            await dev.async_set_light_color(rgb = current_color, luminance = luminance)
            #setColor(dev, current_color, luminance)

    # Close the manager and logout from http_api
    manager.close()
    await http_api_client.async_logout()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(logger=configureLogging()))
    loop.close()
